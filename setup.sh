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

# --- Validate or recreate virtual environment ---
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP_BIN="$VENV_DIR/bin/pip"
VENV_STALE=false

if [ -d "$VENV_DIR" ]; then
    # Check 1: Python binary must be executable and runnable
    if [ ! -x "$VENV_PYTHON" ] || ! "$VENV_PYTHON" -c "import sys" &>/dev/null 2>&1; then
        VENV_STALE=true
    fi

    # Check 2: pip shebang interpreter must exist on disk
    if [ -f "$VENV_PIP_BIN" ]; then
        PIP_INTERP=$(head -1 "$VENV_PIP_BIN" | sed 's/^#!//')
        if [ -n "$PIP_INTERP" ] && [ ! -x "$PIP_INTERP" ]; then
            VENV_STALE=true
        fi
    fi

    if [ "$VENV_STALE" = true ]; then
        echo " Existing virtual environment is stale (broken interpreter path) — recreating..."
        rm -rf "$VENV_DIR"
    else
        echo " Virtual environment OK."
    fi
fi

if [ ! -d "$VENV_DIR" ] || [ "$VENV_STALE" = true ]; then
    echo " Creating virtual environment at $VENV_DIR ..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo " Virtual environment created."
fi

# Use the venv's own pip directly to avoid any PATH confusion
VENV_PIP="$VENV_DIR/bin/pip"

echo " Installing daemon dependencies..."
"$VENV_PIP" install --upgrade pip -q
"$VENV_PIP" install -r "$SCRIPT_DIR/requirements.txt" -q
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

# --- Check REAPER installation and set up symlink ---
REAPER_CONFIG="$HOME/.config/REAPER"
REAPER_SCRIPTS="$REAPER_CONFIG/Scripts"
SYMLINK_NAME="reasig"
SYMLINK_PATH="$REAPER_SCRIPTS/$SYMLINK_NAME"
REASCRIPT_DIR="$SCRIPT_DIR/reascript"

if [ -d "$REAPER_CONFIG" ]; then
    echo " REAPER config found at $REAPER_CONFIG"

    # Check for ReaImGui — the plugin .so lives in UserPlugins as reaper_imgui-*.so
    if find "$REAPER_CONFIG/UserPlugins" \
        \( -name "reaper_imgui*" -o -name "*reaimgui*" -o -name "*ReaImGui*" \) \
        2>/dev/null | grep -q .; then
        echo " ReaImGui extension detected."
    else
        echo ""
        echo "  ReaImGui not found. You need to install it via ReaPack:"
        echo "   1. Open REAPER"
        echo "   2. Extensions → ReaPack → Browse packages"
        echo "   3. Search for 'ReaImGui'"
        echo "   4. Right-click → Install"
        echo "   5. Restart REAPER"
        echo ""
    fi

    # --- Set up Scripts symlink ---
    mkdir -p "$REAPER_SCRIPTS"

    if [ -L "$SYMLINK_PATH" ]; then
        CURRENT_TARGET="$(readlink "$SYMLINK_PATH")"
        if [ "$CURRENT_TARGET" = "$REASCRIPT_DIR" ]; then
            echo " Symlink already correct: $SYMLINK_PATH → $REASCRIPT_DIR"
        else
            echo " Updating symlink (was pointing to $CURRENT_TARGET)..."
            ln -sf "$REASCRIPT_DIR" "$SYMLINK_PATH"
            echo " Symlink updated: $SYMLINK_PATH → $REASCRIPT_DIR"
        fi
    elif [ -e "$SYMLINK_PATH" ]; then
        echo "  $SYMLINK_PATH exists but is not a symlink — skipping."
        echo "   Remove it manually and re-run setup if you want the symlink created."
    else
        ln -s "$REASCRIPT_DIR" "$SYMLINK_PATH"
        echo " Symlink created: $SYMLINK_PATH → $REASCRIPT_DIR"
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
echo "  3. In REAPER: Actions → Load ReaScript → select reascript/reasig_main.lua"
echo "     (or via the symlink: Scripts/reasig/reasig_main.lua)"
echo ""
