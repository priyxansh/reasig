# ReaBot 

**AI Mix & Production Assistant for REAPER (Linux)**

ReaBot is a native AI-powered mixing assistant that runs inside [REAPER](https://www.reaper.fm/) as a floating chat window. It analyzes your audio tracks using professional DSP algorithms, feeds the results to LLM models via [OpenRouter](https://openrouter.ai/), and returns specific, actionable mixing advice — referencing your actual plugin chains and exact parameter values.

## Features

-  **Deep Audio Analysis** — Spectral centroid, frequency band energy, Crest Factor, transient density, key/chord detection via `librosa`
-  **Plugin-Aware Advice** — Reads your ReaEQ, ReaComp, and other FX parameters and references them in suggestions
-  **LLM-Powered Intelligence** — Uses free-tier models (Llama 3.1 70B, Mistral 7B) via OpenRouter for expert mixing advice
-  **Streaming Chat** — Responses stream in real-time inside a ReaImGui floating window
-  **Multi-Track Masking Detection** — Identifies frequency conflicts between tracks
-  **Thread-Safe Architecture** — Decoupled daemon process ensures REAPER never hangs

## Architecture

```
REAPER (ReaImGui + ReaScript)  ←→  TCP Socket  ←→  ReaBot Daemon (librosa + OpenRouter)
```

- **UI Layer**: ReaImGui (Dear ImGui bindings for REAPER)
- **DSP Layer**: librosa + scipy (offline spectral/temporal analysis)
- **API Layer**: Decoupled Python daemon with async OpenRouter streaming

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/priyxansh/reabot.git
cd reabot
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
#    - Actions → Load ReaScript → select reascript/reabot_main.py
#    - Run the action to open the chat window
```

## Requirements

- **REAPER** (v6.0+) on Linux
- **Python** ≥ 3.9
- **ReaImGui** extension (install via ReaPack)
- **OpenRouter API key** (free tier works — [get one here](https://openrouter.ai/keys))

## Project Structure

```
reabot/
├── daemon/              # Standalone Python daemon process
│   ├── dsp/             # Audio analysis modules (librosa-based)
│   ├── llm/             # OpenRouter API client & prompt engineering
│   ├── server.py        # Async TCP server
│   ├── protocol.py      # JSON-lines IPC protocol
│   └── config.py        # Configuration management
├── reascript/           # Runs inside REAPER's Python environment
│   ├── ui/              # ReaImGui chat window
│   ├── bridge/          # TCP client to daemon
│   └── extraction/      # Track metadata & audio export
├── tests/               # Unit tests
├── requirements.txt     # Daemon Python dependencies
└── setup.sh             # One-shot setup script
```

## License

MIT
