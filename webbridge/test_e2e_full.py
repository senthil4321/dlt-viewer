#!/usr/bin/env python3
"""
Full end-to-end test: simulator → backend → WebSocket.
"""
import asyncio
import json
import time
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

async def main():
    client = TestClient(app)

    # Step 1: Create session
    print("=" * 60)
    print("STEP 1: Create session")
    print("=" * 60)
    session_req = {
        "transport": "tcp",
        "host": "127.0.0.1",
        "port": 3490,
        "ecu_id": "ECU1"
    }
    resp = client.post("/sessions", json=session_req)
    assert resp.status_code == 200, f"Failed to create session: {resp.text}"
    session = resp.json()
    session_id = session["session_id"]
    print(f"[OK] Created session: {session_id}")
    print(f"     State: {session['state']}")

    # Step 2: Start simulator in background
    print("\n" + "=" * 60)
    print("STEP 2: Start simulator")
    print("=" * 60)
    import subprocess
    import sys
    
    sim_cmd = [
        sys.executable,
        "test_ecu_simulator.py",
        "--transport", "tcp",
        "--host", "127.0.0.1",
        "--port", "3490",
        "--count", "30",
        "--interval", "0.3"
    ]
    sim_proc = subprocess.Popen(
        sim_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    print(f"[OK] Simulator started (PID {sim_proc.pid})")
    print("      Waiting for simulator to start listening...")
    await asyncio.sleep(2)

    # Step 3: Connect session (triggers backend to connect to simulator)
    print("\n" + "=" * 60)
    print("STEP 3: Connect session")
    print("=" * 60)
    conn_resp = client.post(f"/sessions/{session_id}/connect")
    assert conn_resp.status_code == 200, f"Failed to connect: {conn_resp.text}"
    conn_data = conn_resp.json()
    print(f"[OK] Connection started")
    print(f"     State: {conn_data['state']}")
    print(f"     Message: {conn_data['message']}")

    # Step 4: Wait for messages and check stats
    print("\n" + "=" * 60)
    print("STEP 4: Monitoring messages (waiting up to 20s)")
    print("=" * 60)
    start = time.time()
    max_wait = 20
    last_count = 0
    
    while time.time() - start < max_wait:
        session_check = client.get(f"/sessions/{session_id}")
        assert session_check.status_code == 200
        session_data = session_check.json()
        
        stats = session_data.get("stats", {})
        msg_count = stats.get("dlt_messages_received", 0)
        
        if msg_count > last_count:
            elapsed = time.time() - start
            print(f"      [{elapsed:.1f}s] Messages received: {msg_count}")
            last_count = msg_count
        
        # Stop checking if we got messages
        if msg_count >= 20:
            print(f"\n[OK] Successfully received {msg_count} messages!")
            break
        
        await asyncio.sleep(0.5)
    
    # Step 5: Final check
    print("\n" + "=" * 60)
    print("STEP 5: Final session state")
    print("=" * 60)
    final_session = client.get(f"/sessions/{session_id}").json()
    final_stats = final_session.get("stats", {})
    print(f"State: {final_session['state']}")
    print(f"Messages received: {final_stats.get('dlt_messages_received', 0)}")
    print(f"Bytes received: {final_stats.get('bytes_received', 0)}")
    
    if final_stats.get('dlt_messages_received', 0) >= 20:
        print("\n" + "=" * 60)
        print("[OK] END-TO-END TEST PASSED!")
        print("=" * 60)
        result = "PASS"
    else:
        print("\n" + "=" * 60)
        print("[FAIL] END-TO-END TEST FAILED - Not enough messages received")
        print("=" * 60)
        result = "FAIL"

    # Cleanup
    try:
        sim_proc.terminate()
        sim_proc.wait(timeout=5)
    except:
        sim_proc.kill()
    
    return result

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result == "PASS" else 1)
