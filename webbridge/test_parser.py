#!/usr/bin/env python3
"""
Test DLT parser directly with known good data.
"""
from app.ingestion.dlt_parser import parse_messages
import binascii

# Raw data from the simulator (3 messages, 60 bytes each)
raw_hex = "01003a3f002e45435531000000000405ea690303534e4d41494e000020000f0054657374206d65737361676520300060000000000000001000000001" \
          "01003a3f002e45435531000000000405fe400303534e4d41494e000020000f0054657374206d657373616765203100600000006400000010000000" \
          "0001003a3f002e4543553100000000040612370303534e4d41494e000020000f0054657374206d6573736167652032006000000000000000100000000100"

raw_data = binascii.unhexlify(raw_hex)
print(f"Raw data: {len(raw_data)} bytes")
print(f"First 50 bytes: {raw_data[:50]}")

messages, remaining = parse_messages(raw_data)
print(f"\nParsed: {len(messages)} messages")
print(f"Remaining: {len(remaining)} bytes")

for i, msg in enumerate(messages):
    print(f"\nMessage {i}:")
    print(f"  ECU: {msg.ecu_id}")
    print(f"  APID/CTID: {msg.apid}/{msg.ctid}")
    print(f"  Type: {msg.msg_type}")
    print(f"  Level: {msg.log_level}")
    print(f"  Payload: {msg.payload_text}")
    print(f"  Error: {msg.decode_error}")
