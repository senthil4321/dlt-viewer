"""Orchestrates per-session ingestion workers (TCP / UDP).

Usage
-----
    await ingestion_manager.start(session_info, on_event_cb)
    # ... later ...
    await ingestion_manager.stop(session_id)

The *on_event_cb* receives ``(session_id, event_type, payload_dict)`` for
every ``message``, ``connection_state``, ``stats``, and ``error`` event
produced by the ingestion worker.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Union

from ..models import DltMessagePayload, SessionInfo, StatsPayload
from .dlt_parser import DltMessage
from .tcp_client import TcpIngestionClient
from .udp_listener import UdpIngestionListener

log = logging.getLogger(__name__)

OnEventCallback = Callable[[str, str, dict], Awaitable[None]]
_Worker = Union[TcpIngestionClient, UdpIngestionListener]

STATS_INTERVAL_SEC = 5.0


class _SessionStats:
    __slots__ = ("messages_received", "bytes_received", "decode_errors")

    def __init__(self) -> None:
        self.messages_received: int = 0
        self.bytes_received: int    = 0
        self.decode_errors: int     = 0


class IngestionManager:
    """Manages one ingestion worker per active session."""

    def __init__(self) -> None:
        self._workers:    dict[str, _Worker]          = {}
        self._stats:      dict[str, _SessionStats]    = {}
        self._callbacks:  dict[str, OnEventCallback]  = {}
        self._stat_tasks: dict[str, asyncio.Task]     = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def start(self, session: SessionInfo, on_event: OnEventCallback) -> None:
        """Start ingestion for *session*, replacing any existing worker."""
        sid = session.session_id

        # Tear down any running worker for this session first.
        if sid in self._workers:
            await self.stop(sid)

        self._callbacks[sid] = on_event
        self._stats[sid]     = _SessionStats()

        # Build per-session message + state callbacks.
        async def _on_message(session_id: str, msg: DltMessage) -> None:
            stats = self._stats.get(session_id)
            if stats is not None:
                stats.messages_received += 1
                stats.bytes_received    += msg.length
                if msg.decode_error:
                    stats.decode_errors += 1

            cb = self._callbacks.get(session_id)
            if cb is None:
                return

            payload = DltMessagePayload(
                ecu_id       = msg.ecu_id,
                apid         = msg.apid,
                ctid         = msg.ctid,
                msg_type     = msg.msg_type,
                log_level    = msg.log_level,
                verbose      = msg.verbose,
                mcnt         = msg.mcnt,
                timestamp_sec = msg.timestamp_sec,
                payload_text = msg.payload_text,
                decode_error = msg.decode_error,
            )
            await cb(session_id, "message", payload.model_dump())

        async def _on_state(session_id: str, state: str, error: str | None) -> None:
            cb = self._callbacks.get(session_id)
            if cb is None:
                return
            p: dict = {"state": state}
            if error:
                p["error"] = error
            await cb(session_id, "connection_state", p)

        if session.transport == "tcp":
            worker: _Worker = TcpIngestionClient(
                session_id = sid,
                host       = session.host,
                port       = session.port,
                on_message = _on_message,
                on_state   = _on_state,
            )
        else:
            worker = UdpIngestionListener(
                session_id     = sid,
                host           = session.host,
                port           = session.port,
                on_message     = _on_message,
                on_state       = _on_state,
                multicast_group = session.multicast_group,
                interface_ip   = session.interface_ip,
            )

        self._workers[sid] = worker
        worker.start()

        self._stat_tasks[sid] = asyncio.create_task(
            self._stats_loop(sid), name=f"stats-{sid}"
        )
        log.info("Ingestion started for session %s (%s)", sid, session.transport)

    async def stop(self, session_id: str) -> None:
        """Stop ingestion for *session_id* and release all resources."""
        worker = self._workers.pop(session_id, None)
        if worker is not None:
            await worker.stop()

        task = self._stat_tasks.pop(session_id, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._stats.pop(session_id, None)
        self._callbacks.pop(session_id, None)
        log.info("Ingestion stopped for session %s", session_id)

    def is_active(self, session_id: str) -> bool:
        return session_id in self._workers

    # ------------------------------------------------------------------
    # Stats broadcast loop
    # ------------------------------------------------------------------

    async def _stats_loop(self, session_id: str) -> None:
        while True:
            await asyncio.sleep(STATS_INTERVAL_SEC)
            stats = self._stats.get(session_id)
            cb    = self._callbacks.get(session_id)
            if stats is None or cb is None:
                break
            payload = StatsPayload(
                messages_received = stats.messages_received,
                bytes_received    = stats.bytes_received,
                decode_errors     = stats.decode_errors,
            )
            await cb(session_id, "stats", payload.model_dump())


ingestion_manager = IngestionManager()
