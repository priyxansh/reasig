"""
ReaBot DSP - Spectral Analysis

Analyzes the frequency content of the audio signal.
"""

import librosa
import numpy as np
from typing import Dict, Any

def analyze_spectrum(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Perform spectral analysis on the audio signal.
    
    Returns:
        Dict containing spectral centroid, bandwidth, rolloff, and energy bands.
    """
    # Calculate Short-Time Fourier Transform (STFT)
    # n_fft=2048 is standard for music/audio analysis
    S = np.abs(librosa.stft(y, n_fft=2048))
    
    # Core spectral features
    centroid = librosa.feature.spectral_centroid(S=S, sr=sr)[0]
    bandwidth = librosa.feature.spectral_bandwidth(S=S, sr=sr)[0]
    rolloff = librosa.feature.spectral_rolloff(S=S, sr=sr, roll_percent=0.85)[0]
    
    # Averages over time
    avg_centroid = float(np.mean(centroid))
    avg_bandwidth = float(np.mean(bandwidth))
    avg_rolloff = float(np.mean(rolloff))
    
    # Calculate energy distribution in specific frequency bands
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    
    # Power spectrogram
    power = S ** 2
    total_power = np.sum(power)
    
    if total_power == 0:
        total_power = 1e-10 # Prevent division by zero
    
    # Define mixing bands (Hz)
    bands = {
        "sub_20_60": (20, 60),
        "low_60_200": (60, 200),
        "low_mid_200_500": (200, 500),
        "mid_500_2k": (500, 2000),
        "upper_mid_2k_5k": (2000, 5000),
        "high_5k_10k": (5000, 10000),
        "air_10k_20k": (10000, 20000)
    }
    
    band_energy = {}
    for name, (low, high) in bands.items():
        # Find bin indices for this frequency range
        idx = np.where((freqs >= low) & (freqs < high))[0]
        if len(idx) > 0:
            # Sum power in these bins across all time frames
            band_pwr = np.sum(power[idx, :])
            # Store as a ratio of total power (0.0 to 1.0)
            band_energy[name] = float(band_pwr / total_power)
        else:
            band_energy[name] = 0.0
            
    return {
        "spectral_centroid_hz": avg_centroid,
        "spectral_bandwidth_hz": avg_bandwidth,
        "spectral_rolloff_hz": avg_rolloff,
        "band_energy": band_energy
    }
