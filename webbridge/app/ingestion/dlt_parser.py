"""Pure-Python DLT message framing and decoding for network streams.

DLT Standard Header layout (network / TCP framing — no storage header prefix):

  byte 0   : htyp  (header-type flags)
  byte 1   : mcnt  (message counter 0–255, wraps)
  bytes 2-3: len   (uint16 big-endian, total length INCLUDING standard header)
  [WEID]   : 4 bytes ECU ID  (ASCII, null-padded)
  [WSID]   : 4 bytes session ID (uint32 big-endian)
  [WTMS]   : 4 bytes timestamp  (uint32 big-endian, units 0.1 ms)

Extended Header (10 bytes, present when htyp & HTYP_UEH):

  byte 0   : msin  (message info)
  byte 1   : noar  (number of arguments)
  bytes 2-5: apid  (application ID, ASCII null-padded)
  bytes 6-9: ctid  (context ID, ASCII null-padded)

msin bit layout:
  bit 0     : verbose flag
  bits 3-1  : mstp  (message type: 0=log, 1=app_trace, 2=nw_trace, 3=control)
  bits 7-4  : mtin  (type info; for log messages this is the log level)

Log levels (mtin when mstp==0):
  0=default, 1=off, 2=fatal, 3=error, 4=warn, 5=info, 6=debug, 7=verbose
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# htyp bit masks
# ---------------------------------------------------------------------------
HTYP_UEH  = 0x01   # use extended header
HTYP_MSBF = 0x02   # MSB first (big-endian payload arguments)
HTYP_WEID = 0x04   # with ECU ID
HTYP_WSID = 0x08   # with session ID
HTYP_WTMS = 0x10   # with timestamp

# msin masks
MSIN_VERB       = 0x01
MSIN_MSTP       = 0x0E
MSIN_MTIN       = 0xF0
MSIN_MSTP_SHIFT = 1
MSIN_MTIN_SHIFT = 4

# message types
DLT_TYPE_LOG       = 0x00
DLT_TYPE_APP_TRACE = 0x01
DLT_TYPE_NW_TRACE  = 0x02
DLT_TYPE_CONTROL   = 0x03

LOG_LEVELS = {
    0: "default",
    1: "off",
    2: "fatal",
    3: "error",
    4: "warn",
    5: "info",
    6: "debug",
    7: "verbose",
}
MSG_TYPES = {
    0: "log",
    1: "app_trace",
    2: "nw_trace",
    3: "control",
}

# ---------------------------------------------------------------------------
# Argument type_info masks (payload, verbose mode)
# ---------------------------------------------------------------------------
TYPE_INFO_TYLE = 0x0000000F
TYPE_INFO_BOOL = 0x00000010
TYPE_INFO_SINT = 0x00000020
TYPE_INFO_UINT = 0x00000040
TYPE_INFO_FLOA = 0x00000080
TYPE_INFO_STRG = 0x00000200
TYPE_INFO_RAWD = 0x00000400
TYPE_INFO_SCOD = 0x00038000
SCOD_UTF8      = 0x00008000

# tyle value -> byte count
TYLE_SIZES = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}

DLT_MAX_MSG_LEN = 65535
STD_HDR_MIN_LEN = 4


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class DltMessage:
    htyp: int
    mcnt: int
    length: int

    # optional standard header fields
    ecu_id:       str   = ""
    session_id:   int   = 0
    timestamp_raw: int  = 0       # units: 0.1 ms
    timestamp_sec: float = 0.0

    # extended header fields
    verbose:   bool = False
    msg_type:  str  = "log"
    log_level: str  = "default"
    apid:      str  = ""
    ctid:      str  = ""
    noar:      int  = 0

    # decoded payload
    payload_text: str   = ""
    payload_raw:  bytes = field(default_factory=bytes)

    # decode quality
    decode_error: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _decode_4cc(buf: bytes, offset: int) -> str:
    """Decode a 4-byte null-padded ASCII identifier."""
    return buf[offset: offset + 4].rstrip(b"\x00").decode("ascii", errors="replace")


def _parse_verbose_payload(payload: bytes, noar: int, big_endian: bool) -> str:
    """Extract a human-readable string from verbose DLT payload arguments."""
    endian = ">" if big_endian else "<"
    pos = 0
    parts: list[str] = []

    for _ in range(noar):
        if pos + 4 > len(payload):
            break
        type_info = struct.unpack_from("<I", payload, pos)[0]
        pos += 4

        if type_info & TYPE_INFO_BOOL:
            if pos + 1 > len(payload):
                break
            parts.append("true" if payload[pos] else "false")
            pos += 1

        elif type_info & TYPE_INFO_STRG:
            if pos + 2 > len(payload):
                break
            str_len = struct.unpack_from("<H", payload, pos)[0]
            pos += 2
            if pos + str_len > len(payload):
                break
            encoding = "utf-8" if (type_info & TYPE_INFO_SCOD) == SCOD_UTF8 else "latin-1"
            raw_str = payload[pos: pos + str_len]
            parts.append(raw_str.rstrip(b"\x00").decode(encoding, errors="replace"))
            pos += str_len

        elif type_info & TYPE_INFO_RAWD:
            if pos + 2 > len(payload):
                break
            raw_len = struct.unpack_from("<H", payload, pos)[0]
            pos += 2
            if pos + raw_len > len(payload):
                break
            parts.append(payload[pos: pos + raw_len].hex())
            pos += raw_len

        elif type_info & (TYPE_INFO_SINT | TYPE_INFO_UINT | TYPE_INFO_FLOA):
            tyle = type_info & TYPE_INFO_TYLE
            size = TYLE_SIZES.get(tyle)
            if size is None or pos + size > len(payload):
                break
            raw = payload[pos: pos + size]
            pos += size

            if type_info & TYPE_INFO_SINT:
                fmt = {1: "b", 2: "h", 4: "i", 8: "q"}.get(size)
                if fmt:
                    parts.append(str(struct.unpack_from(endian + fmt, raw)[0]))
            elif type_info & TYPE_INFO_UINT:
                fmt = {1: "B", 2: "H", 4: "I", 8: "Q"}.get(size)
                if fmt:
                    parts.append(str(struct.unpack_from(endian + fmt, raw)[0]))
            elif type_info & TYPE_INFO_FLOA:
                fmt = {4: "f", 8: "d"}.get(size)
                if fmt:
                    parts.append(f"{struct.unpack_from(endian + fmt, raw)[0]:g}")

        else:
            # Unknown type_info combination; cannot advance safely — stop.
            break

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _parse_one(buf: bytes, offset: int) -> tuple[DltMessage | None, int]:
    """Try to parse a single DLT message starting at *offset* within *buf*.

    Returns:
        (DltMessage, new_offset) on success.
        (None, offset)           when the buffer has an incomplete message.
        (None, -1)               on a detected frame error (caller skips 1 byte).
    """
    if offset + STD_HDR_MIN_LEN > len(buf):
        return None, offset

    htyp   = buf[offset]
    mcnt   = buf[offset + 1]
    length = struct.unpack_from(">H", buf, offset + 2)[0]

    if length < STD_HDR_MIN_LEN or length > DLT_MAX_MSG_LEN:
        return None, -1  # invalid length — trigger resync

    if offset + length > len(buf):
        return None, offset  # not yet fully received

    msg = DltMessage(htyp=htyp, mcnt=mcnt, length=length)
    pos = offset + STD_HDR_MIN_LEN

    # --- optional standard header fields ---
    if htyp & HTYP_WEID:
        if pos + 4 > offset + length:
            return None, -1
        msg.ecu_id = _decode_4cc(buf, pos)
        pos += 4

    if htyp & HTYP_WSID:
        if pos + 4 > offset + length:
            return None, -1
        msg.session_id = struct.unpack_from(">I", buf, pos)[0]
        pos += 4

    if htyp & HTYP_WTMS:
        if pos + 4 > offset + length:
            return None, -1
        msg.timestamp_raw = struct.unpack_from(">I", buf, pos)[0]
        msg.timestamp_sec = msg.timestamp_raw / 10000.0
        pos += 4

    # --- extended header ---
    if htyp & HTYP_UEH:
        if pos + 10 > offset + length:
            return None, -1
        msin      = buf[pos]
        msg.noar  = buf[pos + 1]
        msg.apid  = _decode_4cc(buf, pos + 2)
        msg.ctid  = _decode_4cc(buf, pos + 6)
        pos += 10

        msg.verbose  = bool(msin & MSIN_VERB)
        mstp         = (msin & MSIN_MSTP) >> MSIN_MSTP_SHIFT
        mtin         = (msin & MSIN_MTIN) >> MSIN_MTIN_SHIFT
        msg.msg_type = MSG_TYPES.get(mstp, "unknown")
        if mstp == DLT_TYPE_LOG:
            msg.log_level = LOG_LEVELS.get(mtin, "unknown")

    # --- payload ---
    payload = buf[pos: offset + length]
    msg.payload_raw = payload

    if msg.verbose and msg.noar > 0:
        big_endian = bool(htyp & HTYP_MSBF)
        try:
            msg.payload_text = _parse_verbose_payload(payload, msg.noar, big_endian)
        except Exception as exc:
            msg.decode_error = f"verbose parse error: {exc}"
            msg.payload_text = payload.hex()
    else:
        # Non-verbose: present as printable ASCII with hex fallback.
        if payload:
            msg.payload_text = payload.decode("latin-1", errors="replace").replace("\x00", " ").strip()
        else:
            msg.payload_text = ""

    return msg, offset + length


def parse_messages(buf: bytes) -> tuple[list[DltMessage], bytes]:
    """Parse as many complete DLT messages as possible from *buf*.

    Returns ``(messages, remaining)`` where *remaining* is the unconsumed
    suffix that must be prepended to the next incoming data chunk.
    """
    messages: list[DltMessage] = []
    offset = 0

    while offset < len(buf):
        msg, new_offset = _parse_one(buf, offset)
        if msg is not None:
            messages.append(msg)
            offset = new_offset
        elif new_offset == -1:
            # Frame error: skip one byte to attempt re-synchronisation.
            offset += 1
        else:
            # Incomplete message — need more data from the network.
            break

    return messages, buf[offset:]
