"""
ReaBot LLM - Handler Factory

make_llm_handler() returns an async closure bound to the daemon config.
The returned handler is registered as server.llm_handler in __main__.py
and called for every analyze_track and chat request.

Return value: the handler returns the full response text (str) so the
server can store both turns in conversation_history for multi-turn memory.
"""

import logging
from typing import Callable

from .client  import stream_response
from .context import build_context

logger = logging.getLogger("reabot.llm")


def make_llm_handler(config):
    """
    Factory: returns the llm_handler coroutine bound to config.

    Usage in __main__.py:
        from .llm import make_llm_handler
        server.llm_handler = make_llm_handler(config)
    """

    async def llm_handler(
        request_id:           str,
        analysis:             dict,
        track_metadata:       dict,
        user_question:        str,
        conversation_history: list[dict],
        send_fn:              Callable,
        is_multi_track:       bool = False,
    ) -> str:
        """
        1. Build the full context (system + history + analysis block).
        2. Stream tokens from OpenRouter, forwarding each to the Lua client.
        3. Send response_done when the stream ends.
        4. Return the full response text for storage in conversation history.

        On error: sends an error message to the client and returns "".
        """
        from ..protocol import response_chunk, response_done, error_response

        messages = build_context(
            analysis=analysis,
            track_metadata=track_metadata,
            user_question=user_question,
            conversation_history=conversation_history,
            is_multi_track=is_multi_track,
        )

        full_text: list[str] = []

        async def on_chunk(delta: str) -> None:
            full_text.append(delta)
            await send_fn(response_chunk(request_id, delta))

        async def on_done(text: str) -> None:
            await send_fn(response_done(request_id, text))

        try:
            await stream_response(
                api_key=config.openrouter_api_key,
                model=config.model,
                messages=messages,
                on_chunk=on_chunk,
                on_done=on_done,
            )
        except RuntimeError as e:
            logger.error("LLM stream error for request %s: %s", request_id, e)
            await send_fn(error_response(request_id, str(e), "llm_error"))
            return ""

        return "".join(full_text)

    return llm_handler
