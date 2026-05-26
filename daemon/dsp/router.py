"""
ReaBot DSP - Keyword Analysis Router

Scans the user's prompt and returns an AnalysisFlags object indicating
which DSP modules should run for this request.

This runs locally in microseconds with zero API calls.
The fallback behavior (no keywords matched) is to run all modules.

Note: Stereo analysis is NOT routed here. It is controlled by an explicit
boolean toggle in the UI and passed separately to analyze_audio_file().
"""

from .types import AnalysisFlags

# ---------------------------------------------------------------------------
# Keyword lists per module group
# These are intentionally broad to catch paraphrases.
# A prompt matching multiple groups enables all matched modules.
# ---------------------------------------------------------------------------

_SPECTRUM_MUDDINESS_KEYWORDS = {
    "muddy", "muddiness", "muddy", "boomy", "boom", "boominess",
    "rumble", "bass heavy", "bass-heavy", "low end", "low-end",
    "boxy", "boxiness", "warm", "warmth", "thick", "thickness",
    "harsh", "harshness", "brittle", "tinny", "bright", "dull",
    "dark", "frequency", "frequencies", "eq", "equalizer",
    "band", "bands", "spectrum", "spectral", "resonance",
    "buildup", "build up", "high end", "high-end", "air", "presence",
}

_DYNAMICS_TRANSIENTS_KEYWORDS = {
    "thin", "thinness", "weak", "weakness", "no punch", "lacks punch",
    "flat", "lifeless", "squashed", "squash", "over-compressed",
    "over compressed", "compressed", "compression", "compressor",
    "transient", "transients", "attack", "release", "snap",
    "snappy", "punch", "punchy", "impact", "hit", "crack",
    "dynamic", "dynamics", "loud", "quiet", "level", "volume",
    "crest factor", "limiter", "limiting", "clipping", "clip",
    "rms", "peak", "headroom",
}

_MUSICAL_KEYWORDS = {
    "out of tune", "tuning", "tune", "pitched", "pitch", "key",
    "chord", "chords", "harmony", "harmonics", "harmonic",
    "root", "scale", "melody", "tonal",
    "bpm", "tempo", "beat", "rhythm",
}

# ---------------------------------------------------------------------------

def _tokenize(text: str) -> str:
    """Lowercase and normalize text for matching."""
    return text.lower().strip()


def route_analysis(prompt: str, track_metadata: dict | None = None) -> AnalysisFlags:
    """
    Determine which DSP modules to run based on the user's prompt.

    Args:
        prompt: The user's question or instruction.
        track_metadata: Optional track metadata dict. Currently unused but
            reserved for future routing based on track name (e.g. a track
            named "Kick" auto-enables transient analysis).

    Returns:
        AnalysisFlags with the appropriate modules enabled.
    """
    if not prompt or not prompt.strip():
        # No prompt — run everything as the safe fallback
        return AnalysisFlags.all_enabled()

    normalized = _tokenize(prompt)

    run_spectrum = False
    run_muddiness = False
    run_dynamics = False
    run_transients = False
    run_musical = False

    # Check each keyword group
    for keyword in _SPECTRUM_MUDDINESS_KEYWORDS:
        if keyword in normalized:
            run_spectrum = True
            run_muddiness = True
            break

    for keyword in _DYNAMICS_TRANSIENTS_KEYWORDS:
        if keyword in normalized:
            run_dynamics = True
            run_transients = True
            break

    for keyword in _MUSICAL_KEYWORDS:
        if keyword in normalized:
            run_musical = True
            break

    # Fallback: if nothing matched at all, run everything
    any_matched = run_spectrum or run_dynamics or run_musical
    if not any_matched:
        return AnalysisFlags.all_enabled()

    # Spectrum analysis is always needed if muddiness is flagged
    # (muddiness.py reads from spectrum output)
    if run_muddiness:
        run_spectrum = True

    return AnalysisFlags(
        run_spectrum=run_spectrum,
        run_dynamics=run_dynamics,
        run_muddiness=run_muddiness,
        run_transients=run_transients,
        run_musical=run_musical,
    )
