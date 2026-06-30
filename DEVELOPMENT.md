# Development Guide

This document covers setting up and running the dlt-viewer webbridge + web UI in development mode.

## Prerequisites

- **Python 3.11+** with `pip` and `venv`
- **Node.js 18+** with `npm`

## Backend: Webbridge (Python FastAPI)

The webbridge is a REST + WebSocket service that ingests DLT traffic and exposes it via HTTP/WebSocket.

### Setup

```bash
cd webbridge
python -m venv .venv

# Activate the virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Run

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8008 --reload
```

The API is available at http://127.0.0.1:8008.

OpenAPI docs: http://127.0.0.1:8008/docs

### Run tests

```bash
python -m pytest tests/ -v
```

All 41 tests should pass (parser unit tests, REST API integration tests, WebSocket tests).

### Configuration

Copy `.env.example` to `.env` and customize as needed:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `WEBBRIDGE_HOST` | `127.0.0.1` | Bind address |
| `WEBBRIDGE_PORT` | `8008` | Bind port |
| `WEBBRIDGE_LOG_LEVEL` | `info` | Python logging level |
| `WEBBRIDGE_HEARTBEAT_INTERVAL_SEC` | `5.0` | WebSocket heartbeat interval |
| `WEBBRIDGE_CORS_ALLOWED_ORIGINS` | `["http://127.0.0.1:5173","http://localhost:5173"]` | CORS allowed origins |

## Frontend: Web UI (React + Vite)

The web UI is a single-page browser application for managing ECU sessions and inspecting live DLT traffic.

### Setup

```bash
cd webui
npm install
```

### Run

```bash
npm run dev
```

The dev server is available at http://127.0.0.1:5173.

### Build

```bash
npm run build
```

Outputs to `dist/`.

### Configuration

Copy `src/.env.example` to `.env` and customize as needed:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_API_BASE` | `http://127.0.0.1:8008` | Backend API URL |
| `VITE_WS_BASE` | (derived from `VITE_API_BASE`) | Backend WebSocket URL |

## Running the Full Stack

### Terminal 1 — Backend

```bash
cd webbridge
.venv\Scripts\activate    # or: source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8008 --reload
```

### Terminal 2 — Frontend

```bash
cd webui
npm run dev
```

### Using the UI

1. Open http://127.0.0.1:5173 in your browser.
2. On the **Connections** panel:
   - Enter a DLT source (transport, host, port, ECU ID).
   - Click **Create session**.
   - Select the session and click **Connect**.
3. On the **Live stream** panel:
   - Once connected, DLT messages appear in the table.
   - Use the filter bar to search or filter by level.
   - Click a message row to inspect it in the drawer.
4. Watch the stats panel for:
   - Receive rate (messages/second)
   - Total traffic (bytes)
   - Decode errors
   - Client lag (milliseconds)

## Troubleshooting

### Backend won't start

- Ensure Python 3.11+ is installed.
- Verify `.venv` is activated: Windows should show `(.venv)` in the prompt.
- Check port 8008 is not in use: `netstat -an | findstr :8008` (Windows) or `lsof -i :8008` (macOS/Linux).

### Frontend dev server won't start

- Ensure Node.js 18+ is installed: `node --version`.
- Delete `node_modules/` and `.next/` (if present) and try `npm install` again.
- Check port 5173 is not in use.

### WebSocket connection fails

- Confirm the backend is running and accessible at the API base URL.
- Check browser console (F12) for error messages.
- Verify `WEBBRIDGE_CORS_ALLOWED_ORIGINS` includes `http://127.0.0.1:5173` or your frontend URL.

### No DLT messages appear

- Verify the session is in the `connected` state (watch the state pill in the session card).
- Ensure the DLT source (ECU) is sending traffic to the configured host:port.
- Check the backend logs for decode errors.

## Git Workflow

This project uses feature branches for Phase-based development.

```bash
# Current branch
git branch -v

# Pull latest main
git checkout main
git pull origin main

# Create a feature branch
git checkout -b feature/next-phase

# After committing changes
git push origin feature/next-phase

# Open a pull request on GitHub
```

## Documentation

- **Architecture**: [doc/HLD.md](doc/HLD.md), [doc/LLD.md](doc/LLD.md)
- **Implementation progress**: [doc/web-ui-implementation-progress.md](doc/web-ui-implementation-progress.md)
- **Phased roadmap**: [doc/web-ui-python-socket-websocket-plan.md](doc/web-ui-python-socket-websocket-plan.md)

## What's Next

Phase 5 continues with:
- Session persistence and saved presets
- Richer table affordances (sticky columns, copy actions)
- End-to-end browser tests
- Load testing and performance tuning

Phase 6 will introduce control operations (set log level, get log info) and server-side filtering.
