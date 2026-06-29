from datetime import datetime, timezone
from typing import Any, Literal

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
