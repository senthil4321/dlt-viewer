# dlt-viewer webbridge

Lightweight Python service that exposes REST and WebSocket APIs for browser-based clients.
Bridges TCP and UDP ECU connections to live WebSocket event streams.

## Implemented

### REST API

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/health`                           | Liveness check |
| GET    | `/version`                          | Service version |
| POST   | `/sessions`                         | Create a new ECU session |
| GET    | `/sessions`                         | List all sessions |
| GET    | `/sessions/{id}`                    | Get session details |
| POST   | `/sessions/{id}/connect`            | Start TCP/UDP ingestion |
| POST   | `/sessions/{id}/disconnect`         | Stop ingestion |
| WS     | `/stream/{id}`                      | Live event stream |

### WebSocket event types

All events use the `EventEnvelope` schema:

```json
{
  "type": "heartbeat | message | connection_state | stats | error",
  "timestamp": "2026-06-30T12:00:00Z",
  "session_id": "<uuid>",
  "seq": 42,
  "payload": { ... }
}
```

| Event type         | Payload fields | When emitted |
|--------------------|----------------|--------------|
| `heartbeat`        | `message`      | Every 5 s while connected |
| `connection_state` | `state`, `transport`, `host`, `port`, `ecu_id`, `[error]` | On connect/reconnect/error/disconnect |
| `message`          | `ecu_id`, `apid`, `ctid`, `msg_type`, `log_level`, `verbose`, `mcnt`, `timestamp_sec`, `payload_text`, `[decode_error]` | For every decoded DLT message |
| `stats`            | `messages_received`, `bytes_received`, `decode_errors` | Every 5 s while ingesting |

### Ingestion engine

- **TCP client** (`app/ingestion/tcp_client.py`): async TCP connection with
  exponential-backoff reconnect (2 s → 60 s).  Reconnect fires automatically
  on remote close or network error.
- **UDP listener** (`app/ingestion/udp_listener.py`): binds to host:port with
  optional IPv4 multicast group join.
- **DLT parser** (`app/ingestion/dlt_parser.py`): pure-Python streaming DLT
  framing and decoding — handles split frames, byte-level resync, verbose
  argument extraction (bool / int / float / string / raw), and big/little endian
  payloads.
- **Ingestion manager** (`app/ingestion/ingestion_manager.py`): creates and
  tears down workers per session; broadcasts stats every 5 s.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8008 --reload
```

Open:
- http://127.0.0.1:8008/health
- http://127.0.0.1:8008/docs  ← interactive OpenAPI UI

## Example session flow

```bash
# 1. Create a TCP session
curl -X POST http://127.0.0.1:8008/sessions \
  -H "content-type: application/json" \
  -d '{"transport":"tcp","host":"127.0.0.1","port":3490,"ecu_id":"ECU1"}'

# 2. Open WebSocket stream in a separate terminal / browser
#    ws://127.0.0.1:8008/stream/<SESSION_ID>

# 3. Start ingestion (real TCP connect + DLT framing)
curl -X POST http://127.0.0.1:8008/sessions/<SESSION_ID>/connect

# 4. Stop ingestion
curl -X POST http://127.0.0.1:8008/sessions/<SESSION_ID>/disconnect
```

## Running tests

```bash
python -m pytest tests/ -v
```

All 41 tests pass (parser unit tests, REST API tests, WebSocket tests).

## Web UI MVP

Phase 5 now includes a React + Vite frontend scaffold in `../webui` with:

- session creation and connect/disconnect controls
- live WebSocket stream subscription with reconnect
- filter bar for ecu/apid/ctid/level/payload text
- stats cards for receive rate, traffic, decode errors, and client lag
- message detail drawer and virtualized log list

Run it with:

```bash
cd ..\webui
npm install
npm run dev
```

The FastAPI bridge enables CORS for `http://127.0.0.1:5173` and
`http://localhost:5173` by default.

## Next implementation slice

- **Phase 5**: Web UI MVP (React + Vite) — connections page, live log table,
  message detail drawer, filter bar.
- **Phase 6**: Control operations (set log level, get log info) and server-side
  filter pipeline.
- **Phase 7**: Auth, TLS guidance, Prometheus metrics endpoint.

