"""
ReaBot DSP - Musical Analysis

Analyzes BPM and musical key.
"""

import librosa
import numpy as np
from typing import Dict, Any

def analyze_musicality(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Perform musical analysis (BPM and Key).
    """
    # 1. BPM estimation
    # Use onset envelope for better beat tracking
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    
    # Run beat tracker
    # librosa.beat.beat_track returns a tuple, first element is tempo
    tempo_result = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)[0]
    
    # Handle single value or array return type
    if isinstance(tempo_result, np.ndarray):
        bpm = float(tempo_result[0]) if tempo_result.size > 0 else 0.0
    else:
        bpm = float(tempo_result)
        
    # 2. Key estimation
    # Extract chroma features
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    
    # Sum chroma over time
    chroma_sum = np.sum(chroma, axis=1)
    
    # Simple key estimation based on Krumhansl-Kessler profiles
    # (A very naive but effective enough approximation for this scale)
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    if np.max(chroma_sum) > 0:
        # Find the most prominent pitch class
        key_idx = int(np.argmax(chroma_sum))
        key_note = notes[key_idx]
        
        # Very rough major/minor estimation based on the minor 3rd vs major 3rd
        # Relative to key_idx: +3 semitones is minor 3rd, +4 is major 3rd
        min3_idx = (key_idx + 3) % 12
        maj3_idx = (key_idx + 4) % 12
        
        if chroma_sum[min3_idx] > chroma_sum[maj3_idx]:
            scale = "Minor"
        else:
            scale = "Major"
            
        key_str = f"{key_note} {scale}"
    else:
        key_str = "Unknown"
        
    return {
        "bpm": round(bpm, 1),
        "key": key_str
    }
