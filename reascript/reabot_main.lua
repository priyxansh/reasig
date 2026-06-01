--[[
  ReaBot — reabot_main.lua
  Entry point. REAPER loads this file from the action list.

  Responsibilities:
  - Set up Lua require() paths relative to this script's location
  - Initialize all modules
  - Wire callbacks between modules
  - Own and drive the main defer loop
--]]

-- ── Path setup (allows require() to find sibling modules) ──
-- reaper.get_action_context() returns: is_valid, filename, sectionID, cmdID, mode, resolution, val
local _script_path   = ({ reaper.get_action_context() })[2]
local _script_dir    = _script_path:match("(.*[/\\])")

package.path         = _script_dir .. "?.lua;"
    .. _script_dir .. "?/init.lua;"
    .. package.path

-- ── Locate and add Mavriq LuaSockets / Batteries ──
local resource_path  = reaper.GetResourcePath()
local is_windows     = reaper.GetOS():match("Win")
local sep            = is_windows and "\\" or "/"

-- Path to Sockets package
local sockets_path   = table.concat(
  { resource_path, "Scripts", "Mavriq ReaScript Repository", "Various", "Mavriq-Lua-Sockets", "" }, sep)
-- Path to Batteries package
local batteries_path = table.concat(
  { resource_path, "Scripts", "Mavriq ReaScript Repository", "Various", "Mavriq-Lua-Batteries", "" }, sep)

-- Sockets package paths
package.path         = package.path .. ";" .. sockets_path .. "?.lua"
package.cpath        = package.cpath ..
    ";" .. sockets_path .. "?.so;" .. sockets_path .. "?.dll;" .. sockets_path .. "?.dylib"

-- Batteries package paths (fallback/alternative)
package.path         = package.path .. ";" .. batteries_path .. "lua" .. sep .. "?.lua"
package.cpath        = package.cpath ..
    ";" ..
    batteries_path ..
    "bin" .. sep .. "?.so;" .. batteries_path .. "bin" .. sep .. "?.dll;" .. batteries_path .. "bin" .. sep .. "?.dylib"

-- ── Load modules ─────────────────────────────────────────────────────────
local socket         = require("bridge.socket_client")
local render         = require("render.stem_render")
local track          = require("extraction.track")
local ui             = require("ui.chat")

-- ── Initialize ─────────────────────────────────────────────────────────────
ui.init()

local REABOT_MODEL_DISPLAY = ""
ui.set_model(REABOT_MODEL_DISPLAY)

socket.connect()

-- Route all daemon messages through the UI handler
socket.on_message(function(msg)
  local t = msg.type
  local p = msg.payload or {}

  -- status_ok: grab model name and enable Chat if we have stored history
  if t == "status_ok" then
    if p.model and p.model ~= "" then
      ui.set_model(p.model)
    end
    if p.has_history then
      ui.set_has_analysis(true)
      local turns = p.history_turns or 0
      if turns > 0 then
        ui.set_status(string.format("Loaded %d previous turn%s", turns, turns == 1 and "" or "s"))
      end
    end
  end

  -- WAV cleanup: both response_done and analysis_result complete the flow
  if t == "response_done" or t == "analysis_result" or t == "error" then
    _current_request_id = nil
    if _pending_wav then
      render.cleanup(_pending_wav)
      _pending_wav = nil
    end
  end

  ui.on_daemon_message(msg)
end)

-- ── Pending WAV path and current request ID (for deferred cleanup/cancel) ──
_pending_wav = nil -- global so the on_message closure above can reach it
_current_request_id = nil

-- ── ID generator (lightweight, no UUID lib needed) ────────────────────────
local _id_counter = 0
local function make_id()
  _id_counter = _id_counter + 1
  return string.format("reabot-%08x-%04d", os.time(), _id_counter)
end

-- ── Analyze button handler ─────────────────────────────────────────────────
ui.on_analyze_click = function(prompt, stereo)
  -- Guard: reconnect if we fell off
  if not socket.is_connected() then
    socket.reconnect()
    ui.show_error("Reconnecting to daemon — please try again in a moment.")
    return
  end

  -- Guard: need at least one selected track
  local target_track = track.get_first_track_handle()
  if not target_track then
    ui.show_error("No track selected. Select a track in REAPER before clicking Analyze.")
    return
  end

  -- Guard: render not already running
  if render.is_busy() then
    ui.show_error("A render is already in progress. Please wait.")
    return
  end

  -- Read track metadata (includes FX chain nested inside)
  local meta, err = track.get_first_selected()
  if not meta then
    ui.show_error(err or "Could not read track metadata.")
    return
  end

  -- Show user's message immediately so it feels responsive
  ui.add_user_message(prompt)
  ui.set_status("Rendering...")

  -- Start async render — callback fires when WAV file is ready
  render.start(target_track, function(wav_path)
    -- WAV is ready — send analysis request to daemon
    _pending_wav = wav_path
    ui.set_status("Analyzing...")

    local req_id = make_id()
    _current_request_id = req_id
    socket.send({
      type    = "analyze_track",
      id      = req_id,
      payload = {
        wav_path       = wav_path,
        track_metadata = meta, -- fx_chain is nested inside meta
        user_question  = prompt,
        stereo         = stereo,
        project_path   = reaper.GetProjectPath("") or "",
      },
    })
  end, function(render_err)
    -- Render failed
    ui.show_error("Render failed: " .. render_err)
    ui.set_status("Ready")
  end)
end

-- ── Chat button handler (follow-up, no render) ────────────────────────────
ui.on_chat_click = function(prompt)
  if not socket.is_connected() then
    ui.show_error("Not connected to daemon. Start the daemon and try again.")
    return
  end

  ui.add_user_message(prompt)
  ui.set_status("Thinking...")

  local req_id = make_id()
  _current_request_id = req_id
  socket.send({
    type    = "chat",
    id      = req_id,
    payload = {
      user_message = prompt,
    },
  })
end

-- ── Startup: clean up stale temp files from previous sessions ────────────
render.cleanup_stale(3600)

-- ── Send an initial STATUS ping — includes project_path so the daemon can
--    load stored conversation history────
socket.send({
  type    = "status",
  id      = make_id(),
  payload = { project_path = reaper.GetProjectPath("") or "" },
})

-- ── Main defer loop ────────────────────────────────────────────────────────
local function loop()
  socket.tick()
  render.tick()

  -- Sync connection state to UI indicator every frame
  ui.set_connected(socket.is_connected())

  -- Draw UI — returns false when user clicks the X button
  local keep_open = ui.draw()
  if keep_open then
    reaper.defer(loop)
  else
    -- Window closed
    if _current_request_id and socket.is_connected() then
      socket.send({
        type    = "cancel",
        id      = make_id(),
        payload = { target_id = _current_request_id },
      })
      -- Tick once more to flush the send queue exiting
      socket.tick()
    end

    if _pending_wav then
      render.cleanup(_pending_wav)
      _pending_wav = nil
    end
    reaper.ShowConsoleMsg("[ReaBot] Window closed.\n")
  end
end

-- Kick off the loop
loop()
