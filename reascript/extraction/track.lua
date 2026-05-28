--[[
  ReaBot — extraction/track.lua
  Reads metadata and FX chain for the first selected track.
  FX chain is nested inside the returned table so the entire
  track_metadata dict can be sent as-is in the protocol payload.
--]]

local M = {}

-- ── Helpers ────────────────────────────────────────────────────────────────

local function lin_to_db(lin)
  if lin <= 0 then return -100.0 end
  -- math.log(x, base) available in Lua 5.2+; REAPER embeds 5.3
  return 20.0 * math.log(lin, 10)
end

local function round2(n)
  return math.floor(n * 100 + 0.5) / 100
end

-- ── FX chain (private) ─────────────────────────────────────────────────────

local function read_fx_chain(track)
  local chain     = {}
  local fx_count  = reaper.TrackFX_GetCount(track)

  for fi = 0, fx_count - 1 do
    local _, fx_name    = reaper.TrackFX_GetFXName(track, fi, "")
    local enabled        = reaper.TrackFX_GetEnabled(track, fi)
    local param_count    = reaper.TrackFX_GetNumParams(track, fi)
    local params         = {}

    -- Cap at 20 params per plugin to stay within token budget
    for pi = 0, math.min(param_count - 1, 19) do
      local _, pname      = reaper.TrackFX_GetParamName(track, fi, pi, "")
      local pvalue, _, _  = reaper.TrackFX_GetParam(track, fi, pi)
      local _, pdisplay   = reaper.TrackFX_GetFormattedParamValue(track, fi, pi, "")

      -- Skip unnamed or empty params (some plugins expose phantom params)
      if pname and pname ~= "" then
        table.insert(params, {
          name    = pname,
          value   = pvalue and round2(pvalue) or 0,
          display = pdisplay or "",
        })
      end
    end

    table.insert(chain, {
      index   = fi,
      name    = fx_name or ("FX " .. fi),
      enabled = enabled,
      params  = params,
    })
  end

  return chain
end

-- ── Public API ─────────────────────────────────────────────────────────────

---Returns track_metadata table for the first selected track, with fx_chain
---nested inside. Returns nil, error_message if nothing is selected.
---@return table|nil metadata
---@return string|nil error_message
function M.get_first_selected()
  local count = reaper.CountSelectedTracks(0)
  if count == 0 then
    return nil, "No track selected. Select at least one track before analyzing."
  end

  local track = reaper.GetSelectedTrack(0, 0)
  if not track then
    return nil, "Could not get selected track handle."
  end

  -- Track name — fall back to "Track N" for untitled tracks
  local _, name = reaper.GetTrackName(track, "", 512)
  local idx      = math.floor(reaper.GetMediaTrackInfo_Value(track, "IP_TRACKNUMBER"))
  if not name or name == "" then name = "Track " .. idx end

  -- Volume: linear → dBFS, clamped
  local vol_lin = reaper.GetMediaTrackInfo_Value(track, "D_VOL")
  local vol_db  = round2(lin_to_db(vol_lin))
  if vol_db < -100.0 then vol_db = -100.0 end

  -- Pan: -1.0 (full left) to +1.0 (full right)
  local pan = round2(reaper.GetMediaTrackInfo_Value(track, "D_PAN"))

  -- Mute / Solo
  local muted  = reaper.GetMediaTrackInfo_Value(track, "B_MUTE") == 1.0
  local solo_v = reaper.GetMediaTrackInfo_Value(track, "I_SOLO")
  local soloed = solo_v > 0

  -- Media items on track
  local item_count = reaper.CountTrackMediaItems(track)

  -- Project tempo / time sig
  local bpm, _, _ = reaper.GetProjectTimeSignature2(0)
  bpm = round2(bpm)

  -- Project / Audio device sample rate
  local ok, sr_str = reaper.GetAudioDeviceInfo("SRATE")
  local sr = ok and tonumber(sr_str) or 44100

  -- FX chain (nested here per the protocol design)
  local fx_chain = read_fx_chain(track)

  return {
    name         = name,
    index        = idx,
    volume_db    = vol_db,
    pan          = pan,
    muted        = muted,
    soloed       = soloed,
    item_count   = item_count,
    project_bpm  = bpm,
    project_sr   = sr,
    fx_chain     = fx_chain,   -- ← nested; always present (empty table if no FX)
  }, nil
end

---Returns how many tracks are currently selected (convenience for main script guard)
function M.count_selected()
  return reaper.CountSelectedTracks(0)
end

---Returns the MediaTrack* handle of the first selected track, or nil
function M.get_first_track_handle()
  if reaper.CountSelectedTracks(0) == 0 then return nil end
  return reaper.GetSelectedTrack(0, 0)
end

return M
