# Web UI + Python Bridge Progress Log

Date: 2026-06-30
Branch: feature/web-ui-python-bridge-mvp

## Status

**Phase 3 (Socket Ingestion Engine) and Phase 4 (DLT Parsing) complete.**
All 41 tests pass. Connect/disconnect endpoints now drive real TCP/UDP ingestion.

## Completed

1. Created feature branch for isolated implementation.
2. Added project plan document for migration and phased delivery.
3. Added `webbridge/` MVP service scaffold.
4. Implemented REST + WebSocket endpoints:
   - `GET /health`, `GET /version`
   - `POST /sessions`, `GET /sessions`, `GET /sessions/{id}`
   - `POST /sessions/{id}/connect` — starts real TCP/UDP ingestion worker
   - `POST /sessions/{id}/disconnect` — stops ingestion worker
   - `WS /stream/{id}` — live event stream with heartbeat
5. Added environment-driven settings and typed response/event models.
6. Added in-memory session registry service.
7. Added WebSocket `connection_state` broadcast on connect/disconnect.
8. **[NEW] Implemented DLT binary parser** (`app/ingestion/dlt_parser.py`):
   - Standard header (htyp, mcnt, len, optional ECU-ID/session-ID/timestamp)
   - Extended header (msin, noar, apid, ctid)
   - Verbose payload argument decoding: bool, sint, uint, float, string, raw
   - Big/little endian payload support (HTYP_MSBF flag)
   - Streaming framing with split-frame reassembly and byte-level resync
9. **[NEW] Implemented TCP ingestion client** (`app/ingestion/tcp_client.py`):
   - Async TCP connection with exponential-backoff reconnect (2 s → 60 s)
   - Reconnects automatically on remote close or network error
   - Emits `connection_state` events (connecting / connected / error)
10. **[NEW] Implemented UDP ingestion listener** (`app/ingestion/udp_listener.py`):
    - Binds to host:port for unicast
    - Optional IPv4 multicast group join
    - asyncio DatagramProtocol for zero-copy datagram dispatch
11. **[NEW] Implemented ingestion manager** (`app/ingestion/ingestion_manager.py`):
    - Creates and tears down TCP/UDP workers per session
    - Broadcasts `message`, `connection_state`, `stats` events via session_manager
    - Periodic stats broadcast every 5 s (messages_received, bytes_received, decode_errors)
12. **[NEW] Wired ingestion to REST API** (`app/main.py`):
    - `POST /sessions/{id}/connect` → `ingestion_manager.start()`
    - `POST /sessions/{id}/disconnect` → `ingestion_manager.stop()`
    - State transitions reflected back into session registry
13. **[NEW] Added test suite** (41 tests, all passing):
    - `tests/test_dlt_parser.py` — 21 parser unit tests
    - `tests/test_sessions_api.py` — 16 REST API tests
    - `tests/test_websocket.py` — 5 WebSocket tests

## Files Added This Checkpoint (Phase 3/4)

- `webbridge/app/ingestion/__init__.py`
- `webbridge/app/ingestion/dlt_parser.py`
- `webbridge/app/ingestion/tcp_client.py`
- `webbridge/app/ingestion/udp_listener.py`
- `webbridge/app/ingestion/ingestion_manager.py`
- `webbridge/tests/__init__.py`
- `webbridge/tests/test_dlt_parser.py`
- `webbridge/tests/test_sessions_api.py`
- `webbridge/tests/test_websocket.py`
- `webbridge/pytest.ini`

## Files Modified This Checkpoint

- `webbridge/app/main.py` — wired ingestion_manager into connect/disconnect
- `webbridge/app/models.py` — added DltMessagePayload, StatsPayload, ErrorPayload
- `webbridge/app/services/session_manager.py` — handle WebSocketDisconnect gracefully
- `webbridge/requirements.txt` — added pytest, pytest-asyncio, httpx

## How To Resume Later

1. Checkout branch:
   ```
   git checkout feature/web-ui-python-bridge-mvp
   ```
2. Setup and run bridge:
   ```
   cd webbridge
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app.main:app --host 127.0.0.1 --port 8008 --reload
   ```
3. Run tests:
   ```
   python -m pytest tests/ -v
   ```
4. Verify APIs:
   - `GET /health`
   - `GET /version`
   - `POST /sessions` (transport, host, port, ecu_id)
   - `POST /sessions/<id>/connect` → starts real TCP/UDP ingestion
   - Connect `ws://127.0.0.1:8008/stream/<session_id>` to see live events

## Next Tasks (Phase 5 — Web UI MVP)

1. Scaffold `webui/` with React + Vite + TypeScript.
2. Build connections page (create/connect/disconnect sessions).
3. Build live log stream page (virtualized table, WebSocket consumer).
4. Add message detail drawer (full field inspection).
5. Add filter bar (ecu/apid/ctid/level text search).
6. Show real-time stats panel (recv rate, decode errors, client lag).

## Notes

- The DLT parser handles both verbose and non-verbose messages. Non-verbose
  payloads are decoded as printable Latin-1 text (hex fallback).
- TCP reconnect uses exponential backoff (2 s → 60 s, factor 2×).
- UDP multicast group join is supported via `multicast_group` + `interface_ip`
  session fields.
- The session registry holds state in memory; it resets on service restart.
- Stats events are emitted every 5 s per active ingestion session.

