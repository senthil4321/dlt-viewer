#!/usr/bin/env python3
from fastapi.testclient import TestClient
from app.main import app
import json

client = TestClient(app)

# Create a session
session_req = {
    "transport": "tcp",
    "host": "127.0.0.1", 
    "port": 3490,
    "ecu_id": "ECU1"
}
resp = client.post("/sessions", json=session_req)
session = resp.json()
print("Session response:")
print(json.dumps(session, indent=2, default=str))
