from fastapi import FastAPI, WebSocket
from fastapi.responses import ORJSONResponse

from .config import get_settings
from .models import HealthResponse, VersionResponse
from .services.session_manager import session_manager

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


@app.websocket("/stream/{session_id}")
async def stream(session_id: str, websocket: WebSocket) -> None:
    await session_manager.connect(session_id=session_id, websocket=websocket)
    await session_manager.run_session(session_id=session_id, websocket=websocket)
