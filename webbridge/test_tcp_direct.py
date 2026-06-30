#!/usr/bin/env python3
"""
Direct test of TCP client + DLT parser.
"""
import asyncio
import subprocess
import sys
from app.ingestion.tcp_client import TcpIngestionClient

async def test_direct_tcp_ingestion():
    print("Starting simulator...")
    
    # Start simulator
    sim_cmd = [
        sys.executable,
        "test_ecu_simulator.py",
        "--transport", "tcp",
        "--host", "127.0.0.1",
        "--port", "3490",
        "--count", "10",
        "--interval", "0.3"
    ]
    sim_proc = subprocess.Popen(
        sim_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for simulator to start
    await asyncio.sleep(2)
    
    messages_received = []
    states_received = []
    
    async def on_message(session_id: str, msg):
        messages_received.append(msg)
        print(f"  Message: {msg.ecu_id} {msg.apid}/{msg.ctid} '{msg.payload_text}'")
    
    async def on_state(session_id: str, state: str, error: str | None):
        states_received.append((state, error))
        print(f"  State: {state}" + (f" ({error})" if error else ""))
    
    # Create TCP client
    client = TcpIngestionClient(
        session_id="test-123",
        host="127.0.0.1",
        port=3490,
        on_message=on_message,
        on_state=on_state,
    )
    
    # Start client
    client.start()
    print("TCP client started, waiting for messages...")
    
    # Wait for messages
    await asyncio.sleep(8)
    
    # Stop client
    await client.stop()
    print("TCP client stopped")
    
    print(f"\n[RESULT] Messages received: {len(messages_received)}")
    print(f"[RESULT] States: {states_received}")
    
    # Cleanup
    try:
        sim_proc.terminate()
        sim_proc.wait(timeout=5)
    except:
        sim_proc.kill()
    
    return len(messages_received) > 0

if __name__ == "__main__":
    result = asyncio.run(test_direct_tcp_ingestion())
    exit(0 if result else 1)
