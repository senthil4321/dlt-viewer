from datetime import datetime, timezone

from ..models import SessionCreateRequest, SessionCreateResponse, SessionInfo


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionInfo] = {}

    def create(self, request: SessionCreateRequest) -> SessionInfo:
        session_id = SessionCreateResponse().session_id
        session = SessionInfo(
            session_id=session_id,
            transport=request.transport,
            host=request.host,
            port=request.port,
            ecu_id=request.ecu_id,
            multicast_group=request.multicast_group,
            interface_ip=request.interface_ip,
            state="created",
        )
        self._sessions[session_id] = session
        return session

    def list(self) -> list[SessionInfo]:
        return list(self._sessions.values())

    def get(self, session_id: str) -> SessionInfo | None:
        return self._sessions.get(session_id)

    def set_state(self, session_id: str, state: str) -> SessionInfo | None:
        session = self._sessions.get(session_id)
        if not session:
            return None

        session.state = state
        session.updated_at = datetime.now(timezone.utc)
        self._sessions[session_id] = session
        return session


session_registry = SessionRegistry()