"""Async TCP ingestion client for a DLT ECU stream.

Connection lifecycle:
  start()  → spawns a background task that calls _run_loop()
  stop()   → signals the task and waits for it to finish

_run_loop() implements an exponential-backoff reconnect loop:
  connect → read DLT frames → emit callbacks → on error: wait + retry

Callbacks:
  on_message(session_id, DltMessage)           — called for every parsed msg
  on_state(session_id, state, error_detail)    — state ∈ {connecting,connected,error}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from .dlt_parser import DltMessage, parse_messages

log = logging.getLogger(__name__)

READ_CHUNK            = 65536
RECONNECT_DELAY_INIT  = 2.0
RECONNECT_DELAY_MAX   = 60.0
RECONNECT_DELAY_MULT  = 2.0

OnMessageCallback = Callable[[str, DltMessage], Awaitable[None]]
OnStateCallback   = Callable[[str, str, "str | None"], Awaitable[None]]


class TcpIngestionClient:
    """Persistent async TCP connection to a DLT ECU with automatic reconnect."""

    def __init__(
        self,
        session_id: str,
        host: str,
        port: int,
        on_message: OnMessageCallback,
        on_state: OnStateCallback,
    ) -> None:
        self.session_id = session_id
        self.host       = host
        self.port       = port
        self._on_message = on_message
        self._on_state   = on_state
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._writer_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Spawn the background ingestion task."""
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run_loop(), name=f"tcp-ingest-{self.session_id}"
        )

    async def stop(self) -> None:
        """Signal the task to stop and await its completion."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _send_control_message(self, message: bytes) -> None:
        """Send a control message (e.g., SET_LOG_LEVEL) to the ECU."""
        async with self._writer_lock:
            if self._writer is None:
                raise RuntimeError("Not connected")
            self._writer.write(message)
            await self._writer.drain()
            log.info("TCP [%s] sent control message (%d bytes)", self.session_id, len(message))

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        delay = RECONNECT_DELAY_INIT
        while not self._stop_event.is_set():
            try:
                await self._connect_and_read()
                # Clean exit from read loop (stop requested).
                delay = RECONNECT_DELAY_INIT
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(
                    "TCP [%s] connection error: %s – reconnecting in %.1fs",
                    self.session_id,
                    exc,
                    delay,
                )
                await self._on_state(self.session_id, "error", str(exc))
                # Sleep for backoff duration, but wake early if stop is requested.
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                    return  # stop requested during backoff wait
                except asyncio.TimeoutError:
                    pass
                delay = min(delay * RECONNECT_DELAY_MULT, RECONNECT_DELAY_MAX)

    async def _connect_and_read(self) -> None:
        log.info("TCP [%s] connecting → %s:%d", self.session_id, self.host, self.port)
        await self._on_state(self.session_id, "connecting", None)

    async def _connect_and_read(self) -> None:
        log.info("TCP [%s] connecting → %s:%d", self.session_id, self.host, self.port)
        await self._on_state(self.session_id, "connecting", None)

        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            self._writer = writer  # Store for control message sending
            log.info("TCP [%s] connected", self.session_id)
            await self._on_state(self.session_id, "connected", None)

            buf: bytes = b""
            while not self._stop_event.is_set():
                chunk = await reader.read(READ_CHUNK)
                if not chunk:
                    raise ConnectionError("remote closed the connection")
                buf += chunk
                msgs, buf = parse_messages(buf)
                for msg in msgs:
                    await self._on_message(self.session_id, msg)
        finally:
            self._writer = None
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            log.info("TCP [%s] disconnected", self.session_id)
