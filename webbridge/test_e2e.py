#!/usr/bin/env python3
import time
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Create a session
session_req = {
    "transport": "tcp",
    "host": "127.0.0.1", 
    "port": 3490,
    "ecu_id": "ECU1"
}
resp = client.post("/sessions", json=session_req)
print(f"Create session: {resp.status_code}")
session = resp.json()
print(f"Session ID: {session['session_id']}")
print(f"Session state: {session['state']}")

# Try to connect
conn_resp = client.post(f"/sessions/{session['session_id']}/connect")
print(f"Connect response: {conn_resp.status_code}")
print(f"Connect result: {conn_resp.json()}")

# Wait a moment
time.sleep(2)

# Check session state
check_resp = client.get(f"/sessions/{session['session_id']}")
updated_session = check_resp.json()
print(f"Updated state: {updated_session['state']}")
print(f"Stats: {updated_session.get('stats', {})}")
