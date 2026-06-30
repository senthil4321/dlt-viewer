"""Async UDP listener for DLT datagrams.

Supports:
  - Unicast: bind to host:port and receive datagrams.
  - Multicast: join a multicast group and receive from any sender.

Each UDP datagram is treated as a self-contained byte stream and fed through
the DLT parser (one datagram may contain one or more DLT messages).

Callbacks:
  on_message(session_id, DltMessage)           — called for every parsed msg
  on_state(session_id, state, error_detail)    — state ∈ {connected, error}
"""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
from typing import Awaitable, Callable

from .dlt_parser import DltMessage, parse_messages

log = logging.getLogger(__name__)

OnMessageCallback = Callable[[str, DltMessage], Awaitable[None]]
OnStateCallback   = Callable[[str, str, "str | None"], Awaitable[None]]


class _DltUdpProtocol(asyncio.DatagramProtocol):
    """asyncio DatagramProtocol that feeds received datagrams to the parser."""

    def __init__(
        self,
        session_id: str,
        loop: asyncio.AbstractEventLoop,
        on_message: OnMessageCallback,
    ) -> None:
        self._session_id = session_id
        self._loop       = loop
        self._on_message = on_message

    def datagram_received(self, data: bytes, addr: tuple) -> None:  # type: ignore[override]
        msgs, _ = parse_messages(data)
        for msg in msgs:
            self._loop.create_task(self._on_message(self._session_id, msg))

    def error_received(self, exc: Exception) -> None:
        log.warning("UDP [%s] protocol error: %s", self._session_id, exc)

    def connection_lost(self, exc: Exception | None) -> None:
        log.info("UDP [%s] transport closed: %s", self._session_id, exc)


class UdpIngestionListener:
    """Async UDP listener bound to host:port with optional multicast support."""

    def __init__(
        self,
        session_id: str,
        host: str,
        port: int,
        on_message: OnMessageCallback,
        on_state: OnStateCallback,
        multicast_group: str | None = None,
        interface_ip: str | None    = None,
    ) -> None:
        self.session_id     = session_id
        self.host           = host
        self.port           = port
        self._on_message    = on_message
        self._on_state      = on_state
        self.multicast_group = multicast_group
        self.interface_ip    = interface_ip
        self._transport: asyncio.DatagramTransport | None = None
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run(), name=f"udp-ingest-{self.session_id}"
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._transport is not None:
            self._transport.close()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            if self.multicast_group:
                # For multicast, bind to INADDR_ANY so the kernel delivers
                # packets from all interfaces; the group join determines the source.
                sock.bind(("", self.port))
                group = socket.inet_aton(self.multicast_group)
                iface = socket.inet_aton(self.interface_ip or "0.0.0.0")
                mreq  = struct.pack("4s4s", group, iface)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                log.info(
                    "UDP [%s] joined multicast %s on port %d",
                    self.session_id, self.multicast_group, self.port,
                )
            else:
                sock.bind((self.host, self.port))
                log.info(
                    "UDP [%s] listening on %s:%d", self.session_id, self.host, self.port
                )

            self._transport, _ = await loop.create_datagram_endpoint(
                lambda: _DltUdpProtocol(self.session_id, loop, self._on_message),
                sock=sock,
            )
            await self._on_state(self.session_id, "connected", None)

            # Hold here until stop() is called.
            await self._stop_event.wait()

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("UDP [%s] setup error: %s", self.session_id, exc)
            await self._on_state(self.session_id, "error", str(exc))
        finally:
            if self._transport is not None:
                self._transport.close()
                self._transport = None
