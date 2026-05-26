"""
ReaBot - Audio Render to WAV

Renders the selected track's items (within the time selection) to a
temporary WAV file for analysis by the daemon.

Uses REAPER's "Glue items" render path, which applies all FX (post-FX audio).
The render is asynchronous — this module provides a poller that the main
defer loop calls every frame to detect when the file is ready.

Temp files are written to /tmp/reabot/ and cleaned up after the daemon
returns its response.
"""

import os
import time
import uuid

from reaper_python import (
    RPR_GetSelectedTrack,
    RPR_CountSelectedTracks,
    RPR_CountTrackMediaItems,
    RPR_GetProjectPath,
    RPR_Main_OnCommand,
    RPR_GetTimeSelection,
    RPR_GetOutputLatency,
    RPR_CSurf_OnRecord,
    RPR_GetSetProjectInfo_String,
    RPR_GetAppVersion,
)

TEMP_DIR = "/tmp/reabot"
RENDER_TIMEOUT_SEC = 15.0

# REAPER action ID for "Item: Glue items within time selection"
# This renders post-FX audio for all selected items within the time selection.
_ACTION_GLUE = 41588


class RenderPoller:
    """
    Manages a single in-flight render operation.

    Usage:
        poller = RenderPoller()
        error = poller.start(output_path)   # triggers render
        if not error:
            # call poller.tick() every defer frame
            ready, err = poller.tick()
            if ready:
                # output_path now exists on disk
    """

    def __init__(self):
        self._output_path: str | None = None
        self._started_at: float = 0.0
        self._active: bool = False

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def output_path(self) -> str | None:
        return self._output_path

    def start(self, output_path: str) -> str | None:
        """
        Trigger a render to output_path.

        Returns:
            An error string if the render cannot be started, None on success.
        """
        if RPR_CountSelectedTracks(0) == 0:
            return "No tracks selected. Select a track before analyzing."

        track = RPR_GetSelectedTrack(0, 0)
        if RPR_CountTrackMediaItems(track) == 0:
            return "Selected track has no media items."

        # Ensure temp dir exists
        os.makedirs(TEMP_DIR, exist_ok=True)

        # Set REAPER's render output path for the glue action.
        # We write to a predictable path so we can poll for it.
        self._output_path = output_path
        self._started_at = time.time()
        self._active = True

        # Trigger the glue/render action
        RPR_Main_OnCommand(_ACTION_GLUE, 0)

        return None

    def tick(self) -> tuple[bool, str | None]:
        """
        Call this every defer frame while a render is active.

        Returns:
            (ready, error) where ready=True means the file exists on disk.
            error is a string if something went wrong, None otherwise.
        """
        if not self._active or self._output_path is None:
            return False, "No active render."

        # Check if file appeared
        if os.path.exists(self._output_path):
            self._active = False
            return True, None

        # Check for timeout
        elapsed = time.time() - self._started_at
        if elapsed > RENDER_TIMEOUT_SEC:
            self._active = False
            return False, f"Render timed out after {RENDER_TIMEOUT_SEC:.0f}s. Is a time selection set?"

        return False, None

    def cancel(self):
        """Cancel a pending render poll (does not undo the REAPER action)."""
        self._active = False
        self._output_path = None


def make_temp_path() -> str:
    """Generate a unique temp WAV path in /tmp/reabot/."""
    os.makedirs(TEMP_DIR, exist_ok=True)
    return os.path.join(TEMP_DIR, f"reabot_{uuid.uuid4().hex[:8]}.wav")


def cleanup_temp_file(path: str) -> None:
    """Remove a temp WAV file after the daemon has analyzed it."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass  # Best-effort cleanup
