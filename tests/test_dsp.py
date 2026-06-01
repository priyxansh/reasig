"""
Tests for individual DSP analysis modules.
Uses fast NumPy array fixtures from conftest.py without disk I/O.
"""

import numpy as np
from daemon.dsp import dynamics, noise, stereo, router, loudness, spectrum

# --- Dynamics ---
def test_detect_clipping_clean(sine_wave, sr):
    y = sine_wave(amp=0.5)
    result = dynamics.detect_clipping(y)
    assert result["clip_severity"] == "none"
    assert result["clip_ratio_pct"] == 0.0

def test_detect_clipping_hard(clipped_sine, sr):
    # Hard clipped sine wave
    y = clipped_sine(amp=1.5, threshold=1.0)
    result = dynamics.detect_clipping(y)
    assert result["clip_severity"].startswith("moderate") or result["clip_severity"].startswith("severe") or result["clip_severity"].startswith("significant")
    assert result["clip_ratio_pct"] > 0.0

# --- Noise ---
def test_analyze_noise_floor_properties(sine_wave, white_noise, sr):
    # Noise floor analyzes the quietest 500ms windows.
    # To test it, we need a signal with a "gap".
    
    # Clean signal: 1s loud sine + 1s complete silence
    clean_loud = sine_wave(amp=0.8, seconds=1.0)
    clean_gap = np.zeros(sr, dtype=np.float32)
    clean_y = np.concatenate([clean_loud, clean_gap])
    
    # Noisy signal: 1s loud sine + 1s white noise "gap"
    noisy_loud = sine_wave(amp=0.8, seconds=1.0)
    noisy_gap = white_noise(amp=0.05, seconds=1.0)
    noisy_y = np.concatenate([noisy_loud, noisy_gap])
    
    clean_result = noise.analyze_noise_floor(clean_y, sr)
    noisy_result = noise.analyze_noise_floor(noisy_y, sr)
    
    # Silence/Clean has a lower dBFS noise floor
    assert clean_result["noise_floor_db"] < noisy_result["noise_floor_db"]

# --- Stereo ---
def test_analyze_stereo_mono(stereo_sine, sr):
    # Identical L and R channels
    y = stereo_sine(phase_shift=0.0)
    result = stereo.analyze_stereo(y, sr)
    
    # Exact properties for identical channels
    assert result["stereo_width"] == 0.0
    assert result["mono_compatibility_score"] == 1.0

def test_analyze_stereo_shifted(stereo_sine, sr):
    # Out of phase L and R channels
    y = stereo_sine(phase_shift=np.pi / 2)
    result = stereo.analyze_stereo(y, sr)
    
    # Width should be positive, mono compat might be less than 1.0
    assert result["stereo_width"] > 0.0

# --- Router ---
def test_router_keywords():
    # Test specific exact mappings
    flags = router.route_analysis("my track sounds too boomy")
    assert flags.run_spectrum is True
    assert flags.run_muddiness is True
    
    flags = router.route_analysis("is this clipping")
    assert flags.run_distortion is True
    
    flags = router.route_analysis("spotify loudness")
    assert flags.run_loudness is True

    # Unknown prompts fallback to all enabled (avoid substring collisions like "thin" in "think")
    flags = router.route_analysis("is the overall balance good")
    assert flags.run_spectrum is True
    assert flags.run_loudness is True

# --- Loudness ---
def test_loudness_properties(sine_wave, white_noise, sr):
    y = sine_wave(amp=0.8)
    result = loudness.analyze_loudness(y, sr)
    
    assert isinstance(result.get("lufs_integrated"), float)
    assert "platform_deltas" in result
    assert "spotify" in result["platform_deltas"]

    # Near-silence should be reported as "too quiet" or unmeasurable
    silent = sine_wave(amp=1e-6)
    silent_result = loudness.analyze_loudness(silent, sr)
    lufs = silent_result.get("lufs_integrated")
    # Either returns None (signal too quiet) or an extremely low LUFS value
    assert lufs is None or lufs < -60.0

# --- Spectrum ---
def test_spectrum_properties(white_noise, sr):
    y = white_noise(amp=0.5)
    result = spectrum.analyze_spectrum(y, sr)
    
    assert "spectral_centroid_hz" in result
    assert "band_energy" in result
    
    bands = result["band_energy"]
    assert "sub_20_60" in bands
    assert "air_10k_20k" in bands
    
    # Sum of band energies. Note that bands only cover 20Hz-20kHz.
    # At 44.1kHz, Nyquist is 22.05kHz. White noise has energy up to 22.05kHz.
    # So the sum of energy in 20-20k will be roughly 20000/22050 = 0.907.
    total_energy = sum(bands.values())
    assert 0.85 <= total_energy <= 1.0
