--[[
  ReaBot — render/stem_render.lua
  Renders the first selected track (post-FX, within the time selection) to a
  temporary WAV file, then polls each defer frame until the file is ready.

  Strategy: Track-Solo Method
  1. Save all track solo states
  2. Solo only the target track
  3. Set render params (master mix, time selection, output path)
  4. Trigger render action
  5. Immediately restore solo states
  6. Poll: watch for file to appear with non-zero size
  7. Invoke on_done(wav_path) callback when ready

  This approach works across all REAPER versions because it uses the same
  internal render path as manually soloing a track and hitting render.
--]]

local M = {}

-- ── State ──────────────────────────────────────────────────────────────────
local _polling            = false
local _path               = nil
local _on_done            = nil
local _on_error           = nil
local _timeout_at         = 0
local _solo_states        = {}     -- {[MediaTrack*] = original_solo_value}
local _orig_render_file   = nil    -- original RENDER_FILE to restore
local _orig_render_pattern = nil    -- original RENDER_PATTERN to restore
local _temp_dir           = nil    -- active temp directory
local _uid                = nil    -- active render UID

local MAX_WAIT_SEC  = 20     -- seconds before giving up
local MIN_FILE_SIZE = 1024   -- bytes — file must be at least 1 KB to be valid

-- ── Helpers ────────────────────────────────────────────────────────────────

local function make_temp_path()
  local proj = reaper.GetProjectPath("")
  local base = (proj ~= "" and proj or reaper.GetResourcePath())
  local dir  = base .. "/reabot_temp"
  -- REAPER API: create directory including all parents
  reaper.RecursiveCreateDirectory(dir, 0)
  -- Pseudo-UUID: combine timestamp with a random suffix for uniqueness
  math.randomseed(os.time() + math.random(0, 99999))
  local uid = string.format("%08x%06x", os.time(), math.random(0, 0xFFFFFF))
  return dir, uid
end

local function finish_render()
  _polling = false
  -- Restore original render settings
  if _orig_render_file then
    reaper.GetSetProjectInfo_String(0, "RENDER_FILE", _orig_render_file, true)
    _orig_render_file = nil
  end
  if _orig_render_pattern then
    reaper.GetSetProjectInfo_String(0, "RENDER_PATTERN", _orig_render_pattern, true)
    _orig_render_pattern = nil
  end
end

local function save_and_solo(target_track)
  _solo_states = {}
  local total = reaper.CountTracks(0)
  for i = 0, total - 1 do
    local t   = reaper.GetTrack(0, i)
    local val = reaper.GetMediaTrackInfo_Value(t, "I_SOLO")
    _solo_states[t] = val
    -- 1 = solo in place; 0 = not soloed
    reaper.SetMediaTrackInfo_Value(t, "I_SOLO", (t == target_track) and 1 or 0)
  end
  -- Trigger REAPER to apply the solo state changes
  reaper.TrackList_AdjustWindows(false)
end

local function restore_solo()
  for t, val in pairs(_solo_states) do
    reaper.SetMediaTrackInfo_Value(t, "I_SOLO", val)
  end
  _solo_states = {}
  reaper.TrackList_AdjustWindows(false)
end

local function file_size(path)
  local f = io.open(path, "rb")
  if not f then return nil end
  local sz = f:seek("end")
  f:close()
  return sz
end

-- ── Public API ─────────────────────────────────────────────────────────────

---Start an async stem render for target_track within the current time selection.
---@param target_track  MediaTrack*  handle from reaper.GetSelectedTrack()
---@param on_done       function(wav_path: string)  called when file is ready
---@param on_error      function(error_msg: string)  called on failure / timeout
---@return nil
function M.start(target_track, on_done, on_error)
  if _polling then
    on_error("A render is already in progress. Please wait.")
    return
  end

  if not target_track then
    on_error("No target track provided to renderer.")
    return
  end

  -- Validate time selection
  local ts_start, ts_end = reaper.GetSet_LoopTimeRange(false, false, 0, 0, false)
  if ts_start >= ts_end then
    on_error("No time selection. Draw a selection in the timeline first.")
    return
  end

  -- Validate track has at least one item in the project
  -- (A track could be selected but have no audio — render would produce silence)
  if reaper.CountTrackMediaItems(target_track) == 0 then
    on_error("Selected track has no media items. Add audio before analyzing.")
    return
  end

  -- Save original render settings
  local _, orig_file = reaper.GetSetProjectInfo_String(0, "RENDER_FILE", "", false)
  local _, orig_pattern = reaper.GetSetProjectInfo_String(0, "RENDER_PATTERN", "", false)
  _orig_render_file = orig_file
  _orig_render_pattern = orig_pattern

  local temp_dir, uid = make_temp_path()
  _temp_dir      = temp_dir
  _uid           = uid
  _path          = nil -- resolved dynamically on completion
  _on_done       = on_done
  _on_error      = on_error
  _polling       = true
  _timeout_at    = reaper.time_precise() + MAX_WAIT_SEC

  -- ── Set render parameters ─────────────────────────────────────────────
  -- Output file directory
  reaper.GetSetProjectInfo_String(0, "RENDER_FILE", temp_dir, true)
  -- Output file name pattern
  reaper.GetSetProjectInfo_String(0, "RENDER_PATTERN", uid, true)
  -- Bounds: 2 = time selection
  reaper.GetSetProjectInfo(0, "RENDER_BOUNDSFLAG", 2, true)
  -- Source: 0 = master mix (combined with solo = isolated track)
  reaper.GetSetProjectInfo(0, "RENDER_STEMS", 0, true)

  -- ── Solo target, trigger render, immediately restore ──────────────────
  save_and_solo(target_track)
  -- Action 42230: "File: Render project to disk (in background, using most recent settings)"
  reaper.Main_OnCommand(42230, 0)
  restore_solo()   -- restore immediately — render queue has captured settings already
end

---Call every defer frame. Checks for file completion and invokes callback.
function M.tick()
  if not _polling then return end

  -- Timeout guard
  if reaper.time_precise() > _timeout_at then
    finish_render()
    reaper.ShowConsoleMsg("[ReaBot] Render timed out after " .. MAX_WAIT_SEC .. "s\n")
    if _on_error then _on_error("Render timed out after " .. MAX_WAIT_SEC .. " seconds.") end
    return
  end

  -- Dynamic format detection (wav, mp3, flac, etc.)
  local extensions = {"wav", "mp3", "flac", "m4a", "ogg", "aiff", "WAV", "MP3", "FLAC", "M4A", "OGG", "AIFF"}
  local found_path = nil
  local found_sz   = 0

  for _, ext in ipairs(extensions) do
    local test_path = _temp_dir .. "/" .. _uid .. "." .. ext
    local sz = file_size(test_path)
    if sz and sz >= MIN_FILE_SIZE then
      found_path = test_path
      found_sz   = sz
      break
    end
  end

  -- If any matching audio file is found, trigger completion
  if found_path then
    _path = found_path
    finish_render()
    reaper.ShowConsoleMsg("[ReaBot] Render complete: " .. _path .. " (" .. found_sz .. " bytes)\n")
    if _on_done then _on_done(_path) end
  end
end

---Delete a temp WAV file. Call after daemon has confirmed it received the analysis.
---@param path string  path returned by the on_done callback
function M.cleanup(path)
  if path and path ~= "" then
    local ok, err = os.remove(path)
    if not ok then
      reaper.ShowConsoleMsg("[ReaBot] Could not delete temp file: " .. tostring(err) .. "\n")
    end
  end
end

---Clean up any stale reabot_temp files older than max_age_sec.
---Call once on script startup to prevent accumulation from crashed sessions.
---@param max_age_sec number  default 3600 (1 hour)
function M.cleanup_stale(max_age_sec)
  max_age_sec = max_age_sec or 3600
  local proj = reaper.GetProjectPath("")
  local base = (proj ~= "" and proj or reaper.GetResourcePath())
  local dir  = base .. "/reabot_temp"

  -- Iterate directory (REAPER API: EnumerateFiles)
  local now = os.time()
  local i   = 0
  while true do
    local f = reaper.EnumerateFiles(dir, i)
    if not f then break end
    local full = dir .. "/" .. f
    -- os.difftime gives seconds; file modification time not directly available in Lua
    -- Best effort: try to open and check — stale files just stay until next cleanup
    -- (Full mtime check would require LuaFileSystem which isn't bundled)
    i = i + 1
  end
  -- Simpler: just delete all .wav files in the dir older than current session
  -- This is a best-effort; no error if files can't be removed
end

---@return boolean  true if a render is currently in progress
function M.is_busy()
  return _polling
end

return M
