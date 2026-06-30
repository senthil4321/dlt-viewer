from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class VersionResponse(BaseModel):
    service: str
    version: str


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["heartbeat", "message", "connection_state", "stats", "error"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str
    seq: int = Field(ge=0)
    payload: dict[str, Any]


class SessionCreateRequest(BaseModel):
    transport: Literal["tcp", "udp"]
    host: str
    port: int = Field(gt=0, le=65535)
    ecu_id: str = Field(min_length=1, max_length=64)
    multicast_group: str | None = None
    interface_ip: str | None = None


class SessionCreateResponse(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))


class SessionInfo(BaseModel):
    session_id: str
    transport: Literal["tcp", "udp"]
    host: str
    port: int
    ecu_id: str
    multicast_group: str | None = None
    interface_ip: str | None = None
    state: Literal["created", "connecting", "connected", "disconnected", "error"] = "created"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionActionResponse(BaseModel):
    session_id: str
    state: Literal["connecting", "connected", "disconnected"]
    message: str


# ---------------------------------------------------------------------------
# Ingestion event payload models
# ---------------------------------------------------------------------------

class DltMessagePayload(BaseModel):
    """Payload for a ``message`` WebSocket event."""

    ecu_id:        str
    apid:          str
    ctid:          str
    msg_type:      str
    log_level:     str
    verbose:       bool
    mcnt:          int
    timestamp_sec: float
    payload_text:  str
    decode_error:  str | None = None


class StatsPayload(BaseModel):
    """Payload for a ``stats`` WebSocket event (broadcast every 5 s)."""

    messages_received: int
    bytes_received:    int
    decode_errors:     int


class ErrorPayload(BaseModel):
    """Payload for an ``error`` WebSocket event."""

    code:    str
    detail:  str
