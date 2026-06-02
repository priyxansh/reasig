"""
ReaSig DSP - Harmonic Distortion (THD)

Estimates Total Harmonic Distortion by finding the dominant fundamental
frequency and measuring relative energy at its 2nd through 5th harmonics.

Most meaningful on tonal sources with a clear pitch:
  - Bass guitar, synth bass, electric guitar, vocals, synth leads
Less meaningful on:
  - Full mixes (many fundamentals overlap)
  - Pure noise or atonal percussion
"""

import numpy as np
from typing import Dict, Any, List


def analyze_harmonic_distortion(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Estimate THD from the spectral content of up to the first 2 seconds.

    Args:
        y:  Mono audio array, shape (N,).
        sr: Sample rate in Hz.

    Returns:
        Dict with fundamental_hz, thd_ratio, thd_label, harmonics list.
    """
    # Analyse up to first 2 seconds for speed
    y_segment = y[:min(len(y), sr * 2)]

    if len(y_segment) < 512:
        return {
            "fundamental_hz": None,
            "thd_ratio":      None,
            "thd_label":      "clip too short for distortion analysis",
            "harmonics":      [],
        }

    fft      = np.fft.rfft(y_segment)
    freqs    = np.fft.rfftfreq(len(y_segment), 1.0 / sr)
    spectrum = np.abs(fft)

    # Search for fundamental in 40–3000 Hz (covers bass through vocal range)
    low_idx  = max(1, int(np.searchsorted(freqs, 40.0)))
    high_idx = int(np.searchsorted(freqs, 3000.0))

    if high_idx <= low_idx:
        return {
            "fundamental_hz": None,
            "thd_ratio":      None,
            "thd_label":      "insufficient frequency resolution",
            "harmonics":      [],
        }

    segment_spectrum = spectrum[low_idx:high_idx]
    if np.max(segment_spectrum) < 1e-6:
        return {
            "fundamental_hz": None,
            "thd_ratio":      None,
            "thd_label":      "no clear fundamental detected — may be noise or broadband",
            "harmonics":      [],
        }

    f0_rel_idx = int(np.argmax(segment_spectrum))
    f0_idx     = low_idx + f0_rel_idx
    f0_hz      = float(freqs[f0_idx])
    f0_energy  = float(spectrum[f0_idx])

    if f0_energy < 1e-6:
        return {
            "fundamental_hz": round(f0_hz, 1),
            "thd_ratio":      None,
            "thd_label":      "fundamental too weak to measure harmonic distortion",
            "harmonics":      [],
        }

    # Measure energy at 2nd through 5th harmonics using a ±5 bin window
    harmonic_energy_total = 0.0
    harmonics: List[Dict[str, Any]] = []

    for n in range(2, 6):
        fh_hz = f0_hz * n
        if fh_hz >= sr / 2.0:
            break
        fh_idx = int(np.searchsorted(freqs, fh_hz))
        win_lo = max(0, fh_idx - 5)
        win_hi = min(len(spectrum), fh_idx + 6)
        e      = float(np.max(spectrum[win_lo:win_hi])) if win_hi > win_lo else 0.0
        harmonic_energy_total += e
        harmonics.append({
            "harmonic_n":   n,
            "freq_hz":      round(fh_hz, 1),
            "rel_energy":   round(e / f0_energy, 4),
        })

    thd = harmonic_energy_total / f0_energy if f0_energy > 0 else 0.0

    return {
        "fundamental_hz": round(f0_hz, 1),
        "thd_ratio":      round(thd, 4),
        "thd_label":      _thd_label(thd),
        "harmonics":      harmonics,
    }


def _thd_label(thd: float) -> str:
    if thd < 0.01:   return "very clean — negligible harmonic distortion"
    if thd < 0.05:   return "clean — slight harmonic enrichment, natural character"
    if thd < 0.15:   return "moderate — noticeable warmth or grit, typical of light saturation"
    if thd < 0.35:   return "significant — prominent saturation or overdrive character"
    if thd < 0.70:   return "heavy — strong distortion, likely intentional (fuzz, overdrive)"
    return "extreme — severe distortion or signal corruption"
