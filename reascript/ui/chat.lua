--[[
  ReaBot — ui/chat.lua
  Main ReaImGui chat window.

  Rules for ImGui safety (prevents all pointer/stack errors):
    1. ImGui_End()      is called OUTSIDE `if visible then` — always runs if Begin ran.
    2. ImGui_EndChild() is called OUTSIDE `if ok then`      — always runs after BeginChild.
    3. PushStyleColor / PushStyleVar are always paired with a matching Pop.
    4. ctx is created ONCE in M.init() and never recreated.

  Callbacks wired by reabot_main.lua:
    M.on_analyze_click = function(prompt, stereo_bool)
    M.on_chat_click    = function(prompt)
--]]

local M               = {}

local json            = require("lib/dkjson")

-- ── State ──────────────────────────────────────────────────────────────────
local _ctx            = nil
local _messages       = {}  -- { role = "user"|"bot"|"err"|"bot_analysis", text|data = ... }
local _input_text     = ""
local _status_text    = "Ready"
local _stereo_enabled = false
local _scroll_to_bot  = false
local _is_connected   = false
local _streaming_idx  = nil              -- index into _messages for active stream
local _has_analysis   = false            -- true after first successful Analyze completes
local _model_name     = "unknown model"  -- shown in UI; set by reabot_main.lua via M.set_model()

-- Public callbacks — set by reabot_main.lua
M.on_analyze_click    = nil
M.on_chat_click       = nil

-- ── ImGui colour constants ─────────────────────────────────────────────────
local COL_GREEN       = 0x44FF88FF
local COL_RED         = 0xFF4444FF
local COL_USER        = 0xAADDFFFF -- soft blue
local COL_BOT         = 0xCCFFCCFF -- soft green
local COL_ERR         = 0xFF7777FF -- soft red
local COL_DIM         = 0x888888FF -- grey for labels

-- ── Public API ─────────────────────────────────────────────────────────────

---Create the ImGui context. Call ONCE before the first draw().
function M.init()
  _ctx = reaper.ImGui_CreateContext("ReaBot")
end

---Update the status bar text.
---@param text string
function M.set_status(text)
  _status_text = text
end

---Update the connection indicator.
---@param connected boolean
function M.set_connected(connected)
  _is_connected = connected
end

---Signal that analysis context is available so the Chat button is enabled.
---Called by reabot_main.lua when the daemon reports has_history on startup
---or when an Analyze/Chat response completes.
---@param value boolean
function M.set_has_analysis(value)
  _has_analysis = value
end

---Set the model name shown in the header.
---@param name string
function M.set_model(name)
  _model_name = name or "unknown model"
end

---Programmatically clear the chat (e.g. when user clicks the Clear button or
---the main script wants to reset state on project switch).
function M.clear_chat()
  _messages      = {}
  _streaming_idx = nil
  _has_analysis  = false
  _status_text   = "Ready"
end

---Add a user message to the chat history.
---@param text string
function M.add_user_message(text)
  table.insert(_messages, { role = "user", text = text })
  _scroll_to_bot = true
end

---Add an error message to the chat history and reset status.
---@param text string
function M.show_error(text)
  table.insert(_messages, { role = "err", text = text })
  _status_text = "Ready"
  _scroll_to_bot = true
end

---Called by socket_client.on_message — routes incoming daemon messages to UI state.
---@param msg table  decoded JSON message from daemon
function M.on_daemon_message(msg)
  if not msg or not msg.type then return end
  local t = msg.type
  local p = msg.payload or {}

  if t == "response_chunk" then
    -- Streaming token: append to current (or new) bot message
    local delta = p.content or ""
    if _streaming_idx == nil then
      table.insert(_messages, { role = "bot", text = "" })
      _streaming_idx = #_messages
    end
    _messages[_streaming_idx].text = _messages[_streaming_idx].text .. delta
    _scroll_to_bot = true
  elseif t == "analysis_result" then
    -- LLM not wired yet — display formatted analysis with section labels
    table.insert(_messages, { role = "bot_analysis", data = p.analysis or {} })
    _status_text   = "Ready"
    _scroll_to_bot = true
    _has_analysis  = true -- unlock Chat button
  elseif t == "response_done" then
    _streaming_idx = nil
    _status_text   = "Ready"
    _has_analysis  = true -- unlock Chat button (LLM responded using analysis)
  elseif t == "status_ok" then
    _is_connected = true
  elseif t == "error" then
    local err_text = p.error or "Unknown error from daemon"
    M.show_error(err_text)
  end
end

---Draw the window. Returns false when the user closes it (caller should stop defer loop).
---@return boolean  true = keep running, false = window closed
function M.draw()
  if not _ctx then return false end

  -- Window flags: no saved settings for position/size on first launch
  local window_flags = 0

  local count = reaper.CountSelectedTracks(0)
  local title = string.format("ReaBot — %s  |  %d track%s###ReaBot",
    _model_name,
    count,
    count == 1 and "" or "s"
  )
  local visible, open = reaper.ImGui_Begin(_ctx, title, true, window_flags)

  -- !! SAFETY: ImGui_End must be called unconditionally if Begin was called !!
  if visible then
    _draw_header()
    _draw_chat_history()
    _draw_status_bar()
    _draw_input_row()
  end
  reaper.ImGui_End(_ctx) -- always — even when visible=false (minimised, etc.)

  if not open then
    return false -- user clicked the X button
  end
  return true
end

-- ── Private draw helpers ───────────────────────────────────────────────────

function _draw_header()
  -- Title
  reaper.ImGui_Text(_ctx, "ReaBot")
  reaper.ImGui_SameLine(_ctx)

  -- Connection status dot
  local dot_col  = _is_connected and COL_GREEN or COL_RED
  local dot_text = _is_connected and "●  Connected" or "●  Disconnected"
  reaper.ImGui_PushStyleColor(_ctx, reaper.ImGui_Col_Text(), dot_col)
  reaper.ImGui_Text(_ctx, dot_text)
  reaper.ImGui_PopStyleColor(_ctx, 1)

  -- Right-align Clear button
  local avail = reaper.ImGui_GetContentRegionAvail(_ctx)
  reaper.ImGui_SameLine(_ctx, avail - 40)
  if reaper.ImGui_SmallButton(_ctx, "Clear") then
    M.clear_chat()
  end

  reaper.ImGui_Separator(_ctx)
end

function _draw_chat_history()
  -- Reserve ~85px at the bottom for status + input rows
  local child_height = -85

  -- BeginChild returns bool; EndChild must always be called regardless
  local child_ok = reaper.ImGui_BeginChild(_ctx, "##chat_history", 0, child_height, 0)

  if child_ok then
    for idx, msg in ipairs(_messages) do
      local color, prefix
      if msg.role == "user" then
        color  = COL_USER
        prefix = "You  ▸  "
      elseif msg.role == "bot" then
        color  = COL_BOT
        prefix = "Bot  ▸  "
      elseif msg.role == "bot_analysis" then
        color  = COL_BOT
        prefix = "Bot  ▸  "
      else
        color  = COL_ERR
        prefix = "Err  ▸  "
      end

      if msg.role == "bot_analysis" then
        reaper.ImGui_PushStyleColor(_ctx, reaper.ImGui_Col_Text(), color)
        reaper.ImGui_TextWrapped(_ctx, prefix .. "[Analysis Complete]")
        reaper.ImGui_PopStyleColor(_ctx, 1)
        _draw_analysis_result(msg.data)
      else
        if msg.role == "bot" and idx == _streaming_idx and msg.text == "" then
          local t = math.floor(reaper.time_precise() * 3) % 3
          local dots = string.rep(".", t + 1)
          reaper.ImGui_PushStyleColor(_ctx, reaper.ImGui_Col_Text(), COL_DIM)
          reaper.ImGui_Text(_ctx, "Bot  ▸  Thinking" .. dots)
          reaper.ImGui_PopStyleColor(_ctx, 1)
        else
          reaper.ImGui_PushStyleColor(_ctx, reaper.ImGui_Col_Text(), color)
          reaper.ImGui_TextWrapped(_ctx, prefix .. msg.text)
          reaper.ImGui_PopStyleColor(_ctx, 1)
        end
      end
      reaper.ImGui_Spacing(_ctx)
    end

    -- Auto-scroll to bottom when new messages arrive
    if _scroll_to_bot then
      reaper.ImGui_SetScrollHereY(_ctx, 1.0)
      _scroll_to_bot = false
    end
  end

  -- !! SAFETY: EndChild must be called unconditionally after BeginChild !!
  reaper.ImGui_EndChild(_ctx)
end

function _draw_status_bar()
  reaper.ImGui_Separator(_ctx)

  -- Stereo checkbox
  local changed
  changed, _stereo_enabled = reaper.ImGui_Checkbox(_ctx, "Stereo", _stereo_enabled)

  reaper.ImGui_SameLine(_ctx)

  -- Status text (dimmed colour)
  reaper.ImGui_PushStyleColor(_ctx, reaper.ImGui_Col_Text(), COL_DIM)
  reaper.ImGui_Text(_ctx, _status_text)
  reaper.ImGui_PopStyleColor(_ctx, 1)
end

function _draw_input_row()
  reaper.ImGui_Separator(_ctx)

  -- Input text — stretches to fill available width minus button space (~140px)
  reaper.ImGui_SetNextItemWidth(_ctx, -140)
  local changed, new_text = reaper.ImGui_InputText(
    _ctx, "##prompt", _input_text, 2048
  )
  if changed then _input_text = new_text end

  if reaper.ImGui_IsItemFocused(_ctx) then
    local enter = reaper.ImGui_IsKeyPressed(_ctx, reaper.ImGui_Key_Enter())
    local shift = reaper.ImGui_IsKeyDown(_ctx, reaper.ImGui_Key_LeftShift())
        or reaper.ImGui_IsKeyDown(_ctx, reaper.ImGui_Key_RightShift())
    if enter and shift then
      _trigger_chat()
    elseif enter then
      _trigger_analyze()
    end
  end

  if reaper.ImGui_IsItemHovered(_ctx) then
    reaper.ImGui_SetTooltip(_ctx, "Enter → Analyze  |  Shift+Enter → Chat")
  end

  reaper.ImGui_SameLine(_ctx)

  local n = reaper.CountSelectedTracks(0)
  local analyze_label = (n <= 1) and "Analyze" or ("Analyze " .. n)
  if reaper.ImGui_Button(_ctx, analyze_label, 65, 0) then
    _trigger_analyze()
  end

  reaper.ImGui_SameLine(_ctx)

  -- Chat button: disabled (and greyed) until at least one analysis has run
  if not _has_analysis then
    reaper.ImGui_BeginDisabled(_ctx)
  end
  if reaper.ImGui_Button(_ctx, "Chat", 60, 0) then
    _trigger_chat()
  end
  if not _has_analysis then
    reaper.ImGui_EndDisabled(_ctx)
    if reaper.ImGui_IsItemHovered(_ctx) then
      reaper.ImGui_SetTooltip(_ctx, "Run Analyze first to give the AI data to work with.")
    end
  end
end

-- ── Private trigger helpers ────────────────────────────────────────────────

function _trigger_analyze()
  local prompt = _input_text:match("^%s*(.-)%s*$") -- trim
  if prompt == "" then return end
  if M.on_analyze_click then
    M.on_analyze_click(prompt, _stereo_enabled)
    -- Don't clear input here — user may want to refine prompt
  end
end

function _trigger_chat()
  local prompt = _input_text:match("^%s*(.-)%s*$")
  if prompt == "" then return end
  if M.on_chat_click then
    M.on_chat_click(prompt)
  end
end

-- ── Analysis formatter (Phase 3 display — replaced by LLM in Phase 4) ────

local function _draw_section_label(label)
  reaper.ImGui_PushStyleColor(_ctx, reaper.ImGui_Col_Text(), COL_DIM)
  reaper.ImGui_Text(_ctx, label)
  reaper.ImGui_PopStyleColor(_ctx, 1)
  reaper.ImGui_SameLine(_ctx)
end

local function _draw_value(val)
  reaper.ImGui_PushStyleColor(_ctx, reaper.ImGui_Col_Text(), COL_BOT)
  reaper.ImGui_TextWrapped(_ctx, val)
  reaper.ImGui_PopStyleColor(_ctx, 1)
end

function _draw_analysis_result(analysis)
  if not analysis or next(analysis) == nil then
    _draw_value("(no analysis data received)")
    return
  end

  -- Spectral
  if analysis.spectral_centroid_hz then
    _draw_section_label("[SPECTRAL]")
    _draw_value(string.format("Centroid: %.0f Hz  |  Bandwidth: %.0f Hz  |  Rolloff: %.0f Hz",
      analysis.spectral_centroid_hz or 0,
      analysis.spectral_bandwidth_hz or 0,
      analysis.spectral_rolloff_hz or 0))
  end

  if analysis.band_energy then
    local b = analysis.band_energy
    _draw_section_label("[BANDS]")
    _draw_value(string.format("Sub: %.1f%%  Low: %.1f%%  Lo-Mid: %.1f%%  Mid: %.1f%%  Hi-Mid: %.1f%%  High: %.1f%%",
      (b.sub_20_60 or 0) * 100,
      (b.low_60_200 or 0) * 100,
      (b.low_mid_200_500 or 0) * 100,
      (b.mid_500_2k or 0) * 100,
      (b.upper_mid_2k_5k or 0) * 100,
      (b.high_5k_10k or 0) * 100))
  end

  -- Tonal flags
  if analysis.tonal_balance then
    local tb    = analysis.tonal_balance
    local flags = {}
    if tb.muddiness then table.insert(flags, "MUDDY") end
    if tb.harshness then table.insert(flags, "HARSH") end
    if tb.boxiness then table.insert(flags, "BOXY") end
    if tb.rumble then table.insert(flags, "RUMBLE") end
    local label = (#flags > 0) and table.concat(flags, ", ") or "none"
    _draw_section_label("[TONAL]")
    _draw_value("Flags: " .. label)
  end

  -- Dynamics
  if analysis.rms_db then
    local clip_str = ""
    if analysis.clip_severity and analysis.clip_severity ~= "none" then
      clip_str = "  |  CLIP: " .. (analysis.clip_severity:match("^(.-) %—") or analysis.clip_severity)
    end
    _draw_section_label("[DYNAMICS]")
    _draw_value(string.format("RMS: %.1f dBFS  |  Peak: %.1f dBFS  |  Crest: %.1f dB%s",
      analysis.rms_db or 0,
      analysis.peak_db or 0,
      analysis.crest_factor_db or 0,
      clip_str))
  end

  -- Transients
  if analysis.transients then
    local t = analysis.transients
    _draw_section_label("[TRANSIENTS]")
    _draw_value(string.format("Density: %s  |  %s per sec  |  Att/Dec: %sms / %sms",
      t.density or "?",
      t.onsets_per_second or "?",
      t.avg_attack_ms or "?",
      t.avg_decay_ms or "?"))
  end

  -- Musical
  if analysis.musical then
    _draw_section_label("[MUSICAL]")
    _draw_value(string.format("BPM: %.1f  |  Key: %s",
      analysis.musical.bpm or 0,
      analysis.musical.key or "?"))
  end

  -- Spectral Balance vs Target Curve
  if analysis.overall_balance_score then
    _draw_section_label("[BALANCE]")
    _draw_value(string.format("Score: %.1f (%s)",
      analysis.overall_balance_score,
      analysis.overall_balance_label or "?"))
  end

  -- Loudness
  if analysis.loudness and analysis.loudness.lufs_integrated then
    _draw_section_label("[LOUDNESS]")
    _draw_value(string.format("%.1f LUFS (%s)",
      analysis.loudness.lufs_integrated,
      analysis.loudness.lufs_status or "?"))
  end

  -- Noise Floor
  if analysis.noise and analysis.noise.noise_floor_db then
    _draw_section_label("[NOISE]")
    _draw_value(string.format("Floor: %.1f dBFS  |  SNR: %.1f dB (%s)",
      analysis.noise.noise_floor_db,
      analysis.noise.snr_db or 0,
      analysis.noise.noise_label or "?"))
  end

  -- Reverb
  if analysis.reverb and analysis.reverb.rt60_seconds then
    _draw_section_label("[REVERB]")
    _draw_value(string.format("RT60: %.2fs (%s)",
      analysis.reverb.rt60_seconds,
      analysis.reverb.reverb_label or "?"))
  end

  -- Distortion
  if analysis.distortion and analysis.distortion.thd_ratio then
    _draw_section_label("[DISTORTION]")
    _draw_value(string.format("THD: %.2f%% @ %.0fHz (%s)",
      analysis.distortion.thd_ratio * 100,
      analysis.distortion.fundamental_hz or 0,
      analysis.distortion.thd_label or "?"))
  end

  -- Stereo (if requested)
  if analysis.stereo then
    local s = analysis.stereo
    local interp = s.interpretation or {}
    _draw_section_label("[STEREO]")
    _draw_value(string.format("Width: %.3f (%s)  |  Mono compat: %.3f  |  LR: %s",
      s.stereo_width or 0,
      interp.width_label or "?",
      s.mono_compatibility_score or 0,
      interp.balance_label or "?"))
  end
end

return M
