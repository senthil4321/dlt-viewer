# dlt-viewer webbridge (MVP)

Lightweight Python service that exposes REST and WebSocket APIs for browser-based clients.

## Implemented in this checkpoint

- `GET /health`
- `GET /version`
- `WS /stream/{session_id}` with periodic heartbeat events

## Quick start

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8008 --reload
```

Open:

- http://127.0.0.1:8008/health
- http://127.0.0.1:8008/version

Use a WebSocket client on `ws://127.0.0.1:8008/stream/demo-session`.

## Next implementation slice

- Add REST session management endpoints (`POST /sessions`, connect/disconnect actions).
- Add TCP/UDP ingestion worker abstraction and per-ECU state model.
- Emit real stream events (`message`, `connection_state`, `stats`, `error`).
