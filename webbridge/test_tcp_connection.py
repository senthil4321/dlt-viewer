#!/usr/bin/env python3
"""
Test TCP communication between simulator and backend.
"""
import asyncio
import subprocess
import sys
import time

async def test_tcp_connection():
    print("Starting simulator on 127.0.0.1:3490...")
    
    # Start simulator
    sim_cmd = [
        sys.executable,
        "test_ecu_simulator.py",
        "--transport", "tcp",
        "--host", "127.0.0.1",
        "--port", "3490",
        "--count", "5",
        "--interval", "0.5"
    ]
    sim_proc = subprocess.Popen(
        sim_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for simulator to start
    await asyncio.sleep(2)
    
    print("Connecting to simulator as a test client...")
    try:
        # Try to connect as a client
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", 3490),
            timeout=5.0
        )
        print("[OK] Connected to simulator!")
        
        # Try to read some data
        data = await asyncio.wait_for(reader.read(100), timeout=5.0)
        if data:
            print(f"[OK] Received {len(data)} bytes from simulator")
            print(f"     First 50 bytes: {data[:50]}")
        else:
            print("[FAIL] Simulator closed connection immediately")
        
        writer.close()
        await writer.wait_closed()
        
    except asyncio.TimeoutError:
        print("[FAIL] Connection timeout")
    except Exception as e:
        print(f"[FAIL] Connection error: {e}")
    finally:
        try:
            sim_proc.terminate()
            sim_proc.wait(timeout=5)
        except:
            sim_proc.kill()

if __name__ == "__main__":
    asyncio.run(test_tcp_connection())
