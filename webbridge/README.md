# dlt-viewer webbridge

Lightweight Python service that exposes REST and WebSocket APIs for browser-based clients.
Bridges TCP and UDP ECU connections to live WebSocket event streams.

## Implemented

### REST API

| Method | Path                                          | Description                                             |
|--------|-----------------------------------------------|----------------------------------------------------------|
| GET    | `/health`                                     | Liveness check                                          |
| GET    | `/version`                                    | Service version                                         |
| POST   | `/sessions`                                   | Create a new ECU session                                |
| GET    | `/sessions`                                   | List all sessions                                       |
| GET    | `/sessions/{id}`                              | Get session details                                     |
| POST   | `/sessions/{id}/connect`                      | Start TCP/UDP ingestion                                 |
| POST   | `/sessions/{id}/disconnect`                   | Stop ingestion                                          |
| POST   | `/sessions/{id}/control/set-log-level`        | Send SET_LOG_LEVEL control message (TCP only)           |
| POST   | `/sessions/{id}/control/set-verbose-mode`     | Send SET_VERBOSE_MODE control message (TCP only)        |
| GET    | `/sessions/{id}/control/supported-operations` | List control ops supported for the session's transport  |
| WS     | `/stream/{id}`                                | Live event stream                                       |

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

All 50 tests pass (parser unit tests, REST API tests, WebSocket tests, control operation tests).

## Test ECU simulator

To test the bridge without a real ECU, run the synthetic DLT sender:

```bash
python test_ecu_simulator.py --transport tcp --host 127.0.0.1 --port 3490 --count 100 --interval 0.5
```

This will send 100 synthetic DLT messages to the given host:port every 0.5 seconds.

Use this to end-to-end test the full stack:
1. Start the bridge: `uvicorn app.main:app --host 127.0.0.1 --port 8008 --reload`
2. Open <http://127.0.0.1:8008> in your browser (the UI is served by the same process)
3. Create a session via the UI (or REST: `POST /sessions` with `transport=tcp, host=127.0.0.1, port=3490, ecu_id=ECU1`)
4. In the web UI, select the session and click **Connect**
5. Run the simulator: `python test_ecu_simulator.py --host 127.0.0.1 --port 3490`
6. Watch messages appear in the live stream table

## Web UI MVP (Phase 5)

The web UI is embedded directly in the backend as vanilla HTML5 + JavaScript (no build step required).
An earlier React + Vite prototype was replaced with this vanilla implementation to drop the npm
dependency; see `static/index.html`.

**Features:**
- **Connections page**: create sessions, select transport/host/port/ECU, connect/disconnect
- **Live log table**: ECU, APID, CTID, level, payload columns with virtualized scrolling
- **Filter bar**: real-time search by ECU/APID/CTID/level/payload and level-only dropdown
- **Stats panel**: receive rate, traffic bytes, decode errors, client lag
- **Message drawer**: full field inspection with copyable values
- **WebSocket auto-reconnect**: 1.5 s backoff on disconnect

## Control operations (Phase 6)

The message drawer includes a control panel (shown only for connected TCP sessions) for sending
DLT control messages to the ECU:

- **Set log level**: sends `SET_LOG_LEVEL` for the selected message's APID/CTID
- **Set verbose mode**: sends `SET_VERBOSE_MODE` for the selected message's APID/CTID
- **Supported operations**: queried per-session so UDP sessions correctly show no control options

Control messages are send-only — there is no response parsing/acknowledgment yet. See
[`PHASE6_SUMMARY.md`](PHASE6_SUMMARY.md) for the wire format, endpoint contracts, and test coverage.

### Run the full stack

```bash
cd webbridge
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8008 --reload
```

Then open http://127.0.0.1:8008 in your browser.

### Why no npm/Node.js?

The UI is served as static HTML+CSS+JavaScript from the FastAPI backend, making it:
- **Simpler**: single Python process, no separate build/dev server
- **Easier to deploy**: static files embedded in repo, no npm dependencies
- **Faster**: no JavaScript framework overhead
- **Offline-capable**: UI works without external CDNs

## Roadmap

- ✅ **Phase 5**: Web UI MVP — connections page, live log table, message detail drawer, filter bar.
- ✅ **Phase 6**: Control operations (set log level, set verbose mode, supported-operations query).
- **Phase 7** (next): Response handling for `GET_LOG_INFO`/`GET_SOFTWARE_VERSION`, control message
  history in the UI, auth, TLS guidance, Prometheus metrics endpoint. See
  [`PHASE6_SUMMARY.md`](PHASE6_SUMMARY.md#limitations--future-work) for the full list.

