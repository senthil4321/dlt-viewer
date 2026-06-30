"""WebSocket stream tests.

Uses Starlette's TestClient WebSocket context manager for synchronous
in-process WebSocket testing without starting a real server.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app
from app.config import get_settings


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _patch_ingestion():
    with (
        patch("app.main.ingestion_manager.start", new_callable=AsyncMock),
        patch("app.main.ingestion_manager.stop",  new_callable=AsyncMock),
    ):
        yield


SESSION_PAYLOAD = {
    "transport": "tcp",
    "host": "127.0.0.1",
    "port": 3490,
    "ecu_id": "ECU1",
}


class TestWebSocketStream:
    def _create_session(self, client: TestClient) -> str:
        return client.post("/sessions", json=SESSION_PAYLOAD).json()["session_id"]

    def test_websocket_accepts_connection(self, client: TestClient) -> None:
        """WebSocket connection is accepted and closes cleanly."""
        sid = self._create_session(client)
        with client.websocket_connect(f"/stream/{sid}") as ws:
            assert ws is not None
        # No exception means clean accept + disconnect handling.

    def test_heartbeat_event_received(self, client: TestClient) -> None:
        """First event from the stream is a heartbeat."""
        sid = self._create_session(client)
        # Patch the cached settings singleton so the heartbeat fires quickly.
        cfg = get_settings()
        original = cfg.heartbeat_interval_sec
        cfg.heartbeat_interval_sec = 0.01
        try:
            with client.websocket_connect(f"/stream/{sid}") as ws:
                raw   = ws.receive_text()
                event = json.loads(raw)
                assert event["type"] == "heartbeat"
                assert event["session_id"] == sid
                assert "seq" in event
                assert event["seq"] >= 0
        finally:
            cfg.heartbeat_interval_sec = original

    def test_event_envelope_schema(self, client: TestClient) -> None:
        """Every event has the mandatory envelope fields."""
        sid = self._create_session(client)
        cfg = get_settings()
        original = cfg.heartbeat_interval_sec
        cfg.heartbeat_interval_sec = 0.01
        try:
            with client.websocket_connect(f"/stream/{sid}") as ws:
                event = json.loads(ws.receive_text())
                assert {"type", "timestamp", "session_id", "seq", "payload"}.issubset(event)
        finally:
            cfg.heartbeat_interval_sec = original

    def test_seq_increments(self, client: TestClient) -> None:
        """Sequence numbers increase monotonically per session."""
        sid = self._create_session(client)
        cfg = get_settings()
        original = cfg.heartbeat_interval_sec
        cfg.heartbeat_interval_sec = 0.01
        try:
            with client.websocket_connect(f"/stream/{sid}") as ws:
                e1 = json.loads(ws.receive_text())
                e2 = json.loads(ws.receive_text())
                assert e2["seq"] == e1["seq"] + 1
        finally:
            cfg.heartbeat_interval_sec = original

    def test_unknown_session_still_connects(self, client: TestClient) -> None:
        """WebSocket accepts any session_id; events are scoped by that ID."""
        with client.websocket_connect("/stream/unknown-session") as ws:
            assert ws is not None

