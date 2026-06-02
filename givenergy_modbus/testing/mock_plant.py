"""A faithful in-memory mock GivEnergy plant for testing without hardware.

``MockPlant`` seeds per-device register state from a recorded wire capture and serves
*synthesized*, correct-CRC responses to register-read requests. Unlike a byte-replay
mock it answers an arbitrary read by slicing the seeded register cache, so a real
client's own request sequence (detect → load_config → refresh) round-trips against it.

Fidelity choices (Phase 1 — read-serving, static topology):
- A read whose full ``[base, base+count)`` range isn't present for the target device
  returns an **error response** (the high-bit/0x12-padding shape real hardware uses for an
  absent bank) — so e.g. an All-in-One seed naturally errors on the IR(1000+) bank it lacks.
- Writes are acknowledged with a valid response but do **not** mutate state.
- Heartbeats aren't initiated (the library client drives request/response and doesn't
  require them); an inbound heartbeat response is ignored.

Mutable writes and dynamic bus/device add-remove are a later phase.

Run it directly to point another client at a capture::

    python -m givenergy_modbus.testing.mock_plant --capture path/to/plant.log --port 8899
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import cast

from givenergy_modbus.framer import ServerFramer
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register import HR, IR, MR, Register
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import (
    ClientIncomingMessage,
    ReadHoldingRegistersRequest,
    ReadInputRegistersRequest,
    ReadMeterProductRegistersRequest,
    TransparentRequest,
    TransparentResponse,
    WriteHoldingRegisterRequest,
)
from givenergy_modbus.pdu.read_registers import ReadRegistersResponse

_logger = logging.getLogger(__name__)

_FRAME_MARKER = bytes.fromhex("59590001")
# transparent_function_code → register namespace for the three read functions.
_READ_REGISTER_TYPE: dict[int, type[Register]] = {3: HR, 4: IR, 0x16: MR}

# Fallback redacted serials if the seed capture didn't carry one (shouldn't happen).
_FALLBACK_SERIAL = "MK0000G000"


def _iter_capture_frames(*paths: str | Path) -> list[bytes]:
    """Return complete rx frames from one or more capture ``.log`` files, ts-sorted.

    Each line is ``<ts> rx <hex>``; the hex is a socket chunk, so frames may span lines.
    We concatenate the rx stream in timestamp order and split on the frame marker using
    the MBAP length field — the same framing the wire uses.
    """
    entries: list[tuple[str, bytes]] = []
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "rx":
                try:
                    entries.append((parts[0], bytes.fromhex(parts[-1])))
                except ValueError:
                    continue
    entries.sort(key=lambda e: e[0])
    buf = b"".join(raw for _, raw in entries)

    frames: list[bytes] = []
    i, n = 0, len(buf)
    while i + 8 <= n:
        if buf[i : i + 4] != _FRAME_MARKER:
            i += 1
            continue
        frame_len = 6 + int.from_bytes(buf[i + 4 : i + 6], "big")
        if frame_len < 18 or i + frame_len > n:
            break  # truncated tail
        frames.append(buf[i : i + frame_len])
        i += frame_len
    return frames


def plant_from_capture(*paths: str | Path) -> Plant:
    """Decode the rx frames of one or more capture files into a populated :class:`Plant`.

    Drives the real decode + ``Plant.update`` path, so the resulting
    ``plant.register_caches`` (keyed by device address) is exactly what the library would
    hold after polling the real plant.
    """
    plant = Plant()
    for frame in _iter_capture_frames(*paths):
        try:
            pdu = ClientIncomingMessage.decode_bytes(frame)
        except Exception:  # noqa: BLE001  # nosec B112 — skipping an undecodable frame is intended
            continue
        if isinstance(pdu, TransparentResponse) and not pdu.error:
            plant.update(pdu)
    return plant


class MockPlant:
    """A TCP server impersonating a GivEnergy plant, seeded from a capture."""

    def __init__(
        self,
        devices: dict[int, RegisterCache],
        *,
        inverter_serial: str = _FALLBACK_SERIAL,
        adapter_serial: str = _FALLBACK_SERIAL,
    ) -> None:
        self.devices = devices
        self.inverter_serial = inverter_serial or _FALLBACK_SERIAL
        self.adapter_serial = adapter_serial or _FALLBACK_SERIAL
        self._server: asyncio.AbstractServer | None = None

    @classmethod
    def from_capture(cls, *paths: str | Path) -> "MockPlant":
        """Build a mock plant seeded from one or more capture ``.log`` files."""
        plant = plant_from_capture(*paths)
        return cls(
            plant.register_caches,
            inverter_serial=plant.inverter_serial_number,
            adapter_serial=plant.data_adapter_serial_number,
        )

    # -- serving ---------------------------------------------------------------

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> tuple[str, int]:
        """Start listening; return the bound (host, port). Use port 0 for an ephemeral port."""
        self._server = await asyncio.start_server(self._handle, host, port)
        sock = self._server.sockets[0].getsockname()
        _logger.info("MockPlant listening on %s:%s — %d devices seeded", sock[0], sock[1], len(self.devices))
        return sock[0], sock[1]

    async def serve_forever(self) -> None:
        """Serve until cancelled (after :meth:`start`)."""
        assert self._server is not None, "call start() first"
        async with self._server:
            await self._server.serve_forever()

    async def aclose(self) -> None:
        """Stop the server."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def __aenter__(self) -> "MockPlant":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        framer = ServerFramer()
        try:
            while not reader.at_eof():
                data = await reader.read(4096)
                if not data:
                    break
                async for pdu in framer.decode(data):
                    reply = self._respond(pdu)
                    if reply is not None:
                        writer.write(reply)
                        await writer.drain()
        except asyncio.CancelledError, ConnectionError:
            raise
        except Exception:  # noqa: BLE001 — a mock should keep serving other clients
            _logger.exception("MockPlant handler error")
        finally:
            writer.close()

    def _respond(self, pdu: object) -> bytes | None:
        if isinstance(pdu, WriteHoldingRegisterRequest):
            return self._ack_write(pdu)
        if isinstance(pdu, (ReadHoldingRegistersRequest, ReadInputRegistersRequest, ReadMeterProductRegistersRequest)):
            return self._read(pdu)
        # Heartbeat responses (client → server) and anything else need no reply.
        return None

    def _read(
        self, req: ReadHoldingRegistersRequest | ReadInputRegistersRequest | ReadMeterProductRegistersRequest
    ) -> bytes | None:
        reg_type = _READ_REGISTER_TYPE.get(req.transparent_function_code)
        cache = self.devices.get(req.device_address)
        if cache is None:
            # Absent device address: real hardware doesn't answer at all → no reply (the
            # client times out). This is what detect()'s peripheral probe sweep expects.
            return None
        base, count = req.base_register, req.register_count
        # Present device but absent/partial bank → error response (the 0x12-padding shape
        # real hardware uses, e.g. an AIO on IR(1000+)). Membership test avoids the
        # RegisterCache defaultdict silently materialising 0s for missing registers.
        if reg_type is None or any(reg_type(base + i) not in cache for i in range(count)):
            return self._error(req)
        resp = cast(ReadRegistersResponse, req.expected_response())
        resp.register_values = [cache[reg_type(base + i)] for i in range(count)]
        self._stamp(resp)
        return resp.encode()

    def _error(self, req: TransparentRequest) -> bytes:
        resp = cast(ReadRegistersResponse, req.expected_response())
        resp.error = True
        resp.padding = 0x12
        resp.register_values = []
        self._stamp(resp)
        return resp.encode()

    def _ack_write(self, req: WriteHoldingRegisterRequest) -> bytes:
        # Phase 1: acknowledge with a valid readback response; state is not mutated.
        resp = cast(TransparentResponse, req.expected_response())
        self._stamp(resp)
        return resp.encode()

    def _stamp(self, resp: TransparentResponse) -> None:
        """Set the envelope serials + success padding on a synthesized response."""
        resp.inverter_serial_number = self.inverter_serial
        resp.data_adapter_serial_number = self.adapter_serial
        if not resp.error:
            resp.padding = 0x8A


def main(argv: list[str] | None = None) -> int:
    """CLI: serve a mock plant seeded from one or more capture files."""
    parser = argparse.ArgumentParser(description="Serve a mock GivEnergy plant from a wire capture.")
    parser.add_argument("--capture", required=True, nargs="+", help="capture .log file(s) to seed from")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind host (default: 127.0.0.1; pass 0.0.0.0 to expose on the LAN for an external client)",
    )
    parser.add_argument("--port", type=int, default=8899, help="bind port (default: 8899)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    async def _run() -> None:
        mock = MockPlant.from_capture(*args.capture)
        await mock.start(args.host, args.port)
        await mock.serve_forever()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
