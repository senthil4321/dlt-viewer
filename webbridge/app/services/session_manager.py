import asyncio
import contextlib
from collections import defaultdict

from fastapi import WebSocket

from ..config import get_settings
from ..models import EventEnvelope


class SessionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._seq: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[session_id].add(websocket)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].discard(websocket)
                if not self._connections[session_id]:
                    self._connections.pop(session_id, None)

    async def broadcast_heartbeat(self, session_id: str) -> None:
        settings = get_settings()
        while True:
            await asyncio.sleep(settings.heartbeat_interval_sec)
            seq = self._next_seq(session_id)
            event = EventEnvelope(
                type="heartbeat",
                session_id=session_id,
                seq=seq,
                payload={"message": "alive"},
            )
            await self._broadcast(session_id, event.model_dump(mode="json"))

    async def _broadcast(self, session_id: str, event: dict) -> None:
        dead: list[WebSocket] = []
        async with self._lock:
            targets = list(self._connections.get(session_id, set()))

        for ws in targets:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections[session_id].discard(ws)
                if not self._connections[session_id]:
                    self._connections.pop(session_id, None)

    async def run_session(self, session_id: str, websocket: WebSocket) -> None:
        heartbeat_task = asyncio.create_task(self.broadcast_heartbeat(session_id))
        try:
            while True:
                # Keep connection alive and reserve room for future client commands.
                await websocket.receive_text()
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
            await self.disconnect(session_id, websocket)

    def _next_seq(self, session_id: str) -> int:
        seq = self._seq[session_id]
        self._seq[session_id] += 1
        return seq


session_manager = SessionManager()
