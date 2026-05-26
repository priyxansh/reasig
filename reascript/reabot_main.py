"""
ReaBot - Main Entry Point

This file is loaded by REAPER as a ReaScript. It owns the defer loop
and wires together all components:

  - DaemonClient: non-blocking TCP bridge to the Python daemon
  - ChatWindow: ReaImGui floating window
  - RenderPoller: waits for the async WAV render to complete
  - Extraction modules: track metadata, FX chain

To run: Actions -> Load ReaScript -> select this file
To stop: Run it again (toggle) or close the ReaBot window.

Requires:
  - ReaImGui installed via ReaPack
  - ReaBot daemon running (python -m daemon from the project root)
"""

import sys
import os
import json
import uuid

# Ensure the reascript package and its sibling dirs are importable
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Also add the ReaTeam Extensions API path for imgui.py
_IMGUI_PATH = os.path.expanduser(
    "~/.config/REAPER/Scripts/ReaTeam Extensions/API"
)
if _IMGUI_PATH not in sys.path:
    sys.path.insert(0, _IMGUI_PATH)

import imgui
from reaper_python import RPR_defer, RPR_ShowConsoleMsg

from reascript.bridge.daemon_client import DaemonClient
from reascript.ui.chat_window import ChatWindow
from reascript.ui.theme import apply_theme, THEME_COLOR_COUNT, THEME_VAR_COUNT
from reascript.extraction.track_info import get_track_context
from reascript.extraction.fx_chain import get_selected_tracks_fx
from reascript.extraction.audio_render import RenderPoller, make_temp_path, cleanup_temp_file

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DAEMON_HOST = "127.0.0.1"
DAEMON_PORT = 9876

# ---------------------------------------------------------------------------
# Global state (lives across defer frames for the duration of the session)
# ---------------------------------------------------------------------------
_ctx = None           # ReaImGui context
_window = ChatWindow()
_client = DaemonClient(DAEMON_HOST, DAEMON_PORT)
_poller = RenderPoller()
_open = True          # Window open flag

# State for the current in-flight request
_pending_request_id: str | None = None
_pending_wav_path: str | None = None
_pending_prompt: str | None = None
_pending_stereo: bool = False
_streaming_msg_index: int = -1

# ---------------------------------------------------------------------------
# Daemon message handlers
# ---------------------------------------------------------------------------

def _on_response_chunk(msg: dict) -> None:
    """A token arrived from the LLM. Append to the streaming message."""
    global _streaming_msg_index
    if _streaming_msg_index >= 0:
        _window.append_chunk(_streaming_msg_index, msg.get("payload", {}).get("content", ""))


def _on_response_done(msg: dict) -> None:
    """LLM response is complete."""
    global _streaming_msg_index, _pending_request_id
    if _streaming_msg_index >= 0:
        _window.finish_streaming(_streaming_msg_index)
    _streaming_msg_index = -1
    _pending_request_id = None
    _window.set_status("Ready")
    # Clean up the temp WAV file
    if _pending_wav_path:
        cleanup_temp_file(_pending_wav_path)


def _on_analysis_result(msg: dict) -> None:
    """
    Raw analysis result (no LLM handler registered in daemon yet — Phase 4).
    Display a summary so the UI isn't blank during Phase 3.
    """
    global _streaming_msg_index, _pending_request_id
    analysis = msg.get("payload", {}).get("analysis", {})
    summary_parts = []
    if "rms_db" in analysis:
        summary_parts.append(f"RMS: {analysis['rms_db']:.1f} dB")
    if "spectral_centroid_hz" in analysis:
        summary_parts.append(f"Centroid: {analysis['spectral_centroid_hz']:.0f} Hz")
    if "musical" in analysis:
        m = analysis["musical"]
        summary_parts.append(f"BPM: {m.get('bpm', '?')} | Key: {m.get('key', '?')}")
    if "stereo" in analysis:
        s = analysis["stereo"]
        summary_parts.append(f"Width: {s.get('stereo_width', 0):.2f} | Compat: {s.get('mono_compatibility_score', 1):.2f}")

    if summary_parts:
        result_text = "Analysis complete (LLM not yet active):\n" + "\n".join(f"  {p}" for p in summary_parts)
    else:
        result_text = "Analysis complete. No metrics returned."

    if _streaming_msg_index >= 0:
        _window.append_chunk(_streaming_msg_index, result_text)
        _window.finish_streaming(_streaming_msg_index)

    _streaming_msg_index = -1
    _pending_request_id = None
    _window.set_status("Ready")
    if _pending_wav_path:
        cleanup_temp_file(_pending_wav_path)


def _on_error(msg: dict) -> None:
    """Daemon returned an error."""
    global _streaming_msg_index, _pending_request_id
    error = msg.get("payload", {}).get("error", "Unknown error")
    _window.add_system_message(f"Error: {error}")
    if _streaming_msg_index >= 0:
        _window.finish_streaming(_streaming_msg_index)
    _streaming_msg_index = -1
    _pending_request_id = None
    _window.set_status("Error")
    if _pending_wav_path:
        cleanup_temp_file(_pending_wav_path)


# Register handlers
_client.on("response_chunk",   _on_response_chunk)
_client.on("response_done",    _on_response_done)
_client.on("analysis_result",  _on_analysis_result)
_client.on("error",            _on_error)

# ---------------------------------------------------------------------------
# UI callbacks
# ---------------------------------------------------------------------------

def _handle_analyze(prompt: str, stereo: bool) -> None:
    """
    User clicked Analyze:
    1. Extract track metadata + FX chain.
    2. Start WAV render.
    3. Wait for render to complete (poller.tick()).
    4. Send analyze_track request to daemon.
    """
    global _pending_prompt, _pending_stereo, _pending_wav_path, _streaming_msg_index

    _pending_prompt = prompt
    _pending_stereo = stereo
    _pending_wav_path = make_temp_path()

    error = _poller.start(_pending_wav_path)
    if error:
        _window.add_system_message(f"Cannot render: {error}")
        _window.set_status("Ready")
        return

    _streaming_msg_index = _window.add_assistant_message()
    _window.set_status("Rendering...")


def _handle_chat(prompt: str) -> None:
    """User clicked Chat (no audio — just a follow-up question)."""
    global _streaming_msg_index, _pending_request_id

    request_id = str(uuid.uuid4())
    _pending_request_id = request_id
    _streaming_msg_index = _window.add_assistant_message()

    _client.send_message({
        "type": "chat",
        "id": request_id,
        "payload": {
            "user_message": prompt,
        }
    })
    _window.set_status("Waiting for response...")


_window.on_analyze = _handle_analyze
_window.on_chat = _handle_chat

# ---------------------------------------------------------------------------
# Setup ImGui context
# ---------------------------------------------------------------------------

def _setup() -> None:
    global _ctx
    _ctx = imgui.CreateContext("ReaBot")
    imgui.Attach(_ctx, imgui.GetBuiltinFont())
    apply_theme(_ctx)


_setup()

# ---------------------------------------------------------------------------
# Main defer loop
# ---------------------------------------------------------------------------

def _loop() -> None:
    global _open, _pending_wav_path, _pending_prompt, _pending_stereo
    global _streaming_msg_index, _pending_request_id

    if not _open:
        # Window was closed — clean up and stop the defer loop
        imgui.DestroyContext(_ctx)
        return

    # 1. Tick the daemon client (non-blocking socket I/O)
    was_connected = _client.is_connected
    _client.tick()
    now_connected = _client.is_connected

    if was_connected != now_connected:
        _window.set_connected(now_connected)
        if now_connected:
            _window.set_status("Ready")
        else:
            _window.set_status("Daemon not connected — start the daemon first")

    # 2. Tick the render poller
    if _poller.is_active:
        ready, render_error = _poller.tick()
        if render_error:
            _window.add_system_message(f"Render failed: {render_error}")
            _window.finish_streaming(_streaming_msg_index)
            _streaming_msg_index = -1
            _window.set_status("Ready")
            _pending_wav_path = None
        elif ready:
            # Render done — gather metadata and send to daemon
            _window.set_status("Analyzing...")
            track_context = get_track_context()
            fx_data = get_selected_tracks_fx()

            # Merge FX data into track context
            for i, track in enumerate(track_context.get("selected_tracks", [])):
                if i < len(fx_data):
                    track["fx_chain"] = fx_data[i].get("fx_chain", [])

            request_id = str(uuid.uuid4())
            _pending_request_id = request_id

            _client.send_message({
                "type": "analyze_track",
                "id": request_id,
                "payload": {
                    "wav_path": _pending_wav_path,
                    "track_metadata": track_context,
                    "user_question": _pending_prompt or "",
                    "stereo": _pending_stereo,
                }
            })

    # 3. Draw UI
    imgui.SetNextWindowPos(_ctx, 100, 100, imgui.Cond_FirstUseEver())
    _open = _window.draw(_ctx)

    # 4. Reschedule
    RPR_defer("_loop()")


# Start the loop
_loop()
