"""
Pytest configuration and fixtures for ReaBot DSP testing.

Provides deterministic NumPy arrays for testing DSP modules
without needing real .wav files.
"""

import pytest
import numpy as np
import soundfile as sf
from typing import Callable


@pytest.fixture
def sr() -> int:
    """Standard sample rate for tests."""
    return 44100


@pytest.fixture
def sine_wave() -> Callable:
    """
    Generate a pure sine wave numpy array.
    """
    def _gen(freq: float = 440.0, sr: int = 44100, seconds: float = 2.0, amp: float = 0.5) -> np.ndarray:
        t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
        return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return _gen


@pytest.fixture
def white_noise() -> Callable:
    """
    Generate deterministic white noise.
    """
    def _gen(sr: int = 44100, seconds: float = 2.0, amp: float = 0.1, seed: int = 42) -> np.ndarray:
        rng = np.random.default_rng(seed)
        noise = rng.uniform(-amp, amp, int(sr * seconds))
        return noise.astype(np.float32)
    return _gen


@pytest.fixture
def clipped_sine(sine_wave: Callable) -> Callable:
    """
    Generate a hard-clipped sine wave.
    """
    def _gen(freq: float = 440.0, sr: int = 44100, seconds: float = 2.0, amp: float = 1.5, threshold: float = 1.0) -> np.ndarray:
        # Generate an overly loud sine wave
        wave = sine_wave(freq=freq, sr=sr, seconds=seconds, amp=amp)
        # Hard clip to threshold
        return np.clip(wave, -threshold, threshold)
    return _gen


@pytest.fixture
def stereo_sine(sine_wave: Callable) -> Callable:
    """
    Generate a stereo sine wave (2D array, shape = [2, samples]).
    If phase_shift is provided, the right channel is delayed.
    """
    def _gen(freq: float = 440.0, sr: int = 44100, seconds: float = 2.0, amp: float = 0.5, phase_shift: float = 0.0) -> np.ndarray:
        t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
        left = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        right = (amp * np.sin(2 * np.pi * freq * t + phase_shift)).astype(np.float32)
        return np.stack((left, right))
    return _gen


@pytest.fixture
def write_wav(tmp_path) -> Callable:
    """
    Helper to write a NumPy array to a temporary .wav file.
    Returns the absolute string path to the file.
    """
    def _write(y: np.ndarray, sr: int = 44100, filename: str = "test.wav") -> str:
        filepath = tmp_path / filename
        # Ensure correct shape for soundfile (samples, channels)
        if y.ndim > 1 and y.shape[0] < y.shape[1]:
            y_write = y.T
        else:
            y_write = y
        sf.write(str(filepath), y_write, sr)
        return str(filepath)
    return _write
