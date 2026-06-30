"""Integration tests for the session REST API.

Uses Starlette's synchronous TestClient so no async event-loop fixtures
are needed.  The ingestion_manager is patched to a no-op to avoid
real network connections during CI.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _patch_ingestion():
    """Replace ingestion_manager.start/stop with no-ops for all tests."""
    with (
        patch("app.main.ingestion_manager.start", new_callable=AsyncMock) as mock_start,
        patch("app.main.ingestion_manager.stop",  new_callable=AsyncMock) as mock_stop,
    ):
        yield mock_start, mock_stop


# ---------------------------------------------------------------------------
# /health and /version
# ---------------------------------------------------------------------------

class TestHealthVersion:
    def test_health(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "service" in body
        assert "version" in body

    def test_version(self, client: TestClient) -> None:
        r = client.get("/version")
        assert r.status_code == 200
        body = r.json()
        assert "service" in body
        assert "version" in body


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

SESSION_PAYLOAD = {
    "transport": "tcp",
    "host": "127.0.0.1",
    "port": 3490,
    "ecu_id": "ECU1",
}


class TestSessionCRUD:
    def test_create_session(self, client: TestClient) -> None:
        r = client.post("/sessions", json=SESSION_PAYLOAD)
        assert r.status_code == 200
        body = r.json()
        assert "session_id" in body
        assert body["state"] == "created"
        assert body["transport"] == "tcp"

    def test_list_sessions(self, client: TestClient) -> None:
        client.post("/sessions", json=SESSION_PAYLOAD)
        r = client.get("/sessions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    def test_get_session(self, client: TestClient) -> None:
        sid = client.post("/sessions", json=SESSION_PAYLOAD).json()["session_id"]
        r = client.get(f"/sessions/{sid}")
        assert r.status_code == 200
        assert r.json()["session_id"] == sid

    def test_get_session_not_found(self, client: TestClient) -> None:
        r = client.get("/sessions/nonexistent-id")
        assert r.status_code == 404

    def test_create_udp_session(self, client: TestClient) -> None:
        r = client.post(
            "/sessions",
            json={
                "transport": "udp",
                "host": "239.0.0.1",
                "port": 3490,
                "ecu_id": "ECU2",
                "multicast_group": "239.0.0.1",
            },
        )
        assert r.status_code == 200
        assert r.json()["transport"] == "udp"

    def test_invalid_port(self, client: TestClient) -> None:
        r = client.post(
            "/sessions",
            json={"transport": "tcp", "host": "127.0.0.1", "port": 0, "ecu_id": "X"},
        )
        assert r.status_code == 422  # pydantic validation error

    def test_missing_ecu_id(self, client: TestClient) -> None:
        r = client.post(
            "/sessions",
            json={"transport": "tcp", "host": "127.0.0.1", "port": 3490},
        )
        assert r.status_code == 422


class TestSessionConnectDisconnect:
    def test_connect_returns_connecting(
        self, client: TestClient, _patch_ingestion
    ) -> None:
        sid = client.post("/sessions", json=SESSION_PAYLOAD).json()["session_id"]
        r = client.post(f"/sessions/{sid}/connect")
        assert r.status_code == 200
        body = r.json()
        assert body["state"] == "connecting"
        assert body["session_id"] == sid

    def test_connect_calls_ingestion_start(
        self, client: TestClient, _patch_ingestion
    ) -> None:
        mock_start, _ = _patch_ingestion
        sid = client.post("/sessions", json=SESSION_PAYLOAD).json()["session_id"]
        client.post(f"/sessions/{sid}/connect")
        mock_start.assert_called_once()

    def test_disconnect_returns_disconnected(
        self, client: TestClient, _patch_ingestion
    ) -> None:
        sid = client.post("/sessions", json=SESSION_PAYLOAD).json()["session_id"]
        client.post(f"/sessions/{sid}/connect")
        r = client.post(f"/sessions/{sid}/disconnect")
        assert r.status_code == 200
        assert r.json()["state"] == "disconnected"

    def test_disconnect_calls_ingestion_stop(
        self, client: TestClient, _patch_ingestion
    ) -> None:
        mock_start, mock_stop = _patch_ingestion
        sid = client.post("/sessions", json=SESSION_PAYLOAD).json()["session_id"]
        client.post(f"/sessions/{sid}/connect")
        client.post(f"/sessions/{sid}/disconnect")
        mock_stop.assert_called_once_with(sid)

    def test_connect_not_found(self, client: TestClient) -> None:
        r = client.post("/sessions/nonexistent/connect")
        assert r.status_code == 404

    def test_disconnect_not_found(self, client: TestClient) -> None:
        r = client.post("/sessions/nonexistent/disconnect")
        assert r.status_code == 404
