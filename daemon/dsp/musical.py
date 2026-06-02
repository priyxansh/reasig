"""
ReaSig DSP - Musical Analysis

Analyzes BPM and musical key.
Key estimation uses Krumhansl-Kessler tonal hierarchy profiles, which
correlate chroma vectors against psychoacoustic templates for all 24 keys.
This is significantly more accurate than argmax on the chroma sum,
especially on harmonically complex material.
"""

import librosa
import numpy as np
from typing import Dict, Any

# Krumhansl-Kessler tonal hierarchy profiles (normalized to sum=1 internally)
# These represent the "stability" of each scale degree in major/minor tonality.
_KK_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_KK_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def _estimate_key_kk(chroma_sum: np.ndarray) -> str:
    """
    Krumhansl-Kessler profile correlation.

    Tests all 24 keys (12 major + 12 minor) by rotating the KK profiles
    to each possible tonic and computing Pearson correlation with the
    observed chroma distribution. Returns the best-matching key string.
    """
    if np.max(chroma_sum) < 1e-6:
        return "Unknown"

    # Normalize observed chroma to a probability distribution
    chroma_norm = chroma_sum / (np.sum(chroma_sum) + 1e-8)

    major_norm = np.array(_KK_MAJOR) / sum(_KK_MAJOR)
    minor_norm = np.array(_KK_MINOR) / sum(_KK_MINOR)

    best_score = -np.inf
    best_key   = "Unknown"

    for tonic in range(12):
        # Rotate profiles so tonic aligns with the current pitch class
        major_rotated = np.roll(major_norm, tonic)
        minor_rotated = np.roll(minor_norm, tonic)

        # Pearson correlation — handles scale differences automatically
        r_major = float(np.corrcoef(chroma_norm, major_rotated)[0, 1])
        r_minor = float(np.corrcoef(chroma_norm, minor_rotated)[0, 1])

        if r_major > best_score:
            best_score = r_major
            best_key   = f"{_NOTE_NAMES[tonic]} Major"
        if r_minor > best_score:
            best_score = r_minor
            best_key   = f"{_NOTE_NAMES[tonic]} Minor"

    return best_key


def analyze_musicality(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Perform musical analysis: BPM estimation and key detection.
    """
    # BPM — onset-strength based beat tracker
    onset_env  = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_result = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)[0]

    if isinstance(tempo_result, np.ndarray):
        bpm = float(tempo_result[0]) if tempo_result.size > 0 else 0.0
    else:
        bpm = float(tempo_result)

    # Key — Krumhansl-Kessler chroma correlation
    chroma     = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_sum = np.sum(chroma, axis=1)
    key_str    = _estimate_key_kk(chroma_sum)

    return {
        "bpm": round(bpm, 1),
        "key": key_str,
    }

