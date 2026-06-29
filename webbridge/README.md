# dlt-viewer webbridge (MVP)

Lightweight Python service that exposes REST and WebSocket APIs for browser-based clients.

## Implemented in this checkpoint

- `GET /health`
- `GET /version`
- `POST /sessions`
- `GET /sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/connect`
- `POST /sessions/{session_id}/disconnect`
- `WS /stream/{session_id}` with periodic heartbeat events
- WebSocket `connection_state` event broadcast on connect/disconnect API calls

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

Example session flow:

```bash
curl -X POST http://127.0.0.1:8008/sessions -H "content-type: application/json" -d "{\"transport\":\"tcp\",\"host\":\"127.0.0.1\",\"port\":3490,\"ecu_id\":\"ECU1\"}"
curl http://127.0.0.1:8008/sessions
curl -X POST http://127.0.0.1:8008/sessions/<SESSION_ID>/connect
curl -X POST http://127.0.0.1:8008/sessions/<SESSION_ID>/disconnect
```

## Next implementation slice

- Add TCP/UDP ingestion worker abstraction and per-ECU state model.
- Replace simulated connect/disconnect with real socket lifecycle state transitions.
- Emit real stream events (`message`, `stats`, `error`) from ingestion paths.
