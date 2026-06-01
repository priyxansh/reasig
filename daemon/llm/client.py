"""
ReaBot LLM - OpenRouter SSE Streaming Client

Streams responses from OpenRouter using Server-Sent Events (SSE).
Calls on_chunk() for each token delta as it arrives, and on_done()
with the complete assembled response when the stream finishes.

Error handling covers the most common OpenRouter failure modes and
produces user-readable error messages that are displayed in the REAPER chat.
"""

import asyncio
import json
import logging
from typing import Callable, Awaitable

import aiohttp

logger = logging.getLogger("reabot.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def stream_response(
    api_key: str,
    model: str,
    messages: list[dict],
    on_chunk: Callable[[str], Awaitable[None]],
    on_done:  Callable[[str], Awaitable[None]],
) -> None:
    """
    Stream a chat completion from OpenRouter.

    Args:
        api_key:  OpenRouter API key (from config.openrouter_api_key).
        model:    Model ID string, e.g. "deepseek/deepseek-chat-v3-0324:free".
        messages: Messages list built by context.build_context().
        on_chunk: Async callback invoked with each streaming token delta.
        on_done:  Async callback invoked with the full assembled response text.

    Raises:
        RuntimeError: On auth failures, rate limits, or network errors.
                      The caller (llm_handler in __init__.py) catches this
                      and sends a user-readable error message to the client.
    """
    headers = {
        "Authorization":  f"Bearer {api_key}",
        "Content-Type":   "application/json",
        "HTTP-Referer":   "https://github.com/priyxansh/reabot",
        "X-Title":        "ReaBot — REAPER AI Mix Assistant",
    }
    body = {
        "model":      model,
        "messages":   messages,
        "stream":     True,
        "max_tokens": 1024,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=120, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(OPENROUTER_URL, headers=headers, json=body) as resp:
                # Handle well-known error codes with readable messages
                if resp.status == 401:
                    raise RuntimeError(
                        "Invalid API key. Check OPENROUTER_API_KEY in your .env file."
                    )
                if resp.status == 402:
                    raise RuntimeError(
                        "OpenRouter account has insufficient credits. "
                        "Add credits at openrouter.ai or use a free model."
                    )
                if resp.status == 429:
                    raise RuntimeError(
                        "Rate limited by OpenRouter. Wait a moment and try again."
                    )
                if resp.status >= 500:
                    raise RuntimeError(
                        f"OpenRouter server error (HTTP {resp.status}). Try again shortly."
                    )
                resp.raise_for_status()

                full_response: list[str] = []

                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8").strip()

                    # SSE lines look like "data: {...}" or "data: [DONE]"
                    if not line.startswith("data: "):
                        continue

                    data_str = line[6:]

                    if data_str == "[DONE]":
                        break

                    try:
                        data  = json.loads(data_str)
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            full_response.append(delta)
                            await on_chunk(delta)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        # Malformed SSE frame — skip silently
                        continue

                await on_done("".join(full_response))

    except asyncio.CancelledError:
        # Expected when user clicks Clear or closes window
        logger.debug("LLM stream cancelled mid-flight")
        raise
    except aiohttp.ClientConnectorError:
        raise RuntimeError(
            "Cannot connect to OpenRouter. Check your internet connection."
        )
    except aiohttp.ServerTimeoutError:
        raise RuntimeError(
            "OpenRouter request timed out after 120 seconds."
        )
