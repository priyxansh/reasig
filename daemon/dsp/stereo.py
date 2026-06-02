"""
ReaSig DSP - Stereo Analysis

Analyzes stereo width, L/R balance, Mid/Side spectral content,
and mono compatibility. Only runs when the user explicitly enables
the stereo toggle in the UI.
"""

import numpy as np
from typing import Dict, Any

from .spectrum import analyze_spectrum

# Target sample rate (must match analyzer.py)
TARGET_SR = 44100


def analyze_stereo(y_stereo: np.ndarray, sr: int = TARGET_SR) -> Dict[str, Any]:
    """
    Perform stereo analysis on a 2-channel audio array.

    Args:
        y_stereo: NumPy array of shape (2, N) where y_stereo[0] is Left
                  and y_stereo[1] is Right.
        sr: Sample rate (default 44100).

    Returns:
        Dict with stereo width, L/R balance, M/S spectra, and mono compat score.
    """
    if y_stereo.ndim != 2 or y_stereo.shape[0] != 2:
        raise ValueError(
            f"Expected a 2-channel array with shape (2, N), got {y_stereo.shape}"
        )

    left = y_stereo[0]
    right = y_stereo[1]

    # -------------------------------------------------------------------------
    # 1. L/R Balance
    # Positive = left channel is louder. Negative = right channel is louder.
    # -------------------------------------------------------------------------
    left_rms = float(np.sqrt(np.mean(left ** 2)))
    right_rms = float(np.sqrt(np.mean(right ** 2)))

    if right_rms > 0 and left_rms > 0:
        lr_balance_db = float(20 * np.log10(left_rms / right_rms))
    else:
        lr_balance_db = 0.0

    # -------------------------------------------------------------------------
    # 2. Mid / Side Decomposition
    # Mid  = (L + R) / 2  — the mono-compatible center content
    # Side = (L - R) / 2  — stereo-only content, lost on mono playback
    # -------------------------------------------------------------------------
    mid = (left + right) / 2.0
    side = (left - right) / 2.0

    mid_energy = float(np.sum(mid ** 2))
    side_energy = float(np.sum(side ** 2))
    total_ms_energy = mid_energy + side_energy

    # -------------------------------------------------------------------------
    # 3. Stereo Width
    # Ratio of Side energy to total M/S energy.
    # 0.0 = completely mono. 0.5 = equal Mid and Side. ~1.0 = extremely wide.
    # -------------------------------------------------------------------------
    if total_ms_energy > 0:
        stereo_width = float(side_energy / total_ms_energy)
    else:
        stereo_width = 0.0

    # -------------------------------------------------------------------------
    # 4. Mono Compatibility Score (Pearson Correlation)
    # +1.0 = perfect mono (L and R identical).
    # 0.0  = completely uncorrelated (full stereo).
    # -1.0 = phase-inverted — will fully cancel on mono playback.
    # -------------------------------------------------------------------------
    if np.std(left) > 0 and np.std(right) > 0:
        # Pearson correlation coefficient between L and R
        correlation_matrix = np.corrcoef(left, right)
        mono_compat_score = float(correlation_matrix[0, 1])
    else:
        mono_compat_score = 1.0  # silence is trivially mono-compatible

    # -------------------------------------------------------------------------
    # 5. Mid and Side Spectral Profiles
    # Run analyze_spectrum() on Mid and Side independently.
    # This tells the LLM what frequencies live in the center vs. the edges.
    # e.g. "your low-mids are entirely in the side channel — they'll cancel on mono"
    # -------------------------------------------------------------------------
    mid_spectrum = analyze_spectrum(mid, sr)
    side_spectrum = analyze_spectrum(side, sr) if side_energy > 1e-10 else None

    return {
        "lr_balance_db": round(lr_balance_db, 2),
        "stereo_width": round(stereo_width, 4),
        "mono_compatibility_score": round(mono_compat_score, 4),
        "mid_spectrum": mid_spectrum,
        "side_spectrum": side_spectrum,
        "interpretation": _interpret_stereo(stereo_width, mono_compat_score, lr_balance_db),
    }


def _interpret_stereo(width: float, compat: float, lr_balance: float) -> Dict[str, str]:
    """
    Generate plain-language interpretations of stereo metrics for the LLM.
    Reduces the LLM's reasoning burden by pre-labelling the numbers.
    """
    # Width interpretation
    if width < 0.05:
        width_label = "mono or extremely narrow"
    elif width < 0.20:
        width_label = "narrow"
    elif width < 0.40:
        width_label = "moderate"
    elif width < 0.60:
        width_label = "wide"
    else:
        width_label = "very wide"

    # Mono compatibility
    if compat >= 0.8:
        compat_label = "excellent mono compatibility"
    elif compat >= 0.5:
        compat_label = "acceptable mono compatibility"
    elif compat >= 0.0:
        compat_label = "poor mono compatibility — audible coloration on mono playback"
    else:
        compat_label = "phase cancellation detected — will partially or fully cancel in mono"

    # L/R balance
    if abs(lr_balance) < 0.5:
        balance_label = "balanced"
    elif lr_balance > 0:
        balance_label = f"left-heavy by {abs(lr_balance):.1f} dB"
    else:
        balance_label = f"right-heavy by {abs(lr_balance):.1f} dB"

    return {
        "width_label": width_label,
        "mono_compat_label": compat_label,
        "balance_label": balance_label,
    }
