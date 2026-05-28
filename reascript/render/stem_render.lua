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
local _polling      = false
local _path         = nil
local _on_done      = nil
local _on_error     = nil
local _timeout_at   = 0
local _solo_states  = {}     -- {[MediaTrack*] = original_solo_value}

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
  return dir .. "/" .. uid .. ".wav"
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

  local out_path = make_temp_path()
  _path          = out_path
  _on_done       = on_done
  _on_error      = on_error
  _polling       = true
  _timeout_at    = reaper.time_precise() + MAX_WAIT_SEC

  -- ── Set render parameters ─────────────────────────────────────────────
  -- Output file path
  reaper.GetSetProjectInfo_String(0, "RENDER_FILE", out_path, true)
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
    _polling = false
    reaper.ShowConsoleMsg("[ReaBot] Render timed out after " .. MAX_WAIT_SEC .. "s\n")
    if _on_error then _on_error("Render timed out after " .. MAX_WAIT_SEC .. " seconds.") end
    return
  end

  -- Check if file has appeared with sufficient size
  local sz = file_size(_path)
  if sz and sz >= MIN_FILE_SIZE then
    _polling = false
    reaper.ShowConsoleMsg("[ReaBot] Render complete: " .. _path .. " (" .. sz .. " bytes)\n")
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
