"""
ReaBot - Non-blocking TCP Daemon Client

Runs inside REAPER's main thread (defer loop). All socket I/O is non-blocking
so it never stalls the UI.

Design:
- connect() creates a non-blocking socket and attempts connection.
- tick() is called every defer frame. It flushes queued outgoing messages
  and tries to receive incoming data.
- BlockingIOError (EAGAIN/EWOULDBLOCK) is silently ignored on both send and recv.
- Complete JSON-line messages (terminated by newline) are parsed and dispatched
  to registered callbacks.
"""

import socket
import json
import time
import logging

logger = logging.getLogger("reabot.client")

# How long to wait before retrying a failed connection
_RECONNECT_INTERVAL_SEC = 3.0


class DaemonClient:
    """Non-blocking TCP client for communicating with the ReaBot daemon."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9876):
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None
        self._connected = False
        self._send_queue: list[bytes] = []
        self._recv_buffer = b""
        self._last_connect_attempt = 0.0

        # Registered message callbacks: type -> list[callable]
        self._callbacks: dict[str, list] = {}

        # Single catch-all callback for unrecognised types
        self._default_callback = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        Attempt to open a non-blocking connection to the daemon.
        Safe to call repeatedly — silently ignores if already connected.
        """
        if self._connected:
            return

        now = time.time()
        if now - self._last_connect_attempt < _RECONNECT_INTERVAL_SEC:
            return
        self._last_connect_attempt = now

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setblocking(False)
            # connect_ex returns errno instead of raising
            err = sock.connect_ex((self._host, self._port))
            # EINPROGRESS (115) is expected on non-blocking connect
            if err not in (0, 115):
                sock.close()
                return
            self._sock = sock
            self._connected = True
            self._recv_buffer = b""
            logger.info("Connected to daemon at %s:%s", self._host, self._port)
        except OSError:
            self._connected = False
            self._sock = None

    def disconnect(self) -> None:
        """Close the connection cleanly."""
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._recv_buffer = b""

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Defer-loop tick
    # ------------------------------------------------------------------

    def tick(self) -> None:
        """
        Called every defer frame. Handles all socket I/O non-blockingly.
        Attempt reconnect if disconnected.
        """
        if not self._connected:
            self.connect()
            return

        self._flush_send_queue()
        self._try_recv()

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send_message(self, msg: dict) -> None:
        """
        Queue a message dict for sending. The dict must match the daemon protocol.
        Messages are sent as JSON-lines (UTF-8, newline terminated).
        """
        line = json.dumps(msg, separators=(",", ":")) + "\n"
        self._send_queue.append(line.encode("utf-8"))

    def _flush_send_queue(self) -> None:
        """Try to send all queued messages. Stop on error or would-block."""
        if not self._sock or not self._send_queue:
            return

        while self._send_queue:
            data = self._send_queue[0]
            try:
                sent = self._sock.send(data)
                if sent == len(data):
                    self._send_queue.pop(0)
                else:
                    # Partial send — keep remainder at front
                    self._send_queue[0] = data[sent:]
                    break
            except BlockingIOError:
                break  # Socket buffer full — try again next frame
            except OSError:
                self._handle_disconnect()
                break

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    def _try_recv(self) -> None:
        """Try to read available data from socket. Parse complete JSON-lines."""
        if not self._sock:
            return

        try:
            chunk = self._sock.recv(65536)
            if not chunk:
                # Empty recv = connection closed by remote end
                self._handle_disconnect()
                return
            self._recv_buffer += chunk
        except BlockingIOError:
            return  # No data available this frame — normal
        except OSError:
            self._handle_disconnect()
            return

        # Parse all complete JSON-lines from the buffer
        while b"\n" in self._recv_buffer:
            line, self._recv_buffer = self._recv_buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
                self._dispatch(msg)
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("Received malformed message from daemon")

    def _dispatch(self, msg: dict) -> None:
        """Route a received message to the appropriate registered callback."""
        msg_type = msg.get("type", "")
        callbacks = self._callbacks.get(msg_type, [])
        for cb in callbacks:
            try:
                cb(msg)
            except Exception as e:
                logger.error("Error in callback for %s: %s", msg_type, e)

        if not callbacks and self._default_callback:
            try:
                self._default_callback(msg)
            except Exception as e:
                logger.error("Error in default callback: %s", e)

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on(self, msg_type: str, callback) -> None:
        """Register a callback for a specific message type."""
        if msg_type not in self._callbacks:
            self._callbacks[msg_type] = []
        self._callbacks[msg_type].append(callback)

    def on_any(self, callback) -> None:
        """Register a catch-all callback for any unhandled message type."""
        self._default_callback = callback

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_disconnect(self) -> None:
        """Handle an unexpected connection drop."""
        logger.warning("Lost connection to daemon. Will retry in %ss.", _RECONNECT_INTERVAL_SEC)
        self.disconnect()
