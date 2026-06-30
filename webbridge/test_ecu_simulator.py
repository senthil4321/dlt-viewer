#!/usr/bin/env python
"""
Synthetic DLT ECU simulator for testing the webbridge.

Sends realistic DLT messages to a TCP or UDP destination at configurable intervals.
Usage:
    python test_ecu_simulator.py --help
    python test_ecu_simulator.py --transport tcp --host 127.0.0.1 --port 3490 --count 100
"""

import argparse
import asyncio
import struct
import time
from typing import Literal
from uuid import uuid4

# DLT header constants
DLT_PATTERN = b"DLT\x01"  # Storage header
HTYP_STANDARD_HEADER = 0x20  # 1 UEH (standard header)
HTYP_WITH_ECU_ID = 0x04
HTYP_WITH_SESSION_ID = 0x08
HTYP_WITH_TIMESTAMP = 0x10
HTYP_EXTENDED_HEADER = 0x01
HTYP_VERBOSE = 0x02

# Message types and levels
MSG_TYPE_LOG = 0  # DLT_TYPE_LOG
LOG_LEVEL_FATAL = 1
LOG_LEVEL_ERROR = 2
LOG_LEVEL_WARN = 3
LOG_LEVEL_INFO = 4
LOG_LEVEL_DEBUG = 5
LOG_LEVEL_VERBOSE = 6

# Verbose mode argument types
ARG_TYPE_BOOL = 16
ARG_TYPE_SINT = 32
ARG_TYPE_UINT = 64
ARG_TYPE_FLOA = 128
ARG_TYPE_STRG = 0x00200000
ARG_TYPE_RAWD = 0x01000000


def encode_verbose_argument(value: int | float | str | bool) -> bytes:
    """Encode a single verbose argument."""
    if isinstance(value, bool):
        type_code = ARG_TYPE_BOOL
        data = struct.pack("B", 1 if value else 0)
    elif isinstance(value, int):
        if value < 0:
            type_code = ARG_TYPE_SINT | 16  # 16-bit signed
            data = struct.pack("<h", value)
        else:
            type_code = ARG_TYPE_UINT | 32  # 32-bit unsigned
            data = struct.pack("<I", value)
    elif isinstance(value, float):
        type_code = ARG_TYPE_FLOA | 64  # 64-bit float
        data = struct.pack("<d", value)
    elif isinstance(value, str):
        type_code = ARG_TYPE_STRG
        encoded = value.encode("utf-8") + b"\x00"
        data = struct.pack("<H", len(encoded)) + encoded
    else:
        raise TypeError(f"Unsupported argument type: {type(value)}")

    return struct.pack("<I", type_code) + data


def build_dlt_message(
    ecu_id: str = "ECU1",
    apid: str = "TEST",
    ctid: str = "APP1",
    level: int = LOG_LEVEL_INFO,
    arguments: list | None = None,
) -> bytes:
    """Build a complete DLT message with verbose arguments."""
    if arguments is None:
        arguments = []

    # Build verbose payload
    payload = b""
    noar = 0  # number of arguments
    for arg in arguments:
        payload += encode_verbose_argument(arg)
        noar += 1

    # Build extended header
    mtin = (MSG_TYPE_LOG << 4) | level  # msg type in upper nibble, level in lower
    msin = 0x01 | (0x01 << 1)  # verbose and log message
    ext_header = struct.pack(
        "!BBBB",
        msin,
        noar,
        ord(apid[0]),
        ord(apid[1]) if len(apid) > 1 else 0,
    )
    ext_header += ctid.ljust(4, "\x00").encode()[:4]

    # Build standard header
    ecui = ecu_id.ljust(4, "\x00").encode()[:4]
    session_id = struct.pack("!I", 0)  # session ID = 0
    timestamp = struct.pack("!I", int(time.time() * 10000) & 0xFFFFFFFF)

    htyp = (
        HTYP_STANDARD_HEADER
        | HTYP_WITH_ECU_ID
        | HTYP_WITH_SESSION_ID
        | HTYP_WITH_TIMESTAMP
        | HTYP_EXTENDED_HEADER
        | HTYP_VERBOSE
    )

    std_header_core = struct.pack("!BH", htyp, len(ext_header) + len(payload) + 4)
    std_header = std_header_core + ecui + session_id + timestamp

    # Message counter (mcnt) and length
    mcnt = struct.pack("!B", 1)
    msg_len = struct.pack("!H", len(std_header) + 1 + len(ext_header) + len(payload))

    # Full message (without storage header for UDP)
    dlt_message = mcnt + msg_len + std_header + ext_header + payload

    return dlt_message


async def send_messages_tcp(host: str, port: int, ecu_id: str, count: int, interval: float) -> None:
    """Send DLT messages via TCP (as a server listening for client connections)."""
    
    client_ready = asyncio.Event()
    messages_sent = 0
    
    async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal messages_sent
        peer_addr = writer.get_extra_info('peername')
        print(f"Client connected from {peer_addr}")
        client_ready.set()
        
        try:
            for i in range(count):
                level = [LOG_LEVEL_ERROR, LOG_LEVEL_WARN, LOG_LEVEL_INFO, LOG_LEVEL_DEBUG][i % 4]
                message = build_dlt_message(
                    ecu_id=ecu_id,
                    apid="SNDR",
                    ctid="MAIN",
                    level=level,
                    arguments=[f"Test message {i}", i * 100, i % 2 == 0],
                )
                writer.write(message)
                await writer.drain()
                print(f"[{i+1}/{count}] Sent message (level={level})")
                messages_sent += 1
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            print(f"Client {peer_addr} disconnected")
    
    server = await asyncio.start_server(handle_connection, host, port)
    print(f"ECU simulator listening on {host}:{port} (waiting for client...)")
    
    async with server:
        # Wait for client connection with a timeout
        try:
            await asyncio.wait_for(client_ready.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            print("Timeout waiting for client connection. Exiting.")
            return
        
        # Give the client time to receive all messages
        await asyncio.sleep(count * interval + 2)


async def send_messages_udp(host: str, port: int, ecu_id: str, count: int, interval: float) -> None:
    """Send DLT messages via UDP."""
    loop = asyncio.get_event_loop()
    sock = __import__("socket").socket(__import__("socket").AF_INET, __import__("socket").SOCK_DGRAM)
    sock.setblocking(False)

    print(f"Sending to {host}:{port} via UDP")

    try:
        for i in range(count):
            level = [LOG_LEVEL_ERROR, LOG_LEVEL_WARN, LOG_LEVEL_INFO, LOG_LEVEL_DEBUG][i % 4]
            message = build_dlt_message(
                ecu_id=ecu_id,
                apid="SNDR",
                ctid="MAIN",
                level=level,
                arguments=[f"Test message {i}", i * 100, i % 2 == 0],
            )
            await loop.sock_sendto(sock, message, (host, port))
            print(f"[{i+1}/{count}] Sent message (level={level})")
            await asyncio.sleep(interval)
    finally:
        sock.close()
    print("Done.")


async def main():
    parser = argparse.ArgumentParser(description="Synthetic DLT ECU simulator")
    parser.add_argument("--transport", choices=["tcp", "udp"], default="tcp", help="Transport protocol")
    parser.add_argument("--host", default="127.0.0.1", help="Destination host")
    parser.add_argument("--port", type=int, default=3490, help="Destination port")
    parser.add_argument("--ecu-id", default="ECU1", help="ECU identifier")
    parser.add_argument("--count", type=int, default=50, help="Number of messages to send")
    parser.add_argument("--interval", type=float, default=0.5, help="Interval between messages (seconds)")

    args = parser.parse_args()

    print(f"Simulating ECU {args.ecu_id} with {args.transport.upper()} to {args.host}:{args.port}")
    print(f"Sending {args.count} messages with {args.interval}s interval\n")

    if args.transport == "tcp":
        await send_messages_tcp(args.host, args.port, args.ecu_id, args.count, args.interval)
    else:
        await send_messages_udp(args.host, args.port, args.ecu_id, args.count, args.interval)


if __name__ == "__main__":
    asyncio.run(main())
