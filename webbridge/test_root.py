#!/usr/bin/env python3
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
resp = client.get("/")
print(f"Status: {resp.status_code}")
print(f"Content-Type: {resp.headers.get('content-type', 'N/A')}")
if resp.status_code == 200:
    print(f"HTML length: {len(resp.text)}")
    print(f"Preview: {resp.text[:200]}")
else:
    print(f"Error: {resp.text}")
