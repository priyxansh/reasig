"""
ReaBot DSP - Transient Analysis

Analyzes onset detection, percussiveness, and transient shape.
Attack and decay times (in ms) are measured to enable specific
compressor attack/release recommendations.
"""

import librosa
import numpy as np
from typing import Dict, Any, List

# librosa's default hop length — must match onset detection
_HOP_LENGTH = 512


def _measure_attack_release(
    y: np.ndarray, sr: int, onset_frames: np.ndarray
) -> Dict[str, Any]:
    """
    Measure average attack time (onset → peak) and decay time (peak → -20 dB)
    across detected onsets. Returns times in milliseconds.

    Analyses up to 20 onsets to keep runtime bounded.
    """
    if len(onset_frames) == 0:
        return {"avg_attack_ms": None, "avg_decay_ms": None}

    attack_times: List[float] = []
    decay_times:  List[float] = []

    for frame in onset_frames[:20]:
        onset_sample = int(frame) * _HOP_LENGTH
        # Look at a 500ms window after each onset
        window_end = min(onset_sample + int(0.5 * sr), len(y))
        if window_end <= onset_sample + 10:
            continue

        segment  = np.abs(y[onset_sample:window_end])
        peak_idx = int(np.argmax(segment))
        peak_amp = float(segment[peak_idx])

        if peak_amp < 1e-6:
            continue

        # Attack: samples from onset to peak
        attack_times.append(peak_idx * 1000.0 / sr)

        # Decay: samples from peak until amplitude falls below -20 dB of peak
        threshold  = peak_amp * 0.1   # -20 dB relative
        post_peak  = segment[peak_idx:]
        below      = np.where(post_peak < threshold)[0]
        if len(below) > 0:
            decay_times.append(float(below[0]) * 1000.0 / sr)

    return {
        "avg_attack_ms": round(float(np.mean(attack_times)), 1) if attack_times else None,
        "avg_decay_ms":  round(float(np.mean(decay_times)),  1) if decay_times  else None,
    }


def analyze_transients(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Perform transient and onset analysis.

    Returns:
        Dict with density, onsets_per_second, percussive_ratio,
        avg_attack_ms, and avg_decay_ms.
    """
    # Detect onsets
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, hop_length=_HOP_LENGTH)

    duration = librosa.get_duration(y=y, sr=sr)
    onsets_per_second = len(onset_frames) / duration if duration > 0 else 0.0

    if onsets_per_second < 1.0:
        density = "low"
    elif onsets_per_second < 4.0:
        density = "medium"
    else:
        density = "high"

    # Harmonic-percussive separation for percussive energy ratio
    y_harmonic, y_percussive = librosa.effects.hpss(y)
    p_energy = float(np.sum(y_percussive ** 2))
    h_energy = float(np.sum(y_harmonic  ** 2))
    total    = p_energy + h_energy
    percussive_ratio = p_energy / total if total > 0 else 0.0

    # Attack and decay timing
    timing = _measure_attack_release(y, sr, onset_frames)

    return {
        "density":            density,
        "onsets_per_second":  round(onsets_per_second, 2),
        "percussive_ratio":   round(percussive_ratio, 4),
        "avg_attack_ms":      timing["avg_attack_ms"],
        "avg_decay_ms":       timing["avg_decay_ms"],
    }

