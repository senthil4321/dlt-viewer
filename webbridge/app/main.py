from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .config import get_settings
from .ingestion.ingestion_manager import ingestion_manager
from .ingestion.tcp_client import TcpIngestionClient
from .ingestion.control_messages import (
    build_set_log_level_request,
    build_get_log_info_request,
    build_set_verbose_mode_request,
)
from .models import (
    ControlOperationResponse,
    HealthResponse,
    SessionActionResponse,
    SessionCreateRequest,
    SessionInfo,
    SetLogLevelRequest,
    SetVerboseModeRequest,
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

# Serve static files (HTML UI)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="static")


# ---------------------------------------------------------------------------
# Root / UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=FileResponse)
async def root():
    """Serve the web UI."""
    return FileResponse(Path(__file__).parent.parent / "static" / "index.html", media_type="text/html")


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
# Control Operations
# ---------------------------------------------------------------------------

@app.post("/sessions/{session_id}/control/set-log-level", response_model=ControlOperationResponse)
async def set_log_level(session_id: str, request: SetLogLevelRequest) -> ControlOperationResponse:
    """Send a SET_LOG_LEVEL control message to the ECU.
    
    This allows changing the log level of a specific application context
    on the remote ECU without disconnecting.
    """
    session = session_registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != "connected":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot send control message: session is {session.state}, not connected"
        )
    
    # Build the control message
    control_msg = build_set_log_level_request(
        apid=request.apid,
        ctid=request.ctid,
        log_level=request.log_level,
    )
    
    # Get the TCP client for this session
    worker = ingestion_manager._workers.get(session_id)
    if not isinstance(worker, TcpIngestionClient):
        raise HTTPException(
            status_code=409,
            detail="Control operations only supported for TCP transport"
        )
    
    # Send the control message
    try:
        await worker._send_control_message(control_msg)
        return ControlOperationResponse(
            session_id=session_id,
            status="sent",
            message=f"SET_LOG_LEVEL sent to {request.apid}/{request.ctid} (level={request.log_level})",
            operation="set_log_level",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send control message: {e}"
        )


@app.post("/sessions/{session_id}/control/set-verbose-mode", response_model=ControlOperationResponse)
async def set_verbose_mode(session_id: str, request: SetVerboseModeRequest) -> ControlOperationResponse:
    """Send a SET_VERBOSE_MODE control message to the ECU."""
    session = session_registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.state != "connected":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot send control message: session is {session.state}, not connected"
        )
    
    control_msg = build_set_verbose_mode_request(verbose=request.verbose)
    
    worker = ingestion_manager._workers.get(session_id)
    if not isinstance(worker, TcpIngestionClient):
        raise HTTPException(
            status_code=409,
            detail="Control operations only supported for TCP transport"
        )
    
    try:
        await worker._send_control_message(control_msg)
        return ControlOperationResponse(
            session_id=session_id,
            status="sent",
            message=f"SET_VERBOSE_MODE sent to {request.apid}/{request.ctid} (verbose={request.verbose})",
            operation="set_verbose_mode",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send control message: {e}"
        )


@app.get("/sessions/{session_id}/control/supported-operations")
async def get_supported_operations(session_id: str):
    """Get list of control operations supported for this session."""
    session = session_registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    operations = {
        "tcp": [
            {
                "name": "set_log_level",
                "endpoint": f"/sessions/{session_id}/control/set-log-level",
                "description": "Set log level for application/context",
                "parameters": ["apid", "ctid", "log_level"]
            },
            {
                "name": "set_verbose_mode",
                "endpoint": f"/sessions/{session_id}/control/set-verbose-mode",
                "description": "Enable/disable verbose mode",
                "parameters": ["apid", "ctid", "verbose"]
            }
        ],
        "udp": []
    }
    
    return {
        "transport": session.transport,
        "operations": operations.get(session.transport, [])
    }


# ---------------------------------------------------------------------------
# WebSocket stream
# ---------------------------------------------------------------------------

@app.websocket("/stream/{session_id}")
async def stream(session_id: str, websocket: WebSocket) -> None:
    await session_manager.connect(session_id=session_id, websocket=websocket)
    await session_manager.run_session(session_id=session_id, websocket=websocket)
