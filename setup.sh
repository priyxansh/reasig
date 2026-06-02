#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "╔══════════════════════════════════════╗"
echo "║       ReaSig Setup Script            ║"
echo "║  AI Mix Assistant for REAPER         ║"
echo "╚══════════════════════════════════════╝"
echo ""

# --- Check Python version ---
PYTHON_CMD=""
for cmd in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$cmd" &>/dev/null; then
        PY_VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        PY_MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)")
        PY_MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)")
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 9 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo " Error: Python >= 3.9 is required but not found."
    echo "   Please install Python 3.9+ and try again."
    exit 1
fi

echo " Found Python: $PYTHON_CMD ($PY_VER)"

# --- Create virtual environment ---
if [ ! -d "$VENV_DIR" ]; then
    echo " Creating virtual environment at $VENV_DIR ..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo " Virtual environment created."
else
    echo " Virtual environment already exists."
fi

# --- Activate and install dependencies ---
source "$VENV_DIR/bin/activate"
echo " Installing daemon dependencies..."
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt" -q
echo " Dependencies installed."

# --- Check for .env file ---
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo ""
    echo "  No .env file found. Copying from .env.example..."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    echo " Please edit .env and add your OpenRouter API key:"
    echo "   $SCRIPT_DIR/.env"
else
    echo " .env file exists."
fi

# --- Check REAPER installation ---
REAPER_CONFIG="$HOME/.config/REAPER"
if [ -d "$REAPER_CONFIG" ]; then
    echo " REAPER config found at $REAPER_CONFIG"

    # Check for ReaImGui
    if find "$REAPER_CONFIG/UserPlugins" -name "*reaimgui*" -o -name "*ReaImGui*" 2>/dev/null | grep -q .; then
        echo " ReaImGui extension detected."
    else
        echo ""
        echo "  ReaImGui not found. You need to install it via ReaPack:"
        echo "   1. Open REAPER"
        echo "   2. Extensions → ReaPack → Browse packages"
        echo "   3. Search for 'ReaImGui'"
        echo "   4. Right-click → Install"
        echo "   5. Restart REAPER"
    fi
else
    echo "  REAPER config directory not found at $REAPER_CONFIG"
    echo "   Make sure REAPER is installed and has been run at least once."
fi

echo ""
echo "╔══════════════════════════════════════╗"
echo "║          Setup Complete!             ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your OpenRouter API key"
echo "  2. Start the daemon:"
echo "     - Bash/Zsh: source .venv/bin/activate && python -m daemon"
echo "     - Fish:     source .venv/bin/activate.fish; and python -m daemon"
echo "  3. In REAPER: Actions → Load ReaScript → select reascript/reasig_main.py"
echo ""
