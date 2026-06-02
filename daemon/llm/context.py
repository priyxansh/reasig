"""
ReaSig LLM - Context Packager

Converts DSP analysis results + track metadata + conversation history
into an OpenRouter-compatible messages list ready to be sent to the LLM.

The packager is intentionally verbose — more context = better advice.
Budget trimming is done at the end to stay within the model's context window.
"""

from typing import Optional
from .prompts import SYSTEM_PROMPT, MULTI_TRACK_SYSTEM_PROMPT

_MAX_CONTEXT_CHARS = 100_000   # ~25K tokens


def build_context(
    analysis: dict,
    track_metadata: dict,
    user_question: str,
    conversation_history: list[dict],
    is_multi_track: bool = False,
) -> list[dict]:
    """
    Build the messages list for an OpenRouter chat completion request.

    Args:
        analysis:             Combined DSP output from analyze_audio_file().
        track_metadata:       Track info dict from track.lua (name, vol, fx_chain, etc.)
        user_question:        The user's prompt text.
        conversation_history: List of {"role": ..., "content": ...} dicts, oldest first.
        is_multi_track:       If True, uses the multi-track system prompt variant.

    Returns:
        List of message dicts ready to pass to the OpenRouter API.
    """
    system = MULTI_TRACK_SYSTEM_PROMPT if is_multi_track else SYSTEM_PROMPT
    messages: list[dict] = [{"role": "system", "content": system}]

    # Inject conversation history (oldest turn first, after system prompt)
    for turn in conversation_history:
        messages.append({"role": turn["role"], "content": turn["content"]})

    # Build the current-turn user content block
    user_content = _build_analysis_block(analysis, track_metadata, user_question)

    # Trim oldest history turns if we'd exceed the context budget
    messages = _trim_to_budget(messages, user_content)
    messages.append({"role": "user", "content": user_content})

    return messages


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_analysis_block(
    analysis: dict, track_metadata: dict, question: str
) -> str:
    """
    Format the DSP analysis and track metadata into a structured plain-text
    block that the LLM can parse and reason over.
    """
    parts: list[str] = []

    # ── Track overview ────────────────────────────────────────────────────────
    name   = track_metadata.get("name", "Unknown Track")
    vol_db = track_metadata.get("volume_db", 0.0)
    pan    = track_metadata.get("pan", 0.0)
    bpm    = track_metadata.get("project_bpm", "?")
    sr     = track_metadata.get("project_sr", "?")
    muted  = track_metadata.get("muted", False)
    soloed = track_metadata.get("soloed", False)

    state_parts = []
    if muted:  state_parts.append("MUTED")
    if soloed: state_parts.append("SOLOED")
    state_str = f" [{', '.join(state_parts)}]" if state_parts else ""

    parts.append(
        f"TRACK: {name}{state_str} | Vol: {vol_db:.1f} dBFS | Pan: {pan:+.2f}"
        f" | Project: {bpm} BPM @ {sr} Hz"
    )

    # ── FX chain ──────────────────────────────────────────────────────────────
    fx_chain = track_metadata.get("fx_chain", [])
    if fx_chain:
        fx_lines = []
        for fx in fx_chain:
            status = "" if fx.get("enabled", True) else " [BYPASSED]"
            # Include up to 12 params per plugin; skip unnamed params
            params = [
                p for p in fx.get("params", [])[:12]
                if p.get("name")
            ]
            p_str = " | ".join(
                f"{p['name']}: {p.get('display', str(round(p.get('value', 0), 3)))}"
                for p in params
            )
            fx_lines.append(f"  · {fx.get('name', '?')}{status}: {p_str}")
        parts.append("FX CHAIN:\n" + "\n".join(fx_lines))
    else:
        parts.append("FX CHAIN: none / not provided")

    # ── Spectral ──────────────────────────────────────────────────────────────
    if "spectral_centroid_hz" in analysis:
        be = analysis.get("band_energy", {})
        parts.append(
            f"SPECTRUM: centroid={analysis['spectral_centroid_hz']:.0f} Hz"
            f" | bandwidth={analysis.get('spectral_bandwidth_hz', 0):.0f} Hz"
            f" | rolloff={analysis.get('spectral_rolloff_hz', 0):.0f} Hz\n"
            f"  Bands → "
            f"sub 20-60 Hz={be.get('sub_20_60', 0)*100:.1f}% | "
            f"low 60-200 Hz={be.get('low_60_200', 0)*100:.1f}% | "
            f"lo-mid 200-500 Hz={be.get('low_mid_200_500', 0)*100:.1f}% | "
            f"mid 500-2k Hz={be.get('mid_500_2k', 0)*100:.1f}% | "
            f"hi-mid 2k-5k Hz={be.get('upper_mid_2k_5k', 0)*100:.1f}% | "
            f"high 5k-10k Hz={be.get('high_5k_10k', 0)*100:.1f}% | "
            f"air 10k-20k Hz={be.get('air_10k_20k', 0)*100:.1f}%"
        )

    # ── Spectral balance vs commercial reference ───────────────────────────────
    if "spectral_balance_vs_reference" in analysis:
        bal   = analysis["spectral_balance_vs_reference"]
        score = analysis.get("overall_balance_score", "?")
        label = analysis.get("overall_balance_label", "")
        over  = [b for b, v in bal.items() if v.get("deviation_pct", 0) > 6]
        under = [b for b, v in bal.items() if v.get("deviation_pct", 0) < -6]
        bal_line = f"SPECTRAL BALANCE vs REFERENCE: score={score} ({label})"
        if over:  bal_line += f"\n  Over-reference: {', '.join(over)}"
        if under: bal_line += f"\n  Under-reference: {', '.join(under)}"
        parts.append(bal_line)

    # ── Tonal flags (muddiness / harshness / boxiness / rumble) ───────────────
    if "tonal_balance" in analysis:
        tb     = analysis["tonal_balance"]
        flags  = [k.upper() for k, v in tb.items() if v]
        parts.append("TONAL FLAGS: " + (", ".join(flags) if flags else "none detected"))

    # ── Dynamics + clipping ───────────────────────────────────────────────────
    if "rms_db" in analysis:
        parts.append(
            f"DYNAMICS: RMS={analysis['rms_db']:.1f} dBFS"
            f" | Peak={analysis.get('peak_db', 0):.1f} dBFS"
            f" | Crest factor={analysis.get('crest_factor_db', 0):.1f} dB"
        )
    clip_sev = analysis.get("clip_severity", "none")
    if clip_sev and clip_sev != "none":
        parts.append(
            f"CLIPPING: {clip_sev}"
            f" | {analysis.get('clip_ratio_pct', 0):.3f}% of samples clipped"
            f" | True peak: {analysis.get('true_peak_dbfs', 0):.1f} dBFS"
        )

    # ── Loudness (LUFS) ───────────────────────────────────────────────────────
    if "loudness" in analysis:
        ld   = analysis["loudness"]
        lufs = ld.get("lufs_integrated")
        if lufs is not None:
            deltas   = ld.get("platform_deltas", {})
            sp_delta = deltas.get("spotify", {}).get("delta_db")
            yt_delta = deltas.get("youtube", {}).get("delta_db")
            am_delta = deltas.get("apple_music", {}).get("delta_db")
            delta_str = ""
            if sp_delta is not None: delta_str += f" | Δ Spotify: {sp_delta:+.1f} dB"
            if yt_delta is not None: delta_str += f" | Δ YouTube: {yt_delta:+.1f} dB"
            if am_delta is not None: delta_str += f" | Δ Apple Music: {am_delta:+.1f} dB"
            parts.append(
                f"LOUDNESS: {lufs:.1f} LUFS integrated | {ld.get('lufs_status', '')}{delta_str}"
            )
        else:
            parts.append(f"LOUDNESS: {ld.get('lufs_status', 'not measurable')}")

    # ── Noise floor / SNR ─────────────────────────────────────────────────────
    if "noise" in analysis:
        nf = analysis["noise"]
        if nf.get("noise_floor_db") is not None:
            parts.append(
                f"NOISE FLOOR: {nf['noise_floor_db']:.1f} dBFS"
                f" | SNR: {nf.get('snr_db', '?'):.1f} dB"
                f" | {nf.get('noise_label', '')}"
            )
        else:
            parts.append(f"NOISE FLOOR: {nf.get('noise_label', 'not measurable')}")

    # ── Reverb (RT60) ─────────────────────────────────────────────────────────
    if "reverb" in analysis:
        rv   = analysis["reverb"]
        rt60 = rv.get("rt60_seconds")
        rt60_str = f"{rt60:.3f}s" if rt60 is not None else "N/A (tail too long or continuous signal)"
        parts.append(f"REVERB: RT60={rt60_str} | {rv.get('reverb_label', '')}")

    # ── Transients ────────────────────────────────────────────────────────────
    if "transients" in analysis:
        tr  = analysis["transients"]
        atk = tr.get("avg_attack_ms")
        dec = tr.get("avg_decay_ms")
        tr_line = (
            f"TRANSIENTS: {tr.get('density', '?')} density"
            f" | {tr.get('onsets_per_second', 0):.1f} onsets/s"
            f" | percussive ratio={tr.get('percussive_ratio', 0):.2f}"
        )
        if atk is not None: tr_line += f" | avg attack={atk:.1f}ms"
        if dec is not None: tr_line += f" | avg decay={dec:.1f}ms"
        parts.append(tr_line)

    # ── Harmonic distortion (THD) ─────────────────────────────────────────────
    if "distortion" in analysis:
        dt  = analysis["distortion"]
        f0  = dt.get("fundamental_hz")
        thd = dt.get("thd_ratio")
        if f0 is not None and thd is not None:
            parts.append(
                f"DISTORTION: fundamental={f0:.1f} Hz"
                f" | THD={thd:.4f} ({thd*100:.2f}%)"
                f" | {dt.get('thd_label', '')}"
            )

    # ── Musical (BPM + key) ───────────────────────────────────────────────────
    if "musical" in analysis:
        m = analysis["musical"]
        parts.append(f"MUSICAL: BPM={m.get('bpm', '?')} | Key={m.get('key', '?')}")

    # ── Stereo field ──────────────────────────────────────────────────────────
    if "stereo" in analysis:
        s      = analysis["stereo"]
        interp = s.get("interpretation", {})
        parts.append(
            f"STEREO: width={s.get('stereo_width', 0):.3f} ({interp.get('width_label', '?')})"
            f" | mono compat={s.get('mono_compatibility_score', 0):.3f}"
            f" ({interp.get('mono_compat_label', '?')})"
            f" | LR balance: {interp.get('balance_label', '?')}"
        )

    parts.append(f"\nUSER QUESTION: {question}")
    return "\n".join(parts)


def _trim_to_budget(messages: list[dict], new_user_content: str) -> list[dict]:
    """
    Drop the oldest history turns (index 1, after system prompt) until the
    total estimated character count fits within _MAX_CONTEXT_CHARS.

    The system prompt is never dropped.
    """
    total = sum(len(m["content"]) for m in messages) + len(new_user_content)

    # Pop oldest non-system turns (index 1) until we're within budget
    while total > _MAX_CONTEXT_CHARS and len(messages) > 1:
        removed = messages.pop(1)
        total  -= len(removed["content"])

    return messages
