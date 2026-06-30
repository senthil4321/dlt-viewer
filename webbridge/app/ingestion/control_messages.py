"""DLT Control message construction and handling.

DLT Control operations allow remote management of ECUs:
- SET_LOG_LEVEL: Change the log level of an application
- GET_LOG_INFO: Query current log levels and software version
- GET_VERBOSE_MODE: Query verbose mode setting
- SET_VERBOSE_MODE: Enable/disable verbose mode
"""

from __future__ import annotations

import struct
import time
from typing import Literal

# Control message type codes
CTRL_SET_LOG_LEVEL = 0x01
CTRL_SET_TRACE_STATUS = 0x02
CTRL_GET_LOG_INFO = 0x03
CTRL_GET_DEFAULT_LOG_LEVEL = 0x04
CTRL_STORE_CONFIG = 0x05
CTRL_RESET_TO_FACTORY_DEFAULT = 0x06
CTRL_SET_MESSAGE_FILTERING = 0x09
CTRL_SET_DEFAULT_LOG_LEVEL = 0x11
CTRL_SET_DEFAULT_TRACE_STATUS = 0x12
CTRL_GET_VERBOSE_MODE = 0x19
CTRL_SET_VERBOSE_MODE = 0x1A
CTRL_GET_USE_ECU_ID = 0x1B
CTRL_SET_USE_ECU_ID = 0x1C
CTRL_GET_USE_SESSION_ID = 0x1D
CTRL_SET_USE_SESSION_ID = 0x1E
CTRL_GET_USE_TIMESTAMP = 0x1F
CTRL_SET_USE_TIMESTAMP = 0x20
CTRL_GET_USE_EXTENDED_HEADER = 0x21
CTRL_SET_USE_EXTENDED_HEADER = 0x22
CTRL_GET_SOFTWARE_VERSION = 0x23
CTRL_MESSAGE_BUFFER_OVERFLOW = 0x24

# Log level codes
LOG_LEVEL_FATAL = 1
LOG_LEVEL_ERROR = 2
LOG_LEVEL_WARN = 3
LOG_LEVEL_INFO = 4
LOG_LEVEL_DEBUG = 5
LOG_LEVEL_VERBOSE = 6


def build_control_message(
    apid: str,
    ctid: str,
    service_id: int,
    request_data: bytes = b"",
) -> bytes:
    """Build a DLT control message.
    
    Control messages are sent TO an ECU (the bridge becomes a client).
    
    Args:
        apid: Application ID (4 chars, null-padded)
        ctid: Context ID (4 chars, null-padded)
        service_id: Control service ID (e.g. CTRL_SET_LOG_LEVEL)
        request_data: Service-specific request data
        
    Returns:
        Complete DLT control message (network format, no storage header)
    """
    
    # Extended header for control message
    # msin: bit0=verbose(0), bits3-1=mstp (3=control), bits7-4=reserved
    msin = 0x03 << 1  # mstp=3 (control), non-verbose
    noar = 0  # no arguments for control messages
    
    ext_header = struct.pack(
        "!BBBB",
        msin,
        noar,
        ord(apid[0]) if apid else 0,
        ord(apid[1]) if len(apid) > 1 else 0,
    )
    ext_header += ctid.ljust(4, "\x00").encode()[:4]
    
    # Control message data: service_id (uint32 big-endian) + request data
    ctrl_data = struct.pack("!I", service_id) + request_data
    
    # Standard header
    htyp = 0x20 | 0x04 | 0x08 | 0x10 | 0x01  # STD | WEID | WSID | WTMS | UEH
    ecui = b"ECU\x00"  # Placeholder ECU ID (client, not server)
    session_id = struct.pack("!I", 0)
    timestamp = struct.pack("!I", int(time.time() * 10000) & 0xFFFFFFFF)
    
    total_len = 4 + len(ecui) + len(session_id) + len(timestamp) + len(ext_header) + len(ctrl_data)
    
    mcnt = struct.pack("!B", 1)
    
    message = (
        struct.pack("!B", htyp) +
        mcnt +
        struct.pack("!H", total_len) +
        ecui +
        session_id +
        timestamp +
        ext_header +
        ctrl_data
    )
    
    return message


def build_set_log_level_request(
    apid: str,
    ctid: str,
    log_level: int,
) -> bytes:
    """Build a SET_LOG_LEVEL control request.
    
    Args:
        apid: Application ID
        ctid: Context ID
        log_level: New log level (1-6: fatal, error, warn, info, debug, verbose)
        
    Returns:
        DLT control message
    """
    # Request data: log_level (1 byte) + 7 padding bytes
    request_data = struct.pack("!B", log_level) + b"\x00" * 7
    return build_control_message(apid, ctid, CTRL_SET_LOG_LEVEL, request_data)


def build_get_log_info_request(
    apid: str,
    ctid: str,
) -> bytes:
    """Build a GET_LOG_INFO control request.
    
    Args:
        apid: Application ID
        ctid: Context ID
        
    Returns:
        DLT control message
    """
    return build_control_message(apid, ctid, CTRL_GET_LOG_INFO)


def build_get_software_version_request(
    apid: str,
    ctid: str,
) -> bytes:
    """Build a GET_SOFTWARE_VERSION control request.
    
    Args:
        apid: Application ID
        ctid: Context ID
        
    Returns:
        DLT control message
    """
    return build_control_message(apid, ctid, CTRL_GET_SOFTWARE_VERSION)


def build_set_verbose_mode_request(
    apid: str,
    ctid: str,
    verbose: bool,
) -> bytes:
    """Build a SET_VERBOSE_MODE control request.
    
    Args:
        apid: Application ID
        ctid: Context ID
        verbose: True to enable verbose mode, False to disable
        
    Returns:
        DLT control message
    """
    request_data = struct.pack("!B", 1 if verbose else 0) + b"\x00" * 7
    return build_control_message(apid, ctid, CTRL_SET_VERBOSE_MODE, request_data)
