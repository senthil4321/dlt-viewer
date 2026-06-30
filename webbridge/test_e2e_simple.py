#!/usr/bin/env python3
"""
Simplified E2E test - just verify connection succeeds.
"""
import asyncio
import subprocess
import sys
import time
from fastapi.testclient import TestClient
from app.main import app

async def test_e2e_simple():
    client = TestClient(app)

    print("STEP 1: Create session")
    session_req = {
        "transport": "tcp",
        "host": "127.0.0.1",
        "port": 3490,
        "ecu_id": "ECU1"
    }
    resp = client.post("/sessions", json=session_req)
    session = resp.json()
    session_id = session["session_id"]
    print(f"[OK] Session created: {session_id}")

    print("\nSTEP 2: Start simulator")
    sim_cmd = [
        sys.executable,
        "test_ecu_simulator.py",
        "--transport", "tcp",
        "--host", "127.0.0.1",
        "--port", "3490",
        "--count", "20",
        "--interval", "0.2"
    ]
    sim_proc = subprocess.Popen(
        sim_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    print("[OK] Simulator started")
    await asyncio.sleep(2)

    print("\nSTEP 3: Connect session")
    conn_resp = client.post(f"/sessions/{session_id}/connect")
    print(f"[OK] Connection started")
    
    print("\nSTEP 4: Wait for connection to establish")
    for i in range(20):
        await asyncio.sleep(0.5)
        session_check = client.get(f"/sessions/{session_id}")
        state = session_check.json()["state"]
        if state == "connected":
            print(f"[OK] Connected after {i*0.5:.1f}s")
            break
    else:
        print(f"[WARN] Still {state} after 10s")

    print("\nSTEP 5: Wait a bit more for messages")
    await asyncio.sleep(2)

    print("\nSTEP 6: Final check")
    final = client.get(f"/sessions/{session_id}").json()
    print(f"Final state: {final['state']}")
    
    if final['state'] == "connected":
        print("\n[OK] END-TO-END TEST PASSED - Backend successfully connected to simulator")
        result = "PASS"
    else:
        print(f"\n[FAIL] Final state is {final['state']}, expected 'connected'")
        result = "FAIL"

    # Cleanup
    try:
        sim_proc.terminate()
        sim_proc.wait(timeout=5)
    except:
        sim_proc.kill()

    return result

if __name__ == "__main__":
    result = asyncio.run(test_e2e_simple())
    exit(0 if result == "PASS" else 1)
