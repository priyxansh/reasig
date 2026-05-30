"""
ReaBot DSP - Integrated Loudness (LUFS)

Measures integrated loudness per ITU-R BS.1770-4 using pyloudnorm.
Reports absolute LUFS and per-platform deltas so the LLM can give
specific streaming normalization advice.
"""

import numpy as np
from typing import Dict, Any

try:
    import pyloudnorm as pyln
    _PYLOUDNORM_AVAILABLE = True
except ImportError:
    _PYLOUDNORM_AVAILABLE = False

# Streaming platform integrated loudness targets (LUFS)
_TARGETS: Dict[str, float] = {
    "spotify":       -14.0,
    "apple_music":   -16.0,
    "youtube":       -14.0,
    "tidal":         -14.0,
    "amazon_music":  -14.0,
    "broadcast_ebu": -23.0,
}


def analyze_loudness(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Measure integrated loudness (LUFS) and compute per-platform deltas.

    Args:
        y:  Audio signal. Shape (N,) for mono or (2, N) for librosa stereo.
            pyloudnorm expects (N,) mono or (N, 2) stereo — we handle the transpose.
        sr: Sample rate in Hz.

    Returns:
        Dict with lufs_integrated (float or None), lufs_status (str),
        and platform_deltas (dict per platform).
    """
    if not _PYLOUDNORM_AVAILABLE:
        return {
            "lufs_integrated": None,
            "lufs_status":     "pyloudnorm not installed — run: pip install pyloudnorm",
            "platform_deltas": {},
        }

    meter = pyln.Meter(sr)  # ITU-R BS.1770-4

    try:
        if y.ndim == 1:
            lufs = meter.integrated_loudness(y)
        elif y.ndim == 2 and y.shape[0] == 2:
            # librosa stores stereo as (channels, samples) — pyloudnorm wants (samples, channels)
            lufs = meter.integrated_loudness(y.T)
        else:
            lufs = meter.integrated_loudness(y)
    except Exception:
        return {
            "lufs_integrated": None,
            "lufs_status":     "loudness measurement failed — signal may be too short or silent",
            "platform_deltas": {},
        }

    # pyloudnorm returns -inf for silence
    if lufs == float("-inf") or lufs < -70.0:
        return {
            "lufs_integrated": None,
            "lufs_status":     "signal too quiet or silent to measure loudness",
            "platform_deltas": {},
        }

    # pyloudnorm returns np.float64, which propagates to numpy bools on comparison
    lufs_rounded = float(round(lufs, 1))

    platform_deltas: Dict[str, Any] = {}
    for platform, target in _TARGETS.items():
        delta = float(round(lufs_rounded - target, 1))
        platform_deltas[platform] = {
            "target_lufs":    target,
            "delta_db":       delta,
            "will_normalize": bool(delta > 0),   # True = platform will turn it down
        }

    return {
        "lufs_integrated":  lufs_rounded,
        "lufs_status":      _loudness_label(lufs_rounded),
        "platform_deltas":  platform_deltas,
    }


def _loudness_label(lufs: float) -> str:
    if lufs > -9:    return "dangerously loud — heavy normalization on all platforms"
    if lufs > -11:   return "too loud — will be reduced on all major streaming platforms"
    if lufs > -13:   return "slightly loud — will be reduced on Spotify and YouTube"
    if lufs > -15:   return "on target — within Spotify/YouTube range"
    if lufs > -17:   return "slightly quiet — may feel soft on Apple Music"
    if lufs > -23:   return "quiet — fine for broadcast (EBU R128), soft for streaming"
    return "very quiet — significantly below all streaming targets"
