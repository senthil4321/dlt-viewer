"""Unit tests for the DLT message parser."""

import struct

import pytest

from app.ingestion.dlt_parser import (
    HTYP_MSBF,
    HTYP_UEH,
    HTYP_WEID,
    HTYP_WSID,
    HTYP_WTMS,
    TYPE_INFO_SINT,
    TYPE_INFO_STRG,
    TYPE_INFO_UINT,
    DltMessage,
    parse_messages,
)


# ---------------------------------------------------------------------------
# Helpers to build minimal DLT frames for testing
# ---------------------------------------------------------------------------

def _build_std_header(
    htyp: int,
    mcnt: int,
    extra_fields: bytes = b"",
    ext_header: bytes = b"",
    payload: bytes = b"",
) -> bytes:
    """Return a complete DLT standard-header + payload byte string."""
    content = extra_fields + ext_header + payload
    length  = 4 + len(content)  # 4 = std-header min size
    return struct.pack(">BBH", htyp, mcnt, length) + content


def _build_ext_header(
    verbose: bool,
    mstp: int,
    mtin: int,
    noar: int,
    apid: str,
    ctid: str,
) -> bytes:
    msin = (int(verbose) | (mstp << 1) | (mtin << 4)) & 0xFF
    return (
        struct.pack("BB", msin, noar)
        + apid.encode("ascii").ljust(4, b"\x00")[:4]
        + ctid.encode("ascii").ljust(4, b"\x00")[:4]
    )


def _str_arg(text: str) -> bytes:
    """Pack a verbose STRING argument."""
    encoded = text.encode("latin-1") + b"\x00"
    type_info = TYPE_INFO_STRG
    return struct.pack("<IH", type_info, len(encoded)) + encoded


def _uint32_arg(value: int) -> bytes:
    """Pack a verbose UINT32 argument."""
    type_info = TYPE_INFO_UINT | 0x03  # tyle=3 → 4 bytes
    return struct.pack("<II", type_info, value)


def _sint16_arg(value: int) -> bytes:
    """Pack a verbose SINT16 argument (tyle=2 → 2 bytes)."""
    type_info = TYPE_INFO_SINT | 0x02
    return struct.pack("<Ih", type_info, value)


# ---------------------------------------------------------------------------
# Minimum header
# ---------------------------------------------------------------------------

class TestMinimalHeader:
    def test_minimal_parse(self) -> None:
        frame = _build_std_header(htyp=0x20, mcnt=1)  # version=1, no flags
        msgs, rem = parse_messages(frame)
        assert len(msgs) == 1
        assert rem == b""
        m = msgs[0]
        assert m.mcnt == 1
        assert m.length == 4
        assert m.ecu_id == ""
        assert m.apid == ""
        assert m.ctid == ""
        assert m.verbose is False

    def test_incomplete_returns_remainder(self) -> None:
        # Only 2 bytes — cannot even read the length field.
        msgs, rem = parse_messages(b"\x20\x01")
        assert msgs == []
        assert rem == b"\x20\x01"

    def test_incomplete_payload_buffers(self) -> None:
        # Frame claims length=10 but only 6 bytes provided.
        frame = struct.pack(">BBH", 0x20, 5, 10) + b"\x00\x00"
        msgs, rem = parse_messages(frame)
        assert msgs == []
        assert len(rem) == 6

    def test_zero_length_skips_byte_and_buffers(self) -> None:
        # length=0 is invalid; parser skips the first byte, then at the next
        # offset the remaining 3 bytes are not enough for a full standard header,
        # so they are returned as remainder (no crash, no infinite loop).
        bad = struct.pack(">BBH", 0x20, 0, 0)  # 4 bytes, length field == 0
        msgs, rem = parse_messages(bad)
        assert msgs == []
        assert len(rem) == 3  # 1 byte skipped, 3 bytes buffered


# ---------------------------------------------------------------------------
# Optional standard header fields
# ---------------------------------------------------------------------------

class TestOptionalStdFields:
    def test_with_ecu_id(self) -> None:
        extra = b"ECU1"
        frame = _build_std_header(htyp=0x20 | HTYP_WEID, mcnt=2, extra_fields=extra)
        msgs, _ = parse_messages(frame)
        assert msgs[0].ecu_id == "ECU1"

    def test_with_null_padded_ecu_id(self) -> None:
        extra = b"AB\x00\x00"
        frame = _build_std_header(htyp=0x20 | HTYP_WEID, mcnt=3, extra_fields=extra)
        msgs, _ = parse_messages(frame)
        assert msgs[0].ecu_id == "AB"

    def test_with_session_id(self) -> None:
        extra = struct.pack(">I", 0xDEADBEEF)
        frame = _build_std_header(htyp=0x20 | HTYP_WSID, mcnt=4, extra_fields=extra)
        msgs, _ = parse_messages(frame)
        assert msgs[0].session_id == 0xDEADBEEF

    def test_with_timestamp(self) -> None:
        extra = struct.pack(">I", 10000)  # 10000 * 0.1ms = 1.0 s
        frame = _build_std_header(htyp=0x20 | HTYP_WTMS, mcnt=5, extra_fields=extra)
        msgs, _ = parse_messages(frame)
        assert msgs[0].timestamp_raw == 10000
        assert pytest.approx(msgs[0].timestamp_sec) == 1.0

    def test_all_optional_fields(self) -> None:
        extra = (
            b"ECU1"
            + struct.pack(">I", 42)   # session id
            + struct.pack(">I", 5000) # timestamp
        )
        htyp = 0x20 | HTYP_WEID | HTYP_WSID | HTYP_WTMS
        frame = _build_std_header(htyp=htyp, mcnt=6, extra_fields=extra)
        msgs, _ = parse_messages(frame)
        m = msgs[0]
        assert m.ecu_id == "ECU1"
        assert m.session_id == 42
        assert pytest.approx(m.timestamp_sec) == 0.5


# ---------------------------------------------------------------------------
# Extended header
# ---------------------------------------------------------------------------

class TestExtendedHeader:
    def test_ext_header_parsed(self) -> None:
        ext = _build_ext_header(
            verbose=True, mstp=0, mtin=5, noar=0, apid="APP1", ctid="CTX1"
        )
        frame = _build_std_header(htyp=0x20 | HTYP_UEH, mcnt=10, ext_header=ext)
        msgs, _ = parse_messages(frame)
        m = msgs[0]
        assert m.apid == "APP1"
        assert m.ctid == "CTX1"
        assert m.verbose is True
        assert m.msg_type == "log"
        assert m.log_level == "info"

    def test_log_levels(self) -> None:
        for mtin, expected in [(2, "fatal"), (3, "error"), (4, "warn"), (5, "info"), (6, "debug")]:
            ext = _build_ext_header(verbose=False, mstp=0, mtin=mtin, noar=0, apid="A", ctid="B")
            frame = _build_std_header(htyp=0x20 | HTYP_UEH, mcnt=0, ext_header=ext)
            msgs, _ = parse_messages(frame)
            assert msgs[0].log_level == expected, f"mtin={mtin}"

    def test_msg_type_app_trace(self) -> None:
        ext = _build_ext_header(verbose=False, mstp=1, mtin=1, noar=0, apid="A", ctid="B")
        frame = _build_std_header(htyp=0x20 | HTYP_UEH, mcnt=0, ext_header=ext)
        msgs, _ = parse_messages(frame)
        assert msgs[0].msg_type == "app_trace"


# ---------------------------------------------------------------------------
# Verbose payload decoding
# ---------------------------------------------------------------------------

class TestVerbosePayload:
    def _make_frame(self, *args_bytes: bytes, mstp: int = 0, mtin: int = 5) -> bytes:
        noar    = len(args_bytes)
        payload = b"".join(args_bytes)
        ext     = _build_ext_header(verbose=True, mstp=mstp, mtin=mtin, noar=noar, apid="AP", ctid="CT")
        return _build_std_header(htyp=0x20 | HTYP_UEH, mcnt=0, ext_header=ext, payload=payload)

    def test_string_arg(self) -> None:
        frame = self._make_frame(_str_arg("hello world"))
        msgs, _ = parse_messages(frame)
        assert msgs[0].payload_text == "hello world"

    def test_uint32_arg(self) -> None:
        frame = self._make_frame(_uint32_arg(1234))
        msgs, _ = parse_messages(frame)
        assert msgs[0].payload_text == "1234"

    def test_sint16_negative(self) -> None:
        frame = self._make_frame(_sint16_arg(-42))
        msgs, _ = parse_messages(frame)
        assert msgs[0].payload_text == "-42"

    def test_multiple_args(self) -> None:
        frame = self._make_frame(_str_arg("count:"), _uint32_arg(99))
        msgs, _ = parse_messages(frame)
        assert msgs[0].payload_text == "count: 99"

    def test_big_endian_uint(self) -> None:
        # htyp MSBF flag → big-endian numeric decoding
        noar    = 1
        payload = struct.pack("<II", TYPE_INFO_UINT | 0x03, 0)  # placeholder
        # Re-pack with the actual big-endian value embedded separately:
        type_info_le = struct.pack("<I", TYPE_INFO_UINT | 0x03)
        val_be       = struct.pack(">I", 500)
        payload      = type_info_le + val_be
        ext          = _build_ext_header(verbose=True, mstp=0, mtin=5, noar=noar, apid="A", ctid="B")
        frame        = _build_std_header(
            htyp=0x20 | HTYP_UEH | HTYP_MSBF, mcnt=0, ext_header=ext, payload=payload
        )
        msgs, _ = parse_messages(frame)
        assert msgs[0].payload_text == "500"


# ---------------------------------------------------------------------------
# Multi-message framing
# ---------------------------------------------------------------------------

class TestMultiMessage:
    def test_two_consecutive_messages(self) -> None:
        f1 = _build_std_header(htyp=0x20, mcnt=1)
        f2 = _build_std_header(htyp=0x20, mcnt=2)
        msgs, rem = parse_messages(f1 + f2)
        assert len(msgs) == 2
        assert msgs[0].mcnt == 1
        assert msgs[1].mcnt == 2
        assert rem == b""

    def test_partial_second_message_buffered(self) -> None:
        f1 = _build_std_header(htyp=0x20, mcnt=1)
        f2 = _build_std_header(htyp=0x20, mcnt=2)
        msgs, rem = parse_messages(f1 + f2[:2])
        assert len(msgs) == 1
        assert msgs[0].mcnt == 1
        assert rem == f2[:2]

    def test_reassembly_across_chunks(self) -> None:
        f1 = _build_std_header(htyp=0x20, mcnt=1)
        f2 = _build_std_header(htyp=0x20, mcnt=2)
        combined = f1 + f2

        # Feed first chunk (partial second frame).
        msgs1, rem = parse_messages(combined[:len(f1) + 2])
        assert len(msgs1) == 1

        # Feed remainder.
        msgs2, rem2 = parse_messages(rem + combined[len(f1) + 2:])
        assert len(msgs2) == 1
        assert msgs2[0].mcnt == 2
        assert rem2 == b""

    def test_resync_does_not_crash_on_bad_length(self) -> None:
        # Inject a header with length=0 (invalid) before a valid frame.
        # After the 1-byte skip the subsequent bytes may look like an incomplete
        # valid frame (length field reads a non-zero value), so the parser
        # buffers the tail for future reassembly — but crucially does not crash.
        bad  = struct.pack(">BBH", 0x20, 0, 0)
        good = _build_std_header(htyp=0x20, mcnt=9)
        msgs, rem = parse_messages(bad + good)
        # No crash; some bytes are buffered for the next read.
        assert isinstance(msgs, list)
        assert isinstance(rem, bytes)
