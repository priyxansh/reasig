"""
ReaBot - Track Metadata Extraction

Reads metadata for all currently selected tracks in REAPER.
Runs inside the ReaScript environment (REAPER's main thread).

Returns a list of dicts, one per selected track.
"""

from reaper_python import (
    RPR_CountSelectedTracks,
    RPR_GetSelectedTrack,
    RPR_GetSetMediaTrackInfo_String,
    RPR_GetMediaTrackInfo_Value,
    RPR_GetNumTracks,
    RPR_GetProjectTimeSignature2,
    RPR_GetAudioDeviceInfo,
    RPR_GetProjectPath,
    RPR_CountTrackMediaItems,
    RPR_GetTrackColor,
)


def _vol_to_db(vol: float) -> float:
    """Convert a linear volume value (0.0-4.0+) to dBFS."""
    import math
    if vol <= 0:
        return -150.0
    return 20.0 * math.log10(vol)


def _pan_to_str(pan: float) -> str:
    """Convert pan float (-1.0 to +1.0) to a human-readable string."""
    if abs(pan) < 0.01:
        return "Center"
    side = "L" if pan < 0 else "R"
    pct = int(abs(pan) * 100)
    return f"{pct}% {side}"


def get_selected_tracks() -> list[dict]:
    """
    Return a list of metadata dicts for every currently selected track.

    Returns an empty list if no tracks are selected.
    """
    count = RPR_CountSelectedTracks(0)
    if count == 0:
        return []

    tracks = []
    for i in range(count):
        track = RPR_GetSelectedTrack(0, i)
        if not track:
            continue

        # Track name
        _, _, name, _, _ = RPR_GetSetMediaTrackInfo_String(track, "P_NAME", "", False)

        # Index (1-based for display, REAPER uses 0-based internally)
        track_index = int(RPR_GetMediaTrackInfo_Value(track, "IP_TRACKNUMBER"))

        # Volume and pan
        vol_linear = RPR_GetMediaTrackInfo_Value(track, "D_VOL")
        pan = RPR_GetMediaTrackInfo_Value(track, "D_PAN")
        vol_db = round(_vol_to_db(vol_linear), 1)

        # Mute / Solo
        muted = bool(RPR_GetMediaTrackInfo_Value(track, "B_MUTE"))
        soloed = bool(RPR_GetMediaTrackInfo_Value(track, "I_SOLO"))

        # Number of media items
        item_count = RPR_CountTrackMediaItems(track)

        # Track color (raw integer from REAPER, 0 = default/no color)
        color = RPR_GetTrackColor(track)

        tracks.append({
            "name": name if name else f"Track {track_index}",
            "index": track_index,
            "volume_db": vol_db,
            "pan": round(pan, 3),
            "pan_display": _pan_to_str(pan),
            "muted": muted,
            "soloed": soloed,
            "item_count": item_count,
            "color": color,
        })

    return tracks


def get_project_info() -> dict:
    """
    Return project-level metadata: BPM, time signature, sample rate.
    """
    # BPM and time signature
    _, bpm, num, denom = RPR_GetProjectTimeSignature2(0.0, 0, 0)

    # Sample rate (via audio device info)
    _, _, srate, _ = RPR_GetAudioDeviceInfo("SRATE", "", 32)
    try:
        sample_rate = int(srate)
    except (ValueError, TypeError):
        sample_rate = 44100

    # Project path (so we can write temp files next to it)
    _, path, _ = RPR_GetProjectPath("", 512)

    return {
        "bpm": round(bpm, 2),
        "time_sig_numerator": num,
        "time_sig_denominator": denom,
        "sample_rate": sample_rate,
        "project_path": path,
    }


def get_track_context() -> dict:
    """
    Convenience wrapper: returns both selected track data and project info
    in a single dict ready to be sent to the daemon as track_metadata.
    """
    selected = get_selected_tracks()
    project = get_project_info()

    return {
        "selected_tracks": selected,
        "track_count": len(selected),
        "project": project,
    }
