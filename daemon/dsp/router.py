"""
ReaSig DSP - Keyword Analysis Router

Scans the user's prompt and returns an AnalysisFlags object indicating
which DSP modules should run for this request.

This runs locally in microseconds with zero API calls.
The fallback behavior (no keywords matched) is to run all modules.

Note: Stereo analysis is NOT routed here. It is controlled by an explicit
boolean toggle in the UI and passed separately to analyze_audio_file().
"""

import re
from .types import AnalysisFlags

# ---------------------------------------------------------------------------
# Keyword sets per module group.
# These are intentionally broad to catch paraphrases.
# A prompt matching multiple groups enables all matched modules.
# ---------------------------------------------------------------------------

_SPECTRUM_MUDDINESS_KEYWORDS = {
    "muddy", "muddiness", "boomy", "boom", "boominess",
    "rumble", "bass heavy", "bass-heavy", "low end", "low-end",
    "boxy", "boxiness", "warm", "warmth", "thick", "thickness",
    "harsh", "harshness", "brittle", "tinny", "bright", "dull",
    "dark", "frequency", "frequencies", "eq", "equalizer",
    "band", "bands", "spectrum", "spectral", "resonance",
    "buildup", "build up", "high end", "high-end", "air", "presence",
    "tonal", "tone",
}

_DYNAMICS_TRANSIENTS_KEYWORDS = {
    "thin", "thinness", "weak", "weakness", "no punch", "lacks punch",
    "flat", "lifeless", "squashed", "squash", "over-compressed",
    "over compressed", "compressed", "compression", "compressor",
    "transient", "transients", "attack", "release", "snap",
    "snappy", "punch", "punchy", "impact", "hit", "crack",
    "dynamic", "dynamics", "crest factor", "limiter", "limiting",
    "rms", "peak", "headroom",
}

_LOUDNESS_KEYWORDS = {
    "lufs", "loudness", "loud", "quiet",
    "spotify", "apple music", "youtube", "tidal", "amazon music", "streaming",
    "normalize", "normalisation", "normalization", "normalise",
    "master", "mastering", "level", "turn down", "turned down",
    "integrated", "target", "release loudness", "too loud", "too quiet",
}

_NOISE_KEYWORDS = {
    "noise", "hiss", "hissy", "hum", "buzz", "buzzing",
    "background", "noise floor", "snr", "signal to noise",
    "static", "crackle", "interference", "hissing",
    "recording quality", "clean recording", "dirty recording",
}

_REVERB_KEYWORDS = {
    "reverb", "room", "roomy", "wet", "decay", "tail", "rt60",
    "hall", "ambience", "ambient", "space", "echo", "washy", "wash",
    "smear", "remove reverb", "dry", "tight", "too much reverb",
    "sounds roomy", "sounds wet",
}

_DISTORTION_KEYWORDS = {
    "distortion", "distorted", "dirty", "gritty", "grit",
    "saturate", "saturation", "overdrive", "harmonic distortion", "thd",
    "fuzzy", "fuzz", "aliasing", "bitcrush", "bitcrusher",
    "sounds harsh", "sounds dirty", "harsh", "harshness",
    "clipping", "clip", "clipped", "overloaded",
}

_MUSICAL_KEYWORDS = {
    "out of tune", "tuning", "tune", "pitched", "pitch", "key",
    "chord", "chords", "harmony", "harmonics", "harmonic",
    "root", "scale", "melody",
    "bpm", "tempo", "beat", "rhythm",
}

# ---------------------------------------------------------------------------

def _has_match(keywords: set[str], text: str) -> bool:
    """Check if any of the keywords appear as whole words/phrases in the text."""
    for keyword in keywords:
        # \b ensures we match "thin" but not "think" or "everything"
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, text):
            return True
    return False


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

    normalized = prompt.lower().strip()

    run_spectrum   = False
    run_muddiness  = False
    run_dynamics   = False
    run_transients = False
    run_musical    = False
    run_loudness   = False
    run_noise      = False
    run_reverb     = False
    run_distortion = False

    if _has_match(_SPECTRUM_MUDDINESS_KEYWORDS, normalized):
        run_spectrum  = True
        run_muddiness = True

    if _has_match(_DYNAMICS_TRANSIENTS_KEYWORDS, normalized):
        run_dynamics   = True
        run_transients = True

    if _has_match(_LOUDNESS_KEYWORDS, normalized):
        run_loudness = True

    if _has_match(_NOISE_KEYWORDS, normalized):
        run_noise = True

    if _has_match(_REVERB_KEYWORDS, normalized):
        run_reverb = True

    if _has_match(_DISTORTION_KEYWORDS, normalized):
        run_distortion = True

    if _has_match(_MUSICAL_KEYWORDS, normalized):
        run_musical = True

    # Fallback: if nothing matched at all, run everything
    any_matched = (
        run_spectrum or run_dynamics or run_musical
        or run_loudness or run_noise or run_reverb or run_distortion
    )
    if not any_matched:
        return AnalysisFlags.all_enabled()

    # Spectrum is always needed when muddiness is flagged
    if run_muddiness:
        run_spectrum = True

    return AnalysisFlags(
        run_spectrum=run_spectrum,
        run_dynamics=run_dynamics,
        run_muddiness=run_muddiness,
        run_transients=run_transients,
        run_musical=run_musical,
        run_loudness=run_loudness,
        run_noise=run_noise,
        run_reverb=run_reverb,
        run_distortion=run_distortion,
    )

