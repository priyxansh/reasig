"""
ReaBot - FX Chain Extraction

Reads all plugins and their parameters from every selected track's FX chain.
Runs inside the ReaScript environment.

Raw parameter values from REAPER are floats. The interpreter converts them
to human-readable strings for each known Cockos plugin. Unknown plugins
pass through with the raw value and a note that units are unverified.
"""

from typing import Callable

from reaper_python import (
    RPR_CountSelectedTracks,
    RPR_GetSelectedTrack,
    RPR_GetSetMediaTrackInfo_String,
    RPR_GetMediaTrackInfo_Value,
    RPR_TrackFX_GetCount,
    RPR_TrackFX_GetFXName,
    RPR_TrackFX_GetNumParams,
    RPR_TrackFX_GetParamName,
    RPR_TrackFX_GetParam,
    RPR_TrackFX_GetEnabled,
)


# ---------------------------------------------------------------------------
# Parameter interpretation table for known Cockos plugins.
# Maps plugin name fragment -> param name fragment -> formatter function.
# ---------------------------------------------------------------------------

def _fmt_db(v, mn, mx): return f"{v:.1f} dB"
def _fmt_hz(v, mn, mx): return f"{int(v)} Hz" if v >= 1 else f"{v:.1f} Hz"
def _fmt_ratio(v, mn, mx): return f"{v:.1f}:1"
def _fmt_ms(v, mn, mx): return f"{v:.1f} ms"
def _fmt_pct(v, mn, mx): return f"{v:.0f}%"


_PLUGIN_PARAM_MAP: dict[str, dict[str, Callable]] = {
    "reaeq": {
        "freq": _fmt_hz,
        "gain": _fmt_db,
        "bw":   _fmt_pct,   # bandwidth in octaves — REAPER shows this differently but pct is close enough
    },
    "reacomp": {
        "threshold": _fmt_db,
        "ratio":     _fmt_ratio,
        "attack":    _fmt_ms,
        "release":   _fmt_ms,
        "makeup":    _fmt_db,
        "dry":       _fmt_db,
        "wet":       _fmt_db,
    },
    "reagate": {
        "threshold": _fmt_db,
        "attack":    _fmt_ms,
        "release":   _fmt_ms,
        "hold":      _fmt_ms,
        "hysteresis": _fmt_db,
        "lookahead": _fmt_ms,
    },
    "realimit": {
        "threshold":  _fmt_db,
        "ceiling":    _fmt_db,
        "release":    _fmt_ms,
    },
    "reaxcomp": {
        "threshold": _fmt_db,
        "ratio":     _fmt_ratio,
        "attack":    _fmt_ms,
        "release":   _fmt_ms,
        "makeup":    _fmt_db,
    },
}


def _interpret_param(plugin_name: str, param_name: str, value: float, min_val: float, max_val: float) -> str:
    """
    Convert a raw parameter float to a display string.
    Falls back to raw value if the plugin/param combination is not in the map.
    """
    plugin_lower = plugin_name.lower()
    param_lower = param_name.lower()

    for plugin_key, param_map in _PLUGIN_PARAM_MAP.items():
        if plugin_key in plugin_lower:
            for param_key, formatter in param_map.items():
                if param_key in param_lower:
                    try:
                        return formatter(value, min_val, max_val)
                    except Exception:
                        break
            # Plugin recognised but param not — still label the value
            return f"{value:.3g} (units unknown)"

    # Completely unknown plugin
    return f"{value:.3g} (units unverified)"


# ---------------------------------------------------------------------------

def get_fx_chain(track) -> list[dict]:
    """
    Return the full FX chain for a single track object.

    Args:
        track: REAPER track MediaTrack pointer.

    Returns:
        List of plugin dicts, each with name, enabled status, and parameters.
    """
    fx_count = RPR_TrackFX_GetCount(track)
    chain = []

    for fx_idx in range(fx_count):
        # Plugin name
        _, _, _, fx_name, _ = RPR_TrackFX_GetFXName(track, fx_idx, "", 256)

        # Enabled state
        enabled = RPR_TrackFX_GetEnabled(track, fx_idx)

        # Parameters
        param_count = RPR_TrackFX_GetNumParams(track, fx_idx)
        parameters = []

        for p_idx in range(param_count):
            # Param name
            _, _, _, _, param_name, _ = RPR_TrackFX_GetParamName(track, fx_idx, p_idx, "", 256)
            # Value and range
            value, min_val, max_val = RPR_TrackFX_GetParam(track, fx_idx, p_idx, 0.0, 0.0)

            display = _interpret_param(fx_name, param_name, value, min_val, max_val)

            parameters.append({
                "index": p_idx,
                "name": param_name,
                "value": round(value, 4),
                "min": round(min_val, 4),
                "max": round(max_val, 4),
                "display": display,
            })

        chain.append({
            "index": fx_idx,
            "name": fx_name,
            "enabled": bool(enabled),
            "parameters": parameters,
        })

    return chain


def get_selected_tracks_fx() -> list[dict]:
    """
    Return FX chain data for all selected tracks.

    Returns:
        List of dicts, one per selected track, each with track name and fx_chain.
    """
    count = RPR_CountSelectedTracks(0)
    result = []

    for i in range(count):
        track = RPR_GetSelectedTrack(0, i)
        if not track:
            continue

        _, _, name, _, _ = RPR_GetSetMediaTrackInfo_String(track, "P_NAME", "", False)
        track_index = int(RPR_GetMediaTrackInfo_Value(track, "IP_TRACKNUMBER"))

        result.append({
            "track_name": name if name else f"Track {track_index}",
            "track_index": track_index,
            "fx_chain": get_fx_chain(track),
        })

    return result
