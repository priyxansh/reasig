"""
ReaBot DSP - Dynamics Analysis

Analyzes RMS, Peak, and Crest Factor of the audio signal.
"""

import numpy as np
from typing import Dict, Any

def analyze_dynamics(y: np.ndarray) -> Dict[str, Any]:
    """
    Perform dynamics analysis on the audio signal.
    
    Returns:
        Dict containing RMS, Peak, and Crest Factor in dB.
    """
    # Prevent log10 of zero
    safe_y = np.where(y == 0, 1e-10, y)
    
    # Calculate RMS (Root Mean Square)
    rms = np.sqrt(np.mean(safe_y**2))
    
    # Calculate Peak (Absolute max value)
    peak = np.max(np.abs(safe_y))
    
    # Convert to decibels (dBFS)
    # Reference is 1.0 (full scale)
    if rms > 0:
        rms_db = 20 * np.log10(rms)
    else:
        rms_db = -100.0
        
    if peak > 0:
        peak_db = 20 * np.log10(peak)
    else:
        peak_db = -100.0
        
    # Crest Factor: ratio of peak to RMS
    # In dB, this is simply peak_db - rms_db
    crest_factor_db = peak_db - rms_db
    
    return {
        "rms_db": float(rms_db),
        "peak_db": float(peak_db),
        "crest_factor_db": float(crest_factor_db)
    }
