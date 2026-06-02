"""
ReaSig DSP - Noise Floor & Signal-to-Noise Ratio

Estimates the noise floor by finding the quietest 500ms windows in the
signal. Works best on recordings with silent passages between notes/phrases
(vocals, guitars, recorded instruments). Less meaningful for synths that
sustain continuously.
"""

import numpy as np
from typing import Dict, Any


def analyze_noise_floor(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Estimate noise floor dBFS and SNR by analysing the quietest 10% of 500ms windows.

    Args:
        y:  Mono audio array, shape (N,).
        sr: Sample rate in Hz.

    Returns:
        Dict with noise_floor_db, snr_db, noise_label.
    """
    window_samples = int(0.5 * sr)   # 500ms per window
    num_windows    = len(y) // window_samples

    if num_windows < 2:
        return {
            "noise_floor_db": None,
            "snr_db":         None,
            "noise_label":    "clip too short to estimate noise floor — need at least 1 second",
        }

    # RMS per window
    window_rms = []
    for i in range(num_windows):
        chunk = y[i * window_samples : (i + 1) * window_samples]
        rms   = float(np.sqrt(np.mean(chunk ** 2) + 1e-12))
        window_rms.append(rms)

    window_rms_sorted = sorted(window_rms)

    # Noise floor = mean RMS of the quietest 10% of windows (minimum 1)
    quiet_count   = max(1, num_windows // 10)
    quiet_windows = window_rms_sorted[:quiet_count]
    noise_rms     = float(np.mean(quiet_windows))
    signal_rms    = float(np.sqrt(np.mean(y ** 2) + 1e-12))

    if noise_rms < 1e-10:
        return {
            "noise_floor_db": -100.0,
            "snr_db":         100.0,
            "noise_label":    "excellent — inaudible noise floor",
        }

    noise_floor_db = float(20 * np.log10(noise_rms))
    snr_db         = float(20 * np.log10(signal_rms / noise_rms))

    return {
        "noise_floor_db": round(noise_floor_db, 1),
        "snr_db":         round(snr_db, 1),
        "noise_label":    _noise_label(noise_floor_db, snr_db),
    }


def _noise_label(floor: float, snr: float) -> str:
    if floor < -80:   return "excellent — inaudible noise floor"
    if floor < -70:   return "good — noise present but below audible threshold in most contexts"
    if floor < -60:   return "moderate — may be audible in quiet passages or headphone listening"
    if floor < -50:   return "noisy — hiss or hum likely audible"
    return "very noisy — significant background noise, noise reduction recommended"
