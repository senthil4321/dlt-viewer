"""Tests for control operations (Phase 6)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import SetLogLevelRequest, SetVerboseModeRequest
from app.ingestion.control_messages import (
    build_set_log_level_request,
    build_get_log_info_request,
    build_set_verbose_mode_request,
    CTRL_SET_LOG_LEVEL,
    LOG_LEVEL_DEBUG,
)


client = TestClient(app)


class TestControlMessageBuilding:
    """Test control message construction."""

    def test_build_set_log_level_request(self):
        """Test building a SET_LOG_LEVEL control message."""
        msg = build_set_log_level_request(
            apid="APP1",
            ctid="CTX1",
            log_level=LOG_LEVEL_DEBUG,
        )
        
        assert msg is not None
        assert len(msg) > 0
        # First byte should be htyp (STD | WEID | WSID | WTMS | UEH = 0x3D, no VERBOSE for control)
        assert msg[0] == 0x3D
        # Message should contain the log level in the request data
        assert LOG_LEVEL_DEBUG in msg

    def test_build_get_log_info_request(self):
        """Test building a GET_LOG_INFO control message."""
        msg = build_get_log_info_request(apid="APP1", ctid="CTX1")
        
        assert msg is not None
        assert len(msg) > 0
        assert msg[0] == 0x3D

    def test_build_set_verbose_mode_request(self):
        """Test building a SET_VERBOSE_MODE control message."""
        msg_enable = build_set_verbose_mode_request(
            apid="APP1",
            ctid="CTX1",
            verbose=True,
        )
        
        msg_disable = build_set_verbose_mode_request(
            apid="APP1",
            ctid="CTX1",
            verbose=False,
        )
        
        assert msg_enable is not None
        assert msg_disable is not None
        assert len(msg_enable) > 0
        assert len(msg_disable) > 0
        assert msg_enable[0] == 0x3D
        assert msg_disable[0] == 0x3D


class TestControlOperationEndpoints:
    """Test control operation REST endpoints."""

    def test_get_supported_operations_nonexistent_session(self):
        """Test getting supported operations for nonexistent session."""
        resp = client.get("/sessions/nonexistent/control/supported-operations")
        assert resp.status_code == 404

    def test_get_supported_operations_tcp(self):
        """Test getting supported operations for TCP session."""
        # Create a session
        session_resp = client.post(
            "/sessions",
            json={
                "transport": "tcp",
                "host": "127.0.0.1",
                "port": 3490,
                "ecu_id": "ECU1",
            },
        )
        session = session_resp.json()
        session_id = session["session_id"]
        
        # Get supported operations
        resp = client.get(f"/sessions/{session_id}/control/supported-operations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["transport"] == "tcp"
        assert len(data["operations"]) > 0
        
        # Check for expected operations
        op_names = [op["name"] for op in data["operations"]]
        assert "set_log_level" in op_names
        assert "set_verbose_mode" in op_names

    def test_set_log_level_not_connected(self):
        """Test SET_LOG_LEVEL on non-connected session."""
        # Create session
        session_resp = client.post(
            "/sessions",
            json={
                "transport": "tcp",
                "host": "127.0.0.1",
                "port": 3490,
                "ecu_id": "ECU1",
            },
        )
        session_id = session_resp.json()["session_id"]
        
        # Try to send control message without connecting
        resp = client.post(
            f"/sessions/{session_id}/control/set-log-level",
            json={
                "apid": "APP1",
                "ctid": "CTX1",
                "log_level": 4,
            },
        )
        assert resp.status_code == 409  # Conflict - not connected
        assert "not connected" in resp.json()["detail"]

    def test_set_log_level_invalid_log_level(self):
        """Test SET_LOG_LEVEL with invalid log level."""
        session_resp = client.post(
            "/sessions",
            json={
                "transport": "tcp",
                "host": "127.0.0.1",
                "port": 3490,
                "ecu_id": "ECU1",
            },
        )
        session_id = session_resp.json()["session_id"]
        
        # Try to send with invalid log level (should fail validation)
        resp = client.post(
            f"/sessions/{session_id}/control/set-log-level",
            json={
                "apid": "APP1",
                "ctid": "CTX1",
                "log_level": 7,  # Invalid: must be 1-6
            },
        )
        assert resp.status_code == 422  # Validation error

    def test_set_verbose_mode_not_connected(self):
        """Test SET_VERBOSE_MODE on non-connected session."""
        session_resp = client.post(
            "/sessions",
            json={
                "transport": "tcp",
                "host": "127.0.0.1",
                "port": 3490,
                "ecu_id": "ECU1",
            },
        )
        session_id = session_resp.json()["session_id"]
        
        resp = client.post(
            f"/sessions/{session_id}/control/set-verbose-mode",
            json={
                "apid": "APP1",
                "ctid": "CTX1",
                "verbose": True,
            },
        )
        assert resp.status_code == 409
        assert "not connected" in resp.json()["detail"]

    def test_set_log_level_udp_not_supported(self):
        """Test that control operations fail for UDP sessions."""
        # Create UDP session
        session_resp = client.post(
            "/sessions",
            json={
                "transport": "udp",
                "host": "127.0.0.1",
                "port": 3490,
                "ecu_id": "ECU1",
            },
        )
        session_id = session_resp.json()["session_id"]
        
        # Connect it (UDP connects immediately)
        client.post(f"/sessions/{session_id}/connect")
        
        # Try to send control message (should fail - UDP not supported)
        resp = client.post(
            f"/sessions/{session_id}/control/set-log-level",
            json={
                "apid": "APP1",
                "ctid": "CTX1",
                "log_level": 4,
            },
        )
        # Note: This might be 409 (conflict) or 501 (not implemented) depending on implementation
        assert resp.status_code in [409, 501]
