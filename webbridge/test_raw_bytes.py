#!/usr/bin/env python3
"""
Test to see raw bytes being sent by simulator.
"""
import asyncio
import subprocess
import sys

async def test_raw_bytes():
    print("Starting simulator...")
    
    # Start simulator
    sim_cmd = [
        sys.executable,
        "test_ecu_simulator.py",
        "--transport", "tcp",
        "--host", "127.0.0.1",
        "--port", "3490",
        "--count", "3",
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
    
    print("Connecting to simulator as raw TCP client...")
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 3490)
        print("[OK] Connected")
        
        # Read raw data
        data = b""
        while True:
            try:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=2.0)
                if not chunk:
                    print("[INFO] Server closed connection")
                    break
                data += chunk
                print(f"[RX] {len(chunk)} bytes: {chunk[:60].hex()}...")
            except asyncio.TimeoutError:
                print("[INFO] No more data")
                break
        
        print(f"\n[TOTAL] Received {len(data)} bytes total")
        if data:
            print(f"First 100 bytes (hex): {data[:100].hex()}")
            print(f"First 100 bytes (repr): {repr(data[:100])}")
        
        writer.close()
        await writer.wait_closed()
        
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        try:
            sim_proc.terminate()
            sim_proc.wait(timeout=5)
        except:
            sim_proc.kill()

if __name__ == "__main__":
    asyncio.run(test_raw_bytes())
