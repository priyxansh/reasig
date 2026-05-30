"""
ReaBot DSP - Spectral Balance vs Reference Curve

Compares a track's spectral band energy distribution against a target curve
representing a well-balanced commercial mix (simplified B72/Tonal Balance style).

Important: this reference is designed for full mixes. Individual instruments
will naturally deviate from it — the LLM should interpret deviations in context
(e.g., a kick drum being sub-heavy is expected, not a problem).
"""

from typing import Dict, Any

# "Neutral commercial mix" reference — approximate B72-style target
# Values are fractions of total power (sum = 1.0)
_REFERENCE_CURVE: Dict[str, float] = {
    "sub_20_60":        0.05,   #  5% — tight sub
    "low_60_200":       0.20,   # 20% — warm low end
    "low_mid_200_500":  0.18,   # 18% — body
    "mid_500_2k":       0.25,   # 25% — presence
    "upper_mid_2k_5k":  0.18,   # 18% — definition/clarity
    "high_5k_10k":      0.09,   #  9% — air
    "air_10k_20k":      0.05,   #  5% — sparkle
}


def analyze_spectral_balance(band_energy: Dict[str, float]) -> Dict[str, Any]:
    """
    Compare track's band energy ratios against the reference curve.

    Args:
        band_energy: Output from analyze_spectrum()["band_energy"].
                     Keys are band names, values are 0.0–1.0 fractions.

    Returns:
        Dict with spectral_balance_vs_reference (per-band breakdown),
        overall_balance_score, and overall_balance_label.
    """
    deviations: Dict[str, Any] = {}
    for band, ref_frac in _REFERENCE_CURVE.items():
        actual_frac = float(band_energy.get(band, 0.0))
        deviation   = actual_frac - ref_frac   # positive = over, negative = under
        deviations[band] = {
            "actual_pct":    round(actual_frac * 100, 1),
            "reference_pct": round(ref_frac * 100, 1),
            "deviation_pct": round(deviation * 100, 1),
            "label":         _deviation_label(deviation),
        }

    # Overall balance score: sum of absolute deviations in percentage points
    # Lower = more balanced. 0 = perfect match.
    total_deviation = sum(abs(v["deviation_pct"]) for v in deviations.values())

    return {
        "spectral_balance_vs_reference": deviations,
        "overall_balance_score":         round(total_deviation, 1),
        "overall_balance_label":         _overall_label(total_deviation),
    }


def _deviation_label(deviation: float) -> str:
    if abs(deviation) < 0.02:   return "on target"
    if deviation > 0.15:        return "significantly over reference"
    if deviation > 0.06:        return "over reference"
    if deviation < -0.15:       return "significantly under reference"
    if deviation < -0.06:       return "under reference"
    return "slightly off — within acceptable range"


def _overall_label(score: float) -> str:
    if score < 20:    return "well balanced"
    if score < 40:    return "moderate imbalance — one or more bands need attention"
    if score < 70:    return "significant imbalance — spectral issues likely audible"
    return "severe imbalance — major tonal correction recommended"
