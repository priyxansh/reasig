"""
ReaBot DSP - Muddiness and Tonal Imbalance Detection

Uses spectral data to flag common mixing issues.
"""

from typing import Dict, Any

def analyze_tonal_balance(spectrum_data: Dict[str, Any]) -> Dict[str, bool]:
    """
    Analyzes energy bands to detect muddiness, harshness, etc.
    
    Args:
        spectrum_data: Output from analyze_spectrum()
        
    Returns:
        Dict of boolean flags.
    """
    bands = spectrum_data.get("band_energy", {})
    
    # Sub/Rumble detection (< 60Hz)
    # If sub energy is unexpectedly high (relative to low/low-mid)
    sub = bands.get("sub_20_60", 0)
    low = bands.get("low_60_200", 0)
    rumble = sub > 0.4 and (sub > low * 1.5)
    
    # Muddiness detection (200-500Hz)
    # If low-mid contains more than 45% of the total track energy
    low_mid = bands.get("low_mid_200_500", 0)
    muddiness = low_mid > 0.45
    
    # Boxiness (approx 300-600Hz, we use low_mid + mid as a proxy)
    # If energy is extremely concentrated here and lacking highs
    mid = bands.get("mid_500_2k", 0)
    high = bands.get("high_5k_10k", 0)
    air = bands.get("air_10k_20k", 0)
    boxiness = (low_mid + mid > 0.7) and (high + air < 0.05)
    
    # Harshness (2k-5k)
    # If upper-mid contains more than 30% of total energy
    upper_mid = bands.get("upper_mid_2k_5k", 0)
    harshness = upper_mid > 0.30
    
    return {
        "rumble": bool(rumble),
        "muddiness": bool(muddiness),
        "boxiness": bool(boxiness),
        "harshness": bool(harshness)
    }
