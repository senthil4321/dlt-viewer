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
    service_id: int,
    request_data: bytes = b"",
) -> bytes:
    """Build a DLT control message.

    Control messages are sent TO an ECU (the bridge becomes a client).

    Per the DLT control-message spec, the *target* apid/ctid for services
    like SET_LOG_LEVEL live inside ``request_data`` (the service-specific
    payload), not the extended header. The extended header's apid/ctid
    identify the sender of the control request, which the daemon does not
    use for routing, so a fixed placeholder is used here.

    Args:
        service_id: Control service ID (e.g. CTRL_SET_LOG_LEVEL)
        request_data: Service-specific request data

    Returns:
        Complete DLT control message (network format, no storage header)
    """

    # Extended header for control message
    # msin: bit0=verbose(0), bits3-1=mstp (3=control), bits7-4=mtin
    # mtin=1 marks this a control REQUEST (2=response, 3=time) — required
    # for the daemon to recognize and act on the message.
    DLT_CONTROL_REQUEST = 0x01
    msin = (DLT_CONTROL_REQUEST << 4) | (0x03 << 1)
    noar = 0  # no arguments for control messages

    ext_header = struct.pack("!BB", msin, noar)
    ext_header += b"REMO"  # sender apid placeholder (not used for routing)
    ext_header += b"REMO"  # sender ctid placeholder (not used for routing)

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

    Wire payload matches the DLT spec's ``DltServiceSetLogLevel`` struct:
    apid(4) + ctid(4) + log_level(int8) + com_interface(4).

    Args:
        apid: Target application ID
        ctid: Target context ID
        log_level: New log level (1-6: fatal, error, warn, info, debug, verbose)

    Returns:
        DLT control message
    """
    request_data = (
        apid.ljust(4, "\x00").encode()[:4]
        + ctid.ljust(4, "\x00").encode()[:4]
        + struct.pack("!b", log_level)
        + b"\x00" * 4  # com_interface, unused
    )
    return build_control_message(CTRL_SET_LOG_LEVEL, request_data)


def build_get_log_info_request(
    apid: str,
    ctid: str,
    options: int = 7,
) -> bytes:
    """Build a GET_LOG_INFO control request.

    Wire payload matches ``DltServiceGetLogInfoRequest``:
    options(int8) + apid(4) + ctid(4) + com_interface(4).

    Args:
        apid: Target application ID
        ctid: Target context ID
        options: Info detail level (7 = all context/app descriptions)

    Returns:
        DLT control message
    """
    request_data = (
        struct.pack("!b", options)
        + apid.ljust(4, "\x00").encode()[:4]
        + ctid.ljust(4, "\x00").encode()[:4]
        + b"\x00" * 4  # com_interface, unused
    )
    return build_control_message(CTRL_GET_LOG_INFO, request_data)


def build_get_software_version_request() -> bytes:
    """Build a GET_SOFTWARE_VERSION control request.

    This service is ECU-wide (no apid/ctid in the DLT spec's
    ``DltServiceGetSoftwareVersion`` request, which carries only the
    service ID).

    Returns:
        DLT control message
    """
    return build_control_message(CTRL_GET_SOFTWARE_VERSION)


def build_set_verbose_mode_request(verbose: bool) -> bytes:
    """Build a SET_VERBOSE_MODE control request.

    This service is daemon-wide per the DLT spec's
    ``DltServiceSetVerboseMode`` struct (service_id + new_status only) —
    there is no per-apid/ctid targeting.

    Args:
        verbose: True to enable verbose mode, False to disable

    Returns:
        DLT control message
    """
    request_data = struct.pack("!B", 1 if verbose else 0)
    return build_control_message(CTRL_SET_VERBOSE_MODE, request_data)
