"""
ReaBot DSP - Transient Analysis

Analyzes onset detection and percussiveness.
"""

import librosa
import numpy as np
from typing import Dict, Any

def analyze_transients(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Perform transient and onset analysis.
    """
    # Detect onsets (transient hits)
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
    
    # Calculate duration of the audio in seconds
    duration = librosa.get_duration(y=y, sr=sr)
    
    if duration > 0:
        onsets_per_second = len(onset_frames) / duration
    else:
        onsets_per_second = 0.0
        
    # Determine density category
    if onsets_per_second < 1.0:
        density = "low"
    elif onsets_per_second < 4.0:
        density = "medium"
    else:
        density = "high"
        
    # Calculate percussive vs harmonic ratio
    # hpss decomposes audio into harmonic and percussive components
    y_harmonic, y_percussive = librosa.effects.hpss(y)
    
    p_energy = np.sum(y_percussive**2)
    h_energy = np.sum(y_harmonic**2)
    total_energy = p_energy + h_energy
    
    if total_energy > 0:
        percussive_ratio = p_energy / total_energy
    else:
        percussive_ratio = 0.0
        
    return {
        "density": density,
        "onsets_per_second": float(onsets_per_second),
        "percussive_ratio": float(percussive_ratio)
    }
