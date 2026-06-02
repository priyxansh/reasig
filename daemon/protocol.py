"""
ReaSig Daemon - IPC Protocol

JSON-lines protocol over TCP for communication between REAPER ReaScript and the daemon.
Each message is a single JSON object terminated by a newline character.

Message format:
    {"type": "<message_type>", "id": "<uuid>", "payload": {...}}

Response format:
    {"type": "<response_type>", "id": "<original_request_id>", "payload": {...}}
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any
from enum import Enum


class MessageType(str, Enum):
    """Types of messages that can be sent between ReaScript and the daemon."""

    # Requests (ReaScript → Daemon)
    STATUS = "status"
    ANALYZE_TRACK = "analyze_track"
    ANALYZE_MULTI = "analyze_multi"
    CHAT = "chat"
    CANCEL = "cancel"
    CLEAR_HISTORY = "clear_history"

    # Responses (Daemon → ReaScript)
    STATUS_OK = "status_ok"
    RESPONSE_CHUNK = "response_chunk"
    RESPONSE_DONE = "response_done"
    ANALYSIS_RESULT = "analysis_result"
    ERROR = "error"


@dataclass
class Message:
    """A protocol message exchanged between ReaScript and the daemon."""

    type: str
    payload: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_json(self) -> str:
        """Serialize to a JSON-lines string (with trailing newline)."""
        return json.dumps(asdict(self), separators=(",", ":")) + "\n"

    def to_bytes(self) -> bytes:
        """Serialize to bytes for TCP transmission."""
        return self.to_json().encode("utf-8")

    @classmethod
    def from_json(cls, data: str) -> "Message":
        """Deserialize from a JSON string."""
        obj = json.loads(data.strip())
        return cls(
            type=obj["type"],
            payload=obj.get("payload", {}),
            id=obj.get("id", str(uuid.uuid4())),
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "Message":
        """Deserialize from bytes."""
        return cls.from_json(data.decode("utf-8"))


# --- Factory functions for common messages ---


def status_request() -> Message:
    """Create a status check request."""
    return Message(type=MessageType.STATUS)


def status_ok(
    request_id: str,
    model: str = "",
    has_history: bool = False,
    history_turns: int = 0,
) -> Message:
    """Create a status OK response.

    Args:
        request_id:    The id of the STATUS request being acknowledged.
        model:         Model identifier string (shown in UI title bar).
        has_history:   True if there are stored conversation turns for this project.
        history_turns: Number of stored turn pairs (user+assistant) for this project.
    """
    return Message(
        type=MessageType.STATUS_OK,
        id=request_id,
        payload={
            "status":        "ok",
            "version":       "0.1.0",
            "model":         model,
            "has_history":   has_history,
            "history_turns": history_turns,
        },
    )


def analyze_track_request(
    wav_path: str,
    track_metadata: dict,
    user_question: str = "",
    stereo: bool = False,
) -> Message:
    """Create a single-track analysis request."""
    return Message(
        type=MessageType.ANALYZE_TRACK,
        payload={
            "wav_path": wav_path,
            "track_metadata": track_metadata,
            "user_question": user_question,
            "stereo": stereo,
        },
    )


def analyze_multi_request(
    tracks: list[dict],
    user_question: str = "",
    stereo: bool = False,
) -> Message:
    """Create a multi-track analysis request.

    Each track dict should have: wav_path, track_metadata
    """
    return Message(
        type=MessageType.ANALYZE_MULTI,
        payload={
            "tracks": tracks,
            "user_question": user_question,
            "stereo": stereo,
        },
    )


def chat_request(
    user_message: str,
    conversation_history: list[dict] | None = None,
    track_context: dict | None = None,
) -> Message:
    """Create a free-form chat request."""
    return Message(
        type=MessageType.CHAT,
        payload={
            "user_message": user_message,
            "conversation_history": conversation_history or [],
            "track_context": track_context,
        },
    )


def response_chunk(request_id: str, content: str) -> Message:
    """Create a streaming response chunk (single LLM token or group of tokens)."""
    return Message(
        type=MessageType.RESPONSE_CHUNK,
        id=request_id,
        payload={"content": content},
    )


def response_done(request_id: str, full_response: str, usage: dict | None = None) -> Message:
    """Create a response completion message."""
    return Message(
        type=MessageType.RESPONSE_DONE,
        id=request_id,
        payload={
            "full_response": full_response,
            "usage": usage,
        },
    )


def analysis_result(request_id: str, analysis: dict) -> Message:
    """Create an analysis result message (DSP metrics without LLM interpretation)."""
    return Message(
        type=MessageType.ANALYSIS_RESULT,
        id=request_id,
        payload={"analysis": analysis},
    )


def error_response(request_id: str, error_message: str, error_code: str = "unknown") -> Message:
    """Create an error response."""
    return Message(
        type=MessageType.ERROR,
        id=request_id,
        payload={
            "error": error_message,
            "code": error_code,
        },
    )
