"""
ReaBot DSP - Reverb Tail Estimation (RT60)

Estimates RT60 (time for energy to decay 60 dB) using the Schroeder
backward integration method. Most reliable on percussive sounds with
a clear transient followed by a decay tail (snare, kick, clap, room tone).
Less reliable on continuous tonal sources or dense mixes.
"""

import numpy as np
from typing import Dict, Any


def estimate_reverb_tail(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Estimate RT60 via Schroeder backward integration of the energy decay curve.
    Uses the RT20 range (-5 dB to -25 dB) extrapolated to RT60.

    Args:
        y:  Mono audio array, shape (N,).
        sr: Sample rate in Hz.

    Returns:
        Dict with rt60_seconds (float or None) and reverb_label (str).
    """
    min_samples = int(0.5 * sr)
    if len(y) < min_samples:
        return {
            "rt60_seconds": None,
            "reverb_label": "clip too short to estimate reverb tail",
        }

    # Energy Decay Curve via Schroeder backward integration
    y_sq  = y ** 2
    edc   = np.cumsum(y_sq[::-1])[::-1]
    max_e = float(np.max(edc))

    if max_e < 1e-12:
        return {
            "rt60_seconds": None,
            "reverb_label": "silence — cannot estimate reverb",
        }

    edc_db = 10.0 * np.log10(edc / max_e + 1e-12)
    t      = np.arange(len(edc_db)) / float(sr)

    try:
        # Find time points where EDC crosses -5 dB and -25 dB
        idx_5db  = np.where(edc_db <= -5.0)[0]
        idx_25db = np.where(edc_db <= -25.0)[0]

        if len(idx_5db) == 0 or len(idx_25db) == 0:
            raise IndexError("signal does not decay far enough")

        rt20 = float(t[idx_25db[0]] - t[idx_5db[0]])
        if rt20 <= 0.0:
            raise ValueError("non-positive RT20")

        rt60 = round(rt20 * 3.0, 3)
    except (IndexError, ValueError):
        # Signal doesn't have sufficient decay range — likely continuous or very wet
        return {
            "rt60_seconds": None,
            "reverb_label": "reverb tail extends beyond measurement window — very long decay or continuous signal",
        }

    return {
        "rt60_seconds": rt60,
        "reverb_label": _reverb_label(rt60),
    }


def _reverb_label(rt60: float) -> str:
    if rt60 < 0.15:   return "very tight/dry — negligible reverb"
    if rt60 < 0.40:   return "tight — natural room presence"
    if rt60 < 0.80:   return "moderate reverb — audible but controlled"
    if rt60 < 1.50:   return "long reverb — may smear transients in busy mixes"
    if rt60 < 3.00:   return "very long reverb — will wash out detail in dense arrangements"
    return "extremely long reverb — will cause serious mix clarity issues"
