from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from .config import get_settings
from .ingestion.ingestion_manager import ingestion_manager
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health / version
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

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
    """Start real socket ingestion for the session.

    The actual TCP/UDP connection is established asynchronously.  Watch
    the ``/stream/{session_id}`` WebSocket for ``connection_state`` events
    that reflect the live connection lifecycle (connecting → connected /
    error → reconnecting …).
    """
    session = session_registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Mark the session as connecting in the registry immediately.
    session_registry.set_state(session_id, "connecting")

    # Build the event callback that bridges ingestion events → WebSocket
    # broadcasts and keeps the registry state up to date.
    async def _on_event(sid: str, event_type: str, payload: dict) -> None:
        if event_type == "connection_state":
            state = payload.get("state", "")
            if state in ("connected", "error", "disconnected", "connecting"):
                session_registry.set_state(sid, state)
        await session_manager.broadcast_event(
            session_id=sid,
            event_type=event_type,
            payload=payload,
        )

    await ingestion_manager.start(session, _on_event)

    return SessionActionResponse(
        session_id=session_id,
        state="connecting",
        message=(
            f"Ingestion started for {session.transport.upper()} "
            f"{session.host}:{session.port}. "
            "Watch /stream/<session_id> for connection_state events."
        ),
    )


@app.post("/sessions/{session_id}/disconnect", response_model=SessionActionResponse)
async def disconnect_session(session_id: str) -> SessionActionResponse:
    """Stop socket ingestion and mark session disconnected."""
    session = session_registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    await ingestion_manager.stop(session_id)
    session_registry.set_state(session_id, "disconnected")

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
        message="Ingestion stopped and session marked disconnected.",
    )


# ---------------------------------------------------------------------------
# WebSocket stream
# ---------------------------------------------------------------------------

@app.websocket("/stream/{session_id}")
async def stream(session_id: str, websocket: WebSocket) -> None:
    await session_manager.connect(session_id=session_id, websocket=websocket)
    await session_manager.run_session(session_id=session_id, websocket=websocket)
