"""
Integration tests for the full DSP pipeline.
Uses temp .wav files to exercise file-loading and end-to-end analysis.
"""

import os
from daemon.dsp.analyzer import analyze_audio_file

def test_analyze_audio_file_integration(sine_wave, write_wav, sr):
    """
    Test the full DSP pipeline end-to-end on a generated sine wave file.
    """
    # Generate a simple 1-second sine wave
    y = sine_wave(freq=440.0, sr=sr, seconds=1.0, amp=0.8)
    
    # Write to a temporary .wav file
    wav_path = write_wav(y, sr, "test_sine.wav")
    
    assert os.path.exists(wav_path)
    
    # Run full analysis
    analysis = analyze_audio_file(
        wav_path=wav_path,
        user_question="analyze everything",
        stereo=False
    )
    
    # Verify the dictionary contains the expected top-level keys
    # representing the various DSP modules
    assert "rms_db" in analysis
    assert "loudness" in analysis
    assert "spectral_centroid_hz" in analysis
    assert "tonal_balance" in analysis
    assert "transients" in analysis
    assert "musical" in analysis
    assert "noise" in analysis
    assert "reverb" in analysis
    assert "distortion" in analysis
    
    # Validate basic properties of the integration output
    assert analysis["rms_db"] < 0
    assert analysis["musical"]["bpm"] > 0
    assert analysis["distortion"]["fundamental_hz"] > 0
