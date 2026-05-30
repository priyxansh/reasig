"""
ReaBot DSP - Shared Types

Defines shared dataclasses used across DSP modules.
Kept in a dedicated file to avoid circular imports between router.py and analyzer.py.
"""

from dataclasses import dataclass, field


@dataclass
class AnalysisFlags:
    """
    Controls which DSP modules are run for a given analysis request.

    Generated either by the keyword router (automatic) or passed directly
    by the caller with manually set values (Phase 6 override UI).

    Note: stereo analysis is NOT a flag here. It is a separate boolean
    parameter on analyze_audio_file() because it changes how the audio
    file is loaded before any routing or analysis begins.

    Note: spectral_balance has no flag — it runs automatically whenever
    run_spectrum is True (it's just a post-processing step on band_energy).
    """
    run_spectrum:    bool = True
    run_dynamics:    bool = True   # always includes clipping detection
    run_muddiness:   bool = True
    run_transients:  bool = True
    run_musical:     bool = True
    run_loudness:    bool = True
    run_noise:       bool = True
    run_reverb:      bool = True
    run_distortion:  bool = True

    @classmethod
    def all_enabled(cls) -> "AnalysisFlags":
        """Return flags with all modules enabled. Used as the fallback."""
        return cls()

    @classmethod
    def from_dict(cls, d: dict) -> "AnalysisFlags":
        """
        Construct from a plain dict (e.g. from a TCP payload for Phase 6 override).
        Unknown keys are ignored. Missing keys default to True.
        """
        return cls(
            run_spectrum=d.get("run_spectrum",   True),
            run_dynamics=d.get("run_dynamics",   True),
            run_muddiness=d.get("run_muddiness", True),
            run_transients=d.get("run_transients", True),
            run_musical=d.get("run_musical",     True),
            run_loudness=d.get("run_loudness",   True),
            run_noise=d.get("run_noise",         True),
            run_reverb=d.get("run_reverb",       True),
            run_distortion=d.get("run_distortion", True),
        )
