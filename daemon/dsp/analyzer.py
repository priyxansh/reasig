"""
ReaBot DSP - Analyzer Orchestrator

Loads audio files and runs all DSP modules.
"""

import librosa
import numpy as np
import logging
from typing import Dict, Any

from .spectrum import analyze_spectrum
from .dynamics import analyze_dynamics
from .muddiness import analyze_tonal_balance
from .transients import analyze_transients
from .musical import analyze_musicality
from .masking import analyze_masking

logger = logging.getLogger("reabot.dsp")

# Target sample rate for consistent FFT bin sizes across all files
TARGET_SR = 44100
# Maximum duration to analyze (to prevent OOM on full 10-minute stems)
MAX_DURATION_SEC = 30.0

async def analyze_audio_file(wav_path: str) -> Dict[str, Any]:
    """
    Main entry point for DSP analysis of a single audio file.
    
    Args:
        wav_path: Absolute path to the WAV file.
        
    Returns:
        A combined dictionary of all analysis results.
    """
    logger.info("Starting DSP analysis for %s", wav_path)
    
    try:
        # 1. Load audio
        # Force mono and 44.1kHz for consistent analysis
        # Limit duration to prevent massive memory usage
        y, sr = librosa.load(
            wav_path, 
            sr=TARGET_SR, 
            mono=True, 
            duration=MAX_DURATION_SEC
        )
        
        if len(y) == 0:
            raise ValueError(f"Audio file {wav_path} is empty or unreadable.")
            
        # 2. Run modules (synchronously, since they are CPU bound)
        # Note: In a heavily loaded production system, we'd run these in a ProcessPoolExecutor.
        # For a single-user local daemon, running them directly is fine.
        
        # Spectrum
        spectrum_results = analyze_spectrum(y, sr)
        
        # Dynamics
        dynamics_results = analyze_dynamics(y)
        
        # Tonal Balance / Flags
        flags = analyze_tonal_balance(spectrum_results)
        
        # Transients
        transient_results = analyze_transients(y, sr)
        
        # Musical
        musical_results = analyze_musicality(y, sr)
        
        # 3. Combine results
        combined = {
            **dynamics_results,
            **spectrum_results,
            "flags": flags,
            "transients": transient_results,
            "musical": musical_results
        }
        
        logger.info("Analysis complete for %s", wav_path)
        return combined
        
    except Exception as e:
        logger.error("DSP analysis failed for %s: %s", wav_path, str(e))
        raise

async def analyze_multiple_tracks(wav_paths: list[str]) -> Dict[str, Any]:
    """
    Masking handler. Note: This expects wav paths but since we need the 
    actual analysis results for masking, the server routes it differently.
    This function is just a stub for the server masking handler.
    """
    # The actual masking logic uses analyze_masking() and expects dicts,
    # so we don't strictly need a file-based entry point for it here unless
    # we want to re-analyze files. The server currently passes the analysis
    # dicts directly into a combined context.
    # We will just expose analyze_masking directly to the server.
    pass
