from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import ORJSONResponse

from .config import get_settings
from .models import (
    HealthResponse,
    SessionActionResponse,
    SessionCreateRequest,
    SessionInfo,
    VersionResponse,
)
from .services.session_manager import session_manager
from .services.session_registry import session_registry

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    default_response_class=ORJSONResponse,
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        service=settings.app_name,
        version=settings.app_version,
    )


@app.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    return VersionResponse(
        service=settings.app_name,
        version=settings.app_version,
    )


@app.post("/sessions", response_model=SessionInfo)
async def create_session(request: SessionCreateRequest) -> SessionInfo:
    return session_registry.create(request)


@app.get("/sessions", response_model=list[SessionInfo])
async def list_sessions() -> list[SessionInfo]:
    return session_registry.list()


@app.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str) -> SessionInfo:
    session = session_registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.post("/sessions/{session_id}/connect", response_model=SessionActionResponse)
async def connect_session(session_id: str) -> SessionActionResponse:
    session = session_registry.set_state(session_id, "connecting")
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_registry.set_state(session_id, "connected")
    await session_manager.broadcast_event(
        session_id=session_id,
        event_type="connection_state",
        payload={
            "state": "connected",
            "transport": session.transport,
            "host": session.host,
            "port": session.port,
            "ecu_id": session.ecu_id,
        },
    )

    return SessionActionResponse(
        session_id=session_id,
        state="connected",
        message="Session marked connected (socket ingestion pending implementation)",
    )


@app.post("/sessions/{session_id}/disconnect", response_model=SessionActionResponse)
async def disconnect_session(session_id: str) -> SessionActionResponse:
    session = session_registry.set_state(session_id, "disconnected")
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    await session_manager.broadcast_event(
        session_id=session_id,
        event_type="connection_state",
        payload={
            "state": "disconnected",
            "transport": session.transport,
            "host": session.host,
            "port": session.port,
            "ecu_id": session.ecu_id,
        },
    )

    return SessionActionResponse(
        session_id=session_id,
        state="disconnected",
        message="Session marked disconnected",
    )


@app.websocket("/stream/{session_id}")
async def stream(session_id: str, websocket: WebSocket) -> None:
    await session_manager.connect(session_id=session_id, websocket=websocket)
    await session_manager.run_session(session_id=session_id, websocket=websocket)
