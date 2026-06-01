"""
ReaBot Daemon - TCP Socket Server

Async TCP server that handles connections from REAPER ReaScript clients.
Uses asyncio for non-blocking I/O and concurrent client handling.
"""

import asyncio
import logging
from typing import Callable, Awaitable

from .protocol import (
    Message,
    MessageType,
    status_ok,
    error_response,
    response_chunk,
    response_done,
)
from .config import Config

logger = logging.getLogger("reabot.server")


class ClientConnection:
    """Represents a single connected ReaScript client."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        server: "ReaBotServer",
    ):
        self.reader = reader
        self.writer = writer
        self.server = server
        self.addr = writer.get_extra_info("peername")
        self.conversation_history: list[dict] = []
        self._closed = False
        # Cache last analysis so Chat follow-ups have the same DSP context
        self._last_analysis: dict = {}
        self._last_track_metadata: dict = {}
        self._current_task: asyncio.Task | None = None
        # Session persistence
        self._project_path: str = ""
        self._history_loaded: bool = False

    async def send(self, msg: Message) -> None:
        """Send a message to this client."""
        if self._closed:
            return
        try:
            self.writer.write(msg.to_bytes())
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            logger.warning("Connection lost to %s while sending", self.addr)
            self._closed = True

    async def handle(self) -> None:
        """Main loop: read messages from the client and dispatch them."""
        logger.info("Client connected: %s", self.addr)
        buffer = b""

        try:
            while True:
                data = await self.reader.read(65536)
                if not data:
                    break

                buffer += data

                # Process complete JSON-lines messages
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        msg = Message.from_bytes(line)
                        await self._dispatch(msg)
                    except Exception as e:
                        logger.error("Error processing message: %s", e)
                        err = error_response("unknown", str(e), "parse_error")
                        await self.send(err)

        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            logger.info("Client disconnected: %s", self.addr)
        finally:
            self._closed = True
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
            # Persist conversation history for next session
            if self.conversation_history and self._history_loaded:
                from .session import save_history
                await asyncio.to_thread(
                    save_history, self._project_path, self.conversation_history
                )
                logger.info(
                    "Session saved for '%s' (%d turns)",
                    self._project_path, len(self.conversation_history) // 2,
                )
            logger.info("Client connection closed: %s", self.addr)

    async def _dispatch(self, msg: Message) -> None:
        """Route a message to the appropriate handler."""
        msg_type = msg.type

        if msg_type == MessageType.STATUS:
            # Pull project_path from the STATUS payload so we can look up history
            # before the first analyze_track arrives (covers startup ping).
            project_path = msg.payload.get("project_path", "")
            if project_path and not self._project_path:
                self._project_path = project_path

            hist_turns = 0
            _has_history = False
            if not self._history_loaded and self._project_path:
                from .session import load_history, has_history as _check_history
                _has_history = await asyncio.to_thread(_check_history, self._project_path)
                if _has_history:
                    loaded = await asyncio.to_thread(load_history, self._project_path)
                    if loaded:
                        self.conversation_history = loaded
                        hist_turns = len(loaded) // 2
                        logger.info(
                            "Loaded %d history turns for '%s'",
                            hist_turns, self._project_path,
                        )
                self._history_loaded = True
            elif self._history_loaded:
                _has_history = len(self.conversation_history) > 0
                hist_turns = len(self.conversation_history) // 2

            await self.send(
                status_ok(
                    msg.id,
                    model=self.server.config.model,
                    has_history=_has_history,
                    history_turns=hist_turns,
                )
            )

        elif msg_type == MessageType.ANALYZE_TRACK:
            await self._handle_analyze_track(msg)

        elif msg_type == MessageType.ANALYZE_MULTI:
            await self._handle_analyze_multi(msg)

        elif msg_type == MessageType.CHAT:
            await self._handle_chat(msg)

        elif msg_type == MessageType.CANCEL:
            logger.info("Cancel request received for: %s", msg.payload.get("target_id"))
            if self._current_task and not self._current_task.done():
                self._current_task.cancel()

        else:
            await self.send(
                error_response(msg.id, f"Unknown message type: {msg_type}", "unknown_type")
            )

    async def _handle_analyze_track(self, msg: Message) -> None:
        """Handle a single-track analysis request."""
        try:
            wav_path = msg.payload.get("wav_path", "")
            track_metadata = msg.payload.get("track_metadata", {})
            user_question = msg.payload.get("user_question", "")
            stereo = bool(msg.payload.get("stereo", False))
            project_path = msg.payload.get("project_path", "")

            if not wav_path:
                await self.send(error_response(msg.id, "wav_path is required", "missing_field"))
                return

            # Capture project path and lazy-load history on the first real request
            if project_path and not self._project_path:
                self._project_path = project_path

            if not self._history_loaded:
                from .session import load_history
                loaded = await asyncio.to_thread(load_history, self._project_path)
                if loaded:
                    # Merge: prepend stored turns so they precede any already in memory.
                    # In practice this is only hit if STATUS didn't carry project_path.
                    existing_set = {(h["role"], h["content"]) for h in self.conversation_history}
                    merged = loaded + [
                        h for h in self.conversation_history
                        if (h["role"], h["content"]) not in existing_set
                    ]
                    self.conversation_history = merged
                    logger.info(
                        "Lazy-loaded %d history turns for '%s'",
                        len(loaded) // 2, self._project_path,
                    )
                self._history_loaded = True

            # Run DSP analysis in a thread pool to keep the event loop responsive
            if self.server.analyze_handler:
                analysis = await asyncio.to_thread(
                    self.server.analyze_handler,
                    wav_path,
                    user_question=user_question,
                    stereo=stereo,
                )
            else:
                analysis = {}
                logger.warning("No analyze handler registered, skipping DSP analysis")

            # Cache analysis and metadata for subsequent Chat follow-ups
            self._last_analysis = analysis
            self._last_track_metadata = track_metadata

            # Send to LLM if handler is registered
            if self.server.llm_handler:
                self._current_task = asyncio.create_task(
                    self.server.llm_handler(
                        request_id=msg.id,
                        analysis=analysis,
                        track_metadata=track_metadata,
                        user_question=user_question,
                        conversation_history=self.conversation_history,
                        send_fn=self.send,
                    )
                )
                try:
                    full_response = await self._current_task
                    # Store BOTH turns so next request has full multi-turn context
                    if full_response:
                        self.conversation_history.append({"role": "user",      "content": user_question})
                        self.conversation_history.append({"role": "assistant", "content": full_response})
                except asyncio.CancelledError:
                    logger.info("Cancelled in-flight task for %s", msg.id)
                finally:
                    self._current_task = None
            else:
                # No LLM handler — just return the raw analysis
                from .protocol import analysis_result
                await self.send(analysis_result(msg.id, analysis))

        except Exception as e:
            logger.exception("Error in analyze_track handler")
            await self.send(error_response(msg.id, str(e), "analysis_error"))

    async def _handle_analyze_multi(self, msg: Message) -> None:
        """Handle a multi-track analysis request."""
        try:
            tracks = msg.payload.get("tracks", [])
            user_question = msg.payload.get("user_question", "")
            stereo = bool(msg.payload.get("stereo", False))

            if not tracks:
                await self.send(error_response(msg.id, "tracks list is required", "missing_field"))
                return

            # Run DSP analysis on each track in a thread pool
            analyses = []
            if self.server.analyze_handler:
                for track in tracks:
                    wav_path = track.get("wav_path", "")
                    if wav_path:
                        analysis = await asyncio.to_thread(
                            self.server.analyze_handler,
                            wav_path,
                            user_question=user_question,
                            stereo=stereo,
                        )
                        analyses.append({
                            "track_metadata": track.get("track_metadata", {}),
                            "analysis": analysis,
                        })
            else:
                logger.warning("No analyze handler registered")

            # Run masking analysis if available
            # Note: masking_handler expects pre-built analysis dicts, not wav paths.
            masking = None
            if self.server.masking_handler and len(analyses) >= 2:
                masking = self.server.masking_handler(analyses)

            # Send to LLM
            if self.server.llm_handler:
                combined_context = {
                    "tracks": analyses,
                    "masking_analysis": masking,
                }
                await self.server.llm_handler(
                    request_id=msg.id,
                    analysis=combined_context,
                    track_metadata={},
                    user_question=user_question,
                    conversation_history=self.conversation_history,
                    send_fn=self.send,
                )
            else:
                from .protocol import analysis_result
                await self.send(analysis_result(msg.id, {"tracks": analyses, "masking": masking}))

        except Exception as e:
            logger.exception("Error in analyze_multi handler")
            await self.send(error_response(msg.id, str(e), "analysis_error"))

    async def _handle_chat(self, msg: Message) -> None:
        """Handle a free-form chat request."""
        try:
            user_message = msg.payload.get("user_message", "")

            if not user_message:
                await self.send(error_response(msg.id, "user_message is required", "missing_field"))
                return

            # Guard: require at least one prior analysis OR restored history.
            # When history is loaded from the DB the user has already analysed
            # this project in a previous session — Chat is still meaningful
            # because the LLM has the full conversation context.
            if not self._last_analysis and not self._history_loaded:
                await self.send(error_response(
                    msg.id,
                    "No track analysis available yet. Click Analyze first to give me data to work with.",
                    "no_analysis_context",
                ))
                return

            if not self._last_analysis and self._history_loaded:
                # Chat without fresh DSP data — LLM works from conversation history only
                logger.info("Chat with history-only context (no fresh analysis) for %s", self.addr)

            # Re-use the last DSP analysis + metadata so the LLM still has all the numbers
            effective_history = self.conversation_history

            if self.server.llm_handler:
                self._current_task = asyncio.create_task(
                    self.server.llm_handler(
                        request_id=msg.id,
                        analysis=self._last_analysis,
                        track_metadata=self._last_track_metadata,
                        user_question=user_message,
                        conversation_history=effective_history,
                        send_fn=self.send,
                    )
                )
                try:
                    full_response = await self._current_task
                    # Store BOTH turns so the next request has full multi-turn context
                    if full_response:
                        self.conversation_history.append({"role": "user",      "content": user_message})
                        self.conversation_history.append({"role": "assistant", "content": full_response})
                except asyncio.CancelledError:
                    logger.info("Cancelled in-flight task for %s", msg.id)
                finally:
                    self._current_task = None
            else:
                await self.send(
                    error_response(msg.id, "LLM handler not available", "no_llm_handler")
                )

        except Exception as e:
            logger.exception("Error in chat handler")
            await self.send(error_response(msg.id, str(e), "chat_error"))


class ReaBotServer:
    """Async TCP server for the ReaBot daemon."""

    def __init__(self, config: Config):
        self.config = config
        self.server: asyncio.Server | None = None
        self.clients: list[ClientConnection] = []

        # Handler hooks (set by __main__.py after initializing DSP/LLM modules)
        self.analyze_handler: Callable | None = None
        self.masking_handler: Callable | None = None
        self.llm_handler: Callable | None = None

    async def start(self) -> None:
        """Start the TCP server."""
        self.server = await asyncio.start_server(
            self._on_connect,
            self.config.host,
            self.config.port,
        )
        addrs = ", ".join(str(s.getsockname()) for s in self.server.sockets)
        logger.info("ReaBot daemon listening on %s", addrs)

    async def _on_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a new client connection."""
        client = ClientConnection(reader, writer, self)
        self.clients.append(client)
        try:
            await client.handle()
        finally:
            self.clients.remove(client)

    async def serve_forever(self) -> None:
        """Run the server until cancelled."""
        if self.server is None:
            await self.start()
        if self.server is None:
            # start() failed to bind — should not happen in practice since
            # asyncio.start_server raises on failure, but this guard satisfies
            # the type checker and documents the invariant explicitly.
            raise RuntimeError("Failed to start server: asyncio.start_server returned None")
        async with self.server:
            await self.server.serve_forever()

    async def shutdown(self) -> None:
        """Gracefully shut down the server."""
        logger.info("Shutting down ReaBot daemon...")
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        # Close all client connections
        for client in self.clients:
            client._closed = True
            client.writer.close()
        logger.info("ReaBot daemon stopped.")
