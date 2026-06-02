# ReaSig

**DSP Track Analyser & AI Mix Assistant for REAPER**

ReaSig is a REAPER utility that analyses your audio tracks using professional DSP algorithms and translates the results into specific, actionable mixing advice — powered by LLMs via [OpenRouter](https://openrouter.ai/). It runs as a floating chat window inside REAPER, referencing your actual plugin chains, exact parameter values, and measured signal characteristics.

## Features

- **DSP-First Analysis** — Spectral balance, loudness (LUFS), dynamics, transients, stereo width, harmonic distortion, reverb tails, muddiness, and masking — all measured, not guessed
- **Plugin-Aware Advice** — Reads your ReaEQ, ReaComp, and other FX parameters and references them directly in suggestions
- **LLM-Powered Intelligence** — Uses models via [OpenRouter](https://openrouter.ai/) (free tier works) for expert mixing guidance grounded in your actual signal data
- **Streaming Chat** — Responses stream in real-time inside a ReaImGui floating window
- **Session Persistence** — Conversation history is stored in SQLite and survives daemon restarts
- **Thread-Safe Architecture** — Decoupled daemon process ensures REAPER never hangs during analysis or LLM calls

## DSP Features

ReaSig employs a suite of purpose-built audio analysis modules to extract meaningful data from your tracks:

- **Spectrum Analysis** (`librosa`) — Calculates spectral centroid, rolloff, and energy distribution across sub, bass, mid, and treble bands.
- **Loudness & Metering** (`pyloudnorm`) — Accurately measures Integrated LUFS, Short-term LUFS, and True Peak levels to broadcast standards.
- **Dynamics** (`numpy`) — Computes crest factor and Peak-to-RMS ratios to evaluate how compressed or dynamic a signal is.
- **Transients** (`librosa` & `numpy`) — Detects onset events and measures attack sharpness to gauge punchiness.
- **Stereo Width** (`numpy`) — Analyzes Mid/Side correlation to determine spatial spread and phase coherence.
- **Harmonic Distortion** (`numpy`) — Estimates Total Harmonic Distortion (THD) by analyzing overtones relative to the fundamental.
- **Reverb & Tails** (`numpy`) — Measures decay times to detect lingering tails and assess room ambiance.
- **Musicality** (`librosa`) — Estimates track key and tempo (BPM) for context-aware mixing decisions.
- **Noise Floor** (`numpy`) — Estimates the background noise level during quiet passages.
- **Muddiness & Masking** — Evaluates lower-midrange buildup and potential frequency clashes between multiple tracks.

## Architecture

```text
                  [Track Metadata & Audio Path]
  REAPER (Lua)  ─────────────────────────────────►  ReaSig Daemon (Python)
 (ReaImGui UI)  ◄─────────────────────────────────  (DSP Math + OpenRouter)
                     [Streaming LLM Text Chunks]
```

- **UI Layer**: ReaImGui (Dear ImGui bindings for REAPER)
- **DSP Layer**: Offline spectral/temporal analysis engine
- **API Layer**: Decoupled Python daemon with async OpenRouter streaming
- **Persistence Layer**: SQLite database for session history and memory across restarts

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/priyxansh/reasig.git
cd reasig
chmod +x setup.sh && ./setup.sh

# 2. Add your OpenRouter API key
#    Edit .env and set OPENROUTER_API_KEY=sk-or-v1-...

# 3. Start the daemon
# Bash/Zsh:
source .venv/bin/activate
python -m daemon

# Fish shell:
source .venv/bin/activate.fish
python -m daemon

# 4. In REAPER:
#    - Install ReaImGui via ReaPack (Extensions → ReaPack → Browse → search "ReaImGui")
#    - Actions → Load ReaScript → select reascript/reasig_main.lua
#    - Run the action to open the chat window
```

## Requirements

- **REAPER** (v6.0+)
- **Python** ≥ 3.9
- **ReaImGui** extension (install via ReaPack)
- **OpenRouter API key** (free tier works — [get one here](https://openrouter.ai/keys))

## Project Structure

```text
reasig/
├── daemon/                 # Standalone Python daemon process
│   ├── dsp/                # Audio analysis algorithms
│   ├── llm/                # OpenRouter API client & prompt engineering
│   ├── __main__.py         # Daemon entry point
│   ├── server.py           # Async TCP server
│   ├── session.py          # SQLite database & chat history manager
│   ├── protocol.py         # JSON-lines IPC protocol
│   └── config.py           # Configuration management
├── reascript/              # Runs inside REAPER
│   ├── reasig_main.lua     # Main action entry script
│   ├── ui/                 # ReaImGui chat window
│   ├── bridge/             # TCP socket client to daemon
│   ├── extraction/         # Track & FX metadata extraction
│   ├── render/             # Async background audio rendering
│   └── lib/                # Third-party Lua libraries (e.g. dkjson)
├── tests/                  # Unit tests
├── requirements.txt        # Daemon Python dependencies
└── setup.sh                # One-shot setup script
```

## License

MIT
