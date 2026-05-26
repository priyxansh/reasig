"""
ReaBot - Chat Window

Draws the main ReaBot floating window using ReaImGui.
Called every defer frame by reabot_main.py.

The window has four sections:
  1. Header bar — title, connection status, stereo toggle
  2. Chat history — scrollable, streams AI responses token by token
  3. Status bar — current operation state
  4. Input area — text input + Analyze + Chat buttons
"""

from typing import Callable, Optional

import imgui
from .theme import (
    COLOR_USER_MSG, COLOR_AI_MSG,
    COLOR_STATUS_OK, COLOR_STATUS_ERR, COLOR_STATUS_BUSY,
    COLOR_MUTED, COLOR_WARNING,
)

# Window size defaults (user can resize)
WINDOW_W = 480
WINDOW_H = 600


class ChatMessage:
    """A single message in the conversation history."""
    __slots__ = ("role", "content", "streaming")

    def __init__(self, role: str, content: str, streaming: bool = False):
        self.role = role          # "user" | "assistant" | "system"
        self.content = content
        self.streaming = streaming  # True while tokens are still arriving


class ChatWindow:
    """
    Owns the chat window state and draws it each frame.

    State that persists across frames:
    - messages: the conversation history list
    - input_buf: the current text in the input field
    - stereo_enabled: the stereo toggle state
    - status: current status string shown in the status bar
    - _scroll_to_bottom: flag set when a new message arrives
    """

    def __init__(self):
        self.messages: list[ChatMessage] = []
        self.input_buf = ""
        self.stereo_enabled = False
        self.status = "Ready"
        self._scroll_to_bottom = False

        # Callbacks wired by reabot_main.py
        self.on_analyze: Optional[Callable[[str, bool], None]] = None   # called with (prompt: str, stereo: bool)
        self.on_chat: Optional[Callable[[str], None]] = None      # called with (prompt: str)

    # ------------------------------------------------------------------
    # Public API used by reabot_main.py
    # ------------------------------------------------------------------

    def add_user_message(self, text: str) -> None:
        self.messages.append(ChatMessage("user", text))
        self._scroll_to_bottom = True

    def add_assistant_message(self) -> int:
        """Start a new (empty) streaming assistant message. Returns its index."""
        self.messages.append(ChatMessage("assistant", "", streaming=True))
        self._scroll_to_bottom = True
        return len(self.messages) - 1

    def append_chunk(self, index: int, chunk: str) -> None:
        """Append a streaming token to an existing assistant message."""
        if 0 <= index < len(self.messages):
            self.messages[index].content += chunk
            self._scroll_to_bottom = True

    def finish_streaming(self, index: int) -> None:
        """Mark an assistant message as fully received."""
        if 0 <= index < len(self.messages):
            self.messages[index].streaming = False

    def add_system_message(self, text: str) -> None:
        """Add an inline system/error message."""
        self.messages.append(ChatMessage("system", text))
        self._scroll_to_bottom = True

    def set_status(self, status: str) -> None:
        self.status = status

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, ctx) -> bool:
        """
        Draw the window for this frame.

        Args:
            ctx: ReaImGui context.

        Returns:
            False if the window was closed (p_open became False), True otherwise.
        """
        imgui.SetNextWindowSize(ctx, WINDOW_W, WINDOW_H, imgui.Cond_FirstUseEver())
        imgui.SetNextWindowSizeConstraints(ctx, 320, 400, 800, 1200)

        visible, p_open = imgui.Begin(ctx, "ReaBot", True)
        if not visible:
            imgui.End(ctx)
            return p_open

        self._draw_header(ctx)
        imgui.Separator(ctx)

        self._draw_chat_history(ctx)
        imgui.Separator(ctx)

        self._draw_status_bar(ctx)
        imgui.Separator(ctx)

        self._draw_input_area(ctx)

        imgui.End(ctx)
        return p_open

    def _draw_header(self, ctx) -> None:
        """Title + connection indicator + stereo toggle on one line."""
        # Title
        imgui.Text(ctx, "ReaBot")
        imgui.SameLine(ctx)

        # Connection status dot
        # The color is set by the caller via set_status, but we expose a
        # property for the connected state separately
        status_color = COLOR_STATUS_OK if getattr(self, "connected", False) else COLOR_STATUS_ERR
        imgui.TextColored(ctx, status_color, "  " + ("connected" if getattr(self, "connected", False) else "disconnected"))

        imgui.SameLine(ctx)
        # Push to right side
        avail_w, _ = imgui.GetContentRegionAvail(ctx)
        imgui.SetCursorPosX(ctx, imgui.GetCursorPosX(ctx) + avail_w - 110)

        # Stereo toggle
        changed, self.stereo_enabled = imgui.Checkbox(ctx, "Stereo", self.stereo_enabled)

    def _draw_chat_history(self, ctx) -> None:
        """Scrollable chat history panel."""
        # Reserve space: leave room for status bar + input area below
        _, avail_h = imgui.GetContentRegionAvail(ctx)
        chat_h = avail_h - 54  # 28px status + 26px input area approx

        imgui.BeginChild(ctx, "chat_history", 0, chat_h, imgui.ChildFlags_None())

        for msg in self.messages:
            self._draw_message(ctx, msg)

        # Auto-scroll to bottom when new content arrives
        if self._scroll_to_bottom:
            imgui.SetScrollHereY(ctx, 1.0)
            self._scroll_to_bottom = False

        imgui.EndChild(ctx)

    def _draw_message(self, ctx, msg: ChatMessage) -> None:
        """Draw a single chat message bubble."""
        if msg.role == "user":
            imgui.TextColored(ctx, COLOR_USER_MSG, "You")
            imgui.SameLine(ctx)
            imgui.TextWrapped(ctx, msg.content)

        elif msg.role == "assistant":
            imgui.TextColored(ctx, COLOR_AI_MSG, "ReaBot")
            imgui.SameLine(ctx)
            content = msg.content + (" ..." if msg.streaming else "")
            imgui.TextWrapped(ctx, content)

        elif msg.role == "system":
            imgui.TextColored(ctx, COLOR_WARNING, msg.content)

        imgui.Spacing(ctx)

    def _draw_status_bar(self, ctx) -> None:
        """One-line status row."""
        if self.status == "Ready":
            color = COLOR_STATUS_OK
        elif any(kw in self.status for kw in ("Analyzing", "Rendering", "Waiting")):
            color = COLOR_STATUS_BUSY
        else:
            color = COLOR_STATUS_ERR

        imgui.TextColored(ctx, color, self.status)

    def _draw_input_area(self, ctx) -> None:
        """Text input + Analyze button + Chat button."""
        avail_w, _ = imgui.GetContentRegionAvail(ctx)
        input_w = avail_w - 180  # reserve space for two buttons

        imgui.SetNextItemWidth(ctx, input_w)
        # InputText returns (changed, new_value)
        enter_pressed = False
        changed, self.input_buf = imgui.InputText(
            ctx, "##input", self.input_buf,
            imgui.InputTextFlags_EnterReturnsTrue()
        )
        if changed:
            enter_pressed = True

        imgui.SameLine(ctx)

        # Analyze button — render + DSP + LLM
        if imgui.Button(ctx, "Analyze", 80, 0):
            self._trigger_analyze()

        imgui.SameLine(ctx)

        # Chat button — no audio, just follow-up text
        if imgui.Button(ctx, "Chat", 80, 0) or enter_pressed:
            self._trigger_chat()

    def _trigger_analyze(self) -> None:
        prompt = self.input_buf.strip()
        if not prompt:
            self.add_system_message("Enter a question before clicking Analyze.")
            return
        if self.on_analyze:
            self.on_analyze(prompt, self.stereo_enabled)
            self.add_user_message(prompt)
            self.input_buf = ""
            self.set_status("Rendering...")

    def _trigger_chat(self) -> None:
        prompt = self.input_buf.strip()
        if not prompt:
            return
        if self.on_chat:
            self.on_chat(prompt)
            self.add_user_message(prompt)
            self.input_buf = ""
            self.set_status("Waiting for response...")

    def set_connected(self, connected: bool) -> None:
        self.connected = connected
