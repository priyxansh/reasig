"""
ReaBot DSP - Dynamics Analysis

Analyzes RMS, Peak, Crest Factor, and clipping of the audio signal.
Clipping detection is always included alongside dynamics since digital
distortion is a universal concern regardless of the user's question.
"""

import numpy as np
from typing import Dict, Any


def detect_clipping(y: np.ndarray) -> Dict[str, Any]:
    """
    Count samples at or near 0 dBFS (full scale).

    The threshold of 0.999 catches both true clipping and inter-sample
    peaks that would clip on a 16-bit export even if the float peak reads
    slightly below 1.0.
    """
    CLIP_THRESHOLD = 0.999
    abs_y           = np.abs(y)
    clipped_samples = int(np.sum(abs_y >= CLIP_THRESHOLD))
    total_samples   = len(y) if len(y) > 0 else 1
    clip_ratio      = clipped_samples / total_samples

    if clipped_samples == 0:
        severity = "none"
    elif clip_ratio < 0.0001:
        severity = "minor — occasional peaks, likely inaudible"
    elif clip_ratio < 0.001:
        severity = "moderate — audible distortion on transients"
    elif clip_ratio < 0.01:
        severity = "significant — clear clipping distortion"
    else:
        severity = "severe — heavy clipping throughout, needs gain reduction"

    true_peak = float(np.max(abs_y)) if len(abs_y) > 0 else 0.0
    true_peak_dbfs = float(20 * np.log10(true_peak + 1e-10))

    return {
        "clipped_samples": clipped_samples,
        "clip_ratio_pct":  round(clip_ratio * 100, 4),
        "clip_severity":   severity,
        "true_peak_dbfs":  round(true_peak_dbfs, 2),
    }


def analyze_dynamics(y: np.ndarray) -> Dict[str, Any]:
    """
    Perform dynamics analysis on the audio signal.

    Returns:
        Dict containing RMS, Peak, Crest Factor (all in dB/dBFS)
        plus clipping detection results merged in.
    """
    # Prevent log10(0)
    safe_y = np.where(y == 0, 1e-10, y)

    rms  = float(np.sqrt(np.mean(safe_y ** 2)))
    peak = float(np.max(np.abs(safe_y)))

    rms_db  = float(20 * np.log10(rms))  if rms  > 0 else -100.0
    peak_db = float(20 * np.log10(peak)) if peak > 0 else -100.0

    # Crest factor: dynamic headroom between peak and RMS
    crest_factor_db = peak_db - rms_db

    result = {
        "rms_db":           round(rms_db, 2),
        "peak_db":          round(peak_db, 2),
        "crest_factor_db":  round(crest_factor_db, 2),
    }

    # Always include clipping data — relevant for every analysis
    result.update(detect_clipping(y))
    return result

