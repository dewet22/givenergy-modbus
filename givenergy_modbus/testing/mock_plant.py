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

To serve a mock from a capture, use the CLI (the canonical serve tool)::

    givenergy-cli mock-server --capture path/to/plant.log   # see --help for --bind/--port

In-process (tests, scripting), build one with :meth:`MockPlant.from_capture` — which also
re-tails multi-instance devices to distinct serials (#283/#288/#290)::

    mock = MockPlant.from_capture("path/to/plant.log")
    host, port = await mock.start()

Running this module as ``python -m givenergy_modbus.testing.mock_plant`` is **deprecated**: it
double-imports under the package ``__init__`` (a ``RuntimeWarning``). Prefer the CLI or
``from_capture`` above.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from givenergy_modbus.framer import ServerFramer
from givenergy_modbus.model.aio_battery import AioBatteryModuleRegisterGetter
from givenergy_modbus.model.battery import BatteryRegisterGetter
from givenergy_modbus.model.ems import EmsRegisterGetter
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

    Two line shapes are accepted: the canonical ``<ts> rx <hex>`` and the integration
    capture's ``rx: <hex>`` / ``tx: <hex>`` (no timestamp, colon-suffixed direction). Only
    rx lines are kept; the hex is a socket chunk, so frames may span lines, so we concatenate
    the rx stream in timestamp order and split on the frame marker using the MBAP length
    field — the same framing the wire uses. Timestamp-less lines sort stably in file order.
    """
    entries: list[tuple[str, bytes]] = []
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            # Direction token is either parts[0] ("rx:"/"tx:", no timestamp) or parts[1]
            # ("rx"/"tx", canonical with timestamp). Tolerate a trailing colon either way.
            if parts[0].rstrip(":").lower() in ("rx", "tx"):
                direction, ts = parts[0].rstrip(":").lower(), ""
            elif len(parts) >= 3 and parts[1].rstrip(":").lower() in ("rx", "tx"):
                direction, ts = parts[1].rstrip(":").lower(), parts[0]
            else:
                continue
            if direction != "rx":
                continue
            try:
                entries.append((ts, bytes.fromhex(parts[-1])))
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
        if frame_len < 18:
            # False-positive marker or corrupted length — skip one byte and keep searching.
            i += 1
            continue
        if i + frame_len > n:
            break  # genuine truncated tail; wait for more data (or end of file)
        frames.append(buf[i : i + frame_len])
        i += frame_len
    return frames


def plant_from_capture(*paths: str | Path) -> Plant:
    """Decode the rx frames of one or more capture files into a populated :class:`Plant`.

    Drives the real decode + ``Plant.update`` path, so the resulting
    ``plant.register_caches`` (keyed by device address) is exactly what the library would
    hold after polling the real plant.
    """
    frames = _iter_capture_frames(*paths)
    if not frames:
        # Zero frames means none of the lines matched the accepted shapes — almost always a
        # capture-format mismatch. Fail loudly rather than silently serving an empty plant
        # (which would report "0 devices seeded" and answer "absent" for every read). See #322.
        joined = ", ".join(str(p) for p in paths)
        raise ValueError(
            f"No rx frames parsed from capture(s): {joined}. Expected lines shaped '<ts> rx <hex>' or 'rx: <hex>'."
        )
    plant = Plant()
    for frame in frames:
        try:
            pdu = ClientIncomingMessage.decode_bytes(frame)
        except Exception:  # noqa: BLE001  # nosec B112 — skipping an undecodable frame is intended  # pragma: no cover
            continue  # pragma: no cover
        if isinstance(pdu, TransparentResponse) and not pdu.error:
            plant.update(pdu)
    return plant


def _decode_serial(cache: RegisterCache, regs: tuple[Register, ...] | list[Register]) -> str | None:
    """Decode a serial from its registers in a cache (mirrors the model serial converter)."""
    values = [cache.get(r) for r in regs]
    if any(v is None for v in values):
        return None
    raw = b"".join(v.to_bytes(2, "big") for v in values if v is not None)
    # Strip null AND whitespace padding (matching the model's serial handling, e.g. Ems
    # managed_inverters' strip("\x00 ")), so an empty-but-space-padded slot reads as no serial
    # rather than a whitespace string that would be mistaken for a real (colliding) value.
    return raw.decode("latin1").replace("\x00", "").strip().upper() or None


def _encode_serial(serial: str, n_regs: int) -> list[int]:
    """Encode a serial string into ``n_regs`` big-endian uint16 registers (inverse of decode)."""
    data = serial.encode("latin1")[: n_regs * 2].ljust(n_regs * 2, b"\x00")
    return [int.from_bytes(data[i * 2 : i * 2 + 2], "big") for i in range(n_regs)]


def _disambiguate_serials(members: list[tuple[RegisterCache, tuple[Register, ...], str]]) -> None:
    """Make a group of multi-instance members carry distinct serials in the mock cache.

    Each member is ``(cache, serial-registers, suffix)``, where ``suffix`` is a 2-char identity
    unique within the group (bus address or slot index). If two or more members share a non-empty
    serial, **every** populated member is re-tailed with its suffix — preserving the prefix and
    keeping it obviously synthetic. Rewriting *only* the colliding members could mint a value that
    matches an already-distinct member (#288 review); rewriting all, with each member's unique
    suffix, guarantees no two collide. A fully-distinct group is left untouched; empty / sub-2-char
    serials are skipped.
    """
    decoded = [(cache, regs, suffix, _decode_serial(cache, regs)) for cache, regs, suffix in members]
    serials = [s for *_, s in decoded if s]
    if len(set(serials)) == len(serials):
        return  # no collision in this group
    for cache, regs, suffix, serial in decoded:
        if serial and len(serial) >= 2:
            for reg, value in zip(regs, _encode_serial(serial[:-2] + suffix, len(regs))):
                cache[reg] = value


def _make_device_serials_distinct(plant: Plant) -> None:
    """Give each instance of a multi-instance device a distinct serial where the capture collides.

    Fixtures redact every serial to the same placeholder, so replayed packs/modules/slots share a
    serial and collide downstream. Where a group collides, each populated member is re-tailed with a
    unique 2-char suffix (bus address, or EMS slot index) — preserving the real prefix, obviously
    synthetic. A fully-distinct group is left untouched; only the in-memory mock caches change,
    never the fixture bytes.

    Handles the IR/``C.serial`` 5-register devices: LV battery packs and AIO modules (re-tailed by
    bus address), and EMS managed-inverter slots within the 0x11 cache (re-tailed by slot index,
    since they share an address). Meters (MR/``C.string``) and HV BMUs (stride within a single 0x70
    cache) use other layouts and are out of scope.
    """
    caches = plant.register_caches
    # Unified addressing (inverter at 0x11/0x31) puts LV battery pack #1 at 0x32; legacy bare-plant
    # addressing keeps the inverter facade at 0x32 (pack #1 at 0x33). Gate strictly on the canonical
    # inverter addresses present in the caches so a legacy capture never has its inverter serial
    # rewritten as if it were a battery pack (#283 review).
    lv_start = 0x32 if (0x11 in caches or 0x31 in caches) else 0x33
    for addr_range, getter in (
        (range(lv_start, 0x38), BatteryRegisterGetter),  # LV battery packs
        (range(0x50, 0x54), AioBatteryModuleRegisterGetter),  # AIO battery modules
    ):
        # registers_of returns () for getters without a serial_number; _disambiguate_serials then
        # decodes every member to None and no-ops, so we can iterate unconditionally (#247 contract).
        regs = getter.registers_of("serial_number")
        _disambiguate_serials([(caches[a], regs, f"{a:02x}") for a in addr_range if a in caches])

    # EMS managed-inverter slots (#288): up to 4 sub-slots in the single 0x11 EMS cache (not separate
    # device addresses), so address keying can't see them — re-tail by slot index instead. A non-EMS
    # 0x11 cache has no IR2066+ managed-inverter serials, so this is a no-op; the EMS controller's own
    # serial is never touched.
    ems_cache = caches.get(0x11)
    if ems_cache is not None:
        _disambiguate_serials(
            [
                (ems_cache, regs, f"{i:02d}")
                for i in range(1, 5)
                if (regs := EmsRegisterGetter.registers_of(f"inverter_{i}_serial_number"))
            ]
        )


def _verify_spec_commits(spec: dict[int, dict[tuple[type[Register], int], Sequence[int]]]) -> None:
    """Round-trip every HR/IR bank in *spec* through a scratch ``Plant.update()`` (#324).

    Feeds each bank twice — the second pass is the corroborating re-read that commits a
    cold-start-held battery bank (#289) — then asserts every specced register actually
    landed in the plant's caches. Raises ValueError naming the failures, so a synthetic
    bank the commit guards would silently reject (e.g. an internally-impossible battery
    frame, #350) fails fast at construction instead of serving state no client can ingest.
    """
    from givenergy_modbus.pdu.read_registers import (
        ReadHoldingRegistersResponse,
        ReadInputRegistersResponse,
    )

    pdu_for: dict[type[Register], type] = {HR: ReadHoldingRegistersResponse, IR: ReadInputRegistersResponse}
    unsupported = sorted(
        f"0x{dev:02x}:{reg_cls.__name__}({base})"
        for dev, banks in spec.items()
        for (reg_cls, base) in banks
        if reg_cls not in pdu_for
    )
    if unsupported:
        raise ValueError(
            f"verify=True can only round-trip HR/IR banks (they are what exists on the read wire); "
            f"got {', '.join(unsupported)}. Seed other register classes with verify=False."
        )

    plant = Plant()
    for _pass in range(2):  # second feed = the corroborating cold-start re-read (#289)
        for device_address, banks in spec.items():
            for (reg_cls, base), values in banks.items():
                pdu = pdu_for[reg_cls](
                    device_address=device_address,
                    base_register=base,
                    register_count=len(values),
                    register_values=list(values),
                    # Envelope serials a wire decode would carry; update() reads them.
                    inverter_serial_number=_FALLBACK_SERIAL,
                    data_adapter_serial_number=_FALLBACK_SERIAL,
                )
                plant.update(pdu)

    failures = [
        f"0x{device_address:02x}:{reg_cls.__name__}({base + i})"
        for device_address, banks in spec.items()
        for (reg_cls, base), values in banks.items()
        for i, value in enumerate(values)
        if plant.register_caches.get(device_address, RegisterCache()).get(reg_cls(base + i)) != value
    ]
    if failures:
        raise ValueError(
            f"{len(failures)} specced register(s) were rejected by the commit guards and never "
            f"landed in Plant state: {', '.join(failures[:12])}"
            + (" …" if len(failures) > 12 else "")
            + ". The served state would be invisible to a real client; fix the bank values "
            "(or pass verify=False to serve it anyway)."
        )


class MockPlant:
    """A TCP server impersonating a GivEnergy plant, seeded from a capture."""

    def __init__(
        self,
        devices: dict[int, RegisterCache],
        *,
        inverter_serial: str = _FALLBACK_SERIAL,
        adapter_serial: str = _FALLBACK_SERIAL,
        log_writes: bool = False,
    ) -> None:
        self.devices = devices
        self.inverter_serial = inverter_serial or _FALLBACK_SERIAL
        self.adapter_serial = adapter_serial or _FALLBACK_SERIAL
        # When True, inbound writes are logged at INFO (so app-driven write-address
        # discovery is visible without -v); tests leave it False to stay quiet.
        self.log_writes = log_writes
        self._server: asyncio.AbstractServer | None = None

    @classmethod
    def from_capture(cls, *paths: str | Path) -> MockPlant:
        """Build a mock plant seeded from one or more capture ``.log`` files."""
        plant = plant_from_capture(*paths)
        _make_device_serials_distinct(plant)
        return cls(
            plant.register_caches,
            inverter_serial=plant.inverter_serial_number,
            adapter_serial=plant.data_adapter_serial_number,
        )

    @classmethod
    def from_sentinels(
        cls,
        *paths: str | Path,
        spec: list[tuple[int, type[Register], range]],
        offset: int = 0,
    ) -> MockPlant:
        """Build a sentinel-overlaid mock for register cross-correlation.

        Loads a base plant from *paths* (same as :meth:`from_capture`), then
        overlays *spec* with sentinel values ``raw = address + offset``.  Run the
        app against the resulting mock and call :func:`.identify` on each displayed
        value to recover the backing register address.

        Parameters
        ----------
        *paths:
            One or more capture ``.log`` files to seed the base state.
        spec:
            Sentinel overlay: list of ``(device_address, HR|IR|MR, address_range)``
            triples.  Every address in ``address_range`` is written as
            ``register_class(addr) → addr + offset``.
        offset:
            Added to every sentinel value.  Use ``offset=0`` for pass 1,
            ``offset=K`` (e.g. 1000) for pass 2.
        """
        from givenergy_modbus.testing.identify import sentinel_devices

        plant = plant_from_capture(*paths)
        devices = sentinel_devices(plant.register_caches, spec, offset=offset)
        return cls(
            devices,
            inverter_serial=plant.inverter_serial_number,
            adapter_serial=plant.data_adapter_serial_number,
        )

    @classmethod
    def from_spec(
        cls,
        spec: dict[int, dict[tuple[type[Register], int], Sequence[int]]],
        *,
        verify: bool = True,
        inverter_serial: str = _FALLBACK_SERIAL,
        adapter_serial: str = _FALLBACK_SERIAL,
    ) -> MockPlant:
        """Build a mock from a pure register spec — no base capture required (#324).

        *spec* maps ``device_address → {(HR|IR|MR, base_register): values}``; each bank
        seeds ``register_class(base + i) → values[i]``. Together with :meth:`start` this
        turns arbitrary synthetic state into something the real GE app (or this
        library's client) can be driven against.

        With ``verify`` (the default), every HR/IR bank is round-tripped through a
        scratch ``Plant.update()`` first — proving the state would actually *commit*
        past the client-side guards (cold-start hold #289, splice cohort checks,
        impossible-frame refusal #350). A synthetic bank can serve fine over the wire
        yet be silently rejected on ingest, which otherwise surfaces as "the client
        sees nothing" mid-interrogation. Each bank is fed twice, mirroring detect()'s
        corroborating re-read, so cold-start-held battery banks commit exactly as they
        would live. Raises :class:`ValueError` naming every register that failed to
        commit. Only HR/IR banks exist on the read wire; spec any other register class
        with ``verify=False`` (direct cache seeding, no round-trip).

        Every value must fit an unsigned 16-bit register word (0..0xFFFF) regardless of
        ``verify`` — an out-of-range word can never be encoded onto the wire, and would
        otherwise crash ``struct.pack`` at serve time on the first client read.
        """
        devices: dict[int, RegisterCache] = {}
        for device_address, banks in spec.items():
            cache = devices.setdefault(device_address, RegisterCache())
            for (reg_cls, base), values in banks.items():
                for i, value in enumerate(values):
                    if not 0 <= value <= 0xFFFF:
                        raise ValueError(
                            f"0x{device_address:02x}:{reg_cls.__name__}({base + i}) = {value} does not "
                            f"fit an unsigned 16-bit register word (0..65535) and can never be served; "
                            f"encode signed/scaled quantities to their raw wire representation first."
                        )
                    cache[reg_cls(base + i)] = value
        if verify:
            _verify_spec_commits(spec)
        return cls(devices, inverter_serial=inverter_serial, adapter_serial=adapter_serial)

    # -- serving ---------------------------------------------------------------

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> tuple[str, int]:
        """Start listening; return the bound (host, port). Use port 0 for an ephemeral port."""
        self._server = await asyncio.start_server(self._handle, host, port)
        sock = self._server.sockets[0].getsockname()
        _logger.info("MockPlant listening on %s:%s — %d devices seeded", sock[0], sock[1], len(self.devices))
        return sock[0], sock[1]

    async def serve_forever(self) -> None:  # pragma: no cover
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

    async def __aenter__(self) -> MockPlant:
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
        except ConnectionError:  # pragma: no cover
            # Client dropped the socket — a normal disconnect (e.g. an app that opens a
            # fresh connection per operation and resets the previous one), not a mock error.
            _logger.debug("MockPlant client disconnected")  # pragma: no cover
        except Exception:  # noqa: BLE001 — a mock should keep serving other clients  # pragma: no cover
            _logger.exception("MockPlant handler error")  # pragma: no cover
        finally:
            writer.close()

    def _respond(self, pdu: object) -> bytes | None:
        if isinstance(pdu, WriteHoldingRegisterRequest):
            _logger.log(  # pragma: no branch
                logging.INFO if self.log_writes else logging.DEBUG,
                "→ WriteHoldingRegisterRequest device=0x%02x reg=%d val=%d",
                pdu.device_address,
                pdu.register,
                pdu.value,
            )
            return self._ack_write(pdu)
        if isinstance(pdu, (ReadHoldingRegistersRequest, ReadInputRegistersRequest, ReadMeterProductRegistersRequest)):
            _logger.debug(
                "→ %s device=0x%02x base=%d count=%d",
                type(pdu).__name__,
                pdu.device_address,
                pdu.base_register,
                pdu.register_count,
            )
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
            _logger.debug("← no reply (absent device 0x%02x)", req.device_address)
            return None
        base, count = req.base_register, req.register_count
        # Present device but absent/partial bank → error response (the 0x12-padding shape
        # real hardware uses, e.g. an AIO on IR(1000+)). Membership test avoids the
        # RegisterCache defaultdict silently materialising 0s for missing registers.
        if reg_type is None or any(reg_type(base + i) not in cache for i in range(count)):
            _logger.debug(
                "← error response (absent bank) device=0x%02x base=%d count=%d",
                req.device_address,
                base,
                count,
            )
            return self._error(req)
        resp = cast(ReadRegistersResponse, req.expected_response())
        resp.register_values = [cache[reg_type(base + i)] for i in range(count)]
        self._stamp(resp)
        _logger.debug("← %s device=0x%02x base=%d count=%d", type(resp).__name__, req.device_address, base, count)
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
        _logger.debug(
            "← WriteHoldingRegisterResponse (ack, no state mutation) device=0x%02x reg=%d",
            req.device_address,
            req.register,
        )
        return resp.encode()

    def _stamp(self, resp: TransparentResponse) -> None:
        """Set the envelope serials + success padding on a synthesized response."""
        resp.inverter_serial_number = self.inverter_serial
        resp.data_adapter_serial_number = self.adapter_serial
        if not resp.error:
            resp.padding = 0x8A


def main(argv: list[str] | None = None) -> int:
    """CLI: serve a mock plant seeded from one or more capture files.

    Drive the official app (or this library) against it and watch which device address
    inbound writes target — they are logged at INFO. The serial/firmware overrides let you
    impersonate a specific unit so the app accepts the device.
    """
    parser = argparse.ArgumentParser(description="Serve a mock GivEnergy plant from a wire capture.")
    parser.add_argument("--capture", required=True, nargs="+", help="capture .log file(s) to seed from")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind host (default: 127.0.0.1; pass 0.0.0.0 to expose on the LAN for an external client)",
    )
    parser.add_argument("--port", type=int, default=8899, help="bind port (default: 8899)")
    parser.add_argument("--serial", default=None, help="inverter serial to advertise (default: from capture)")
    parser.add_argument("--arm-fw", type=int, default=None, help="override ARM firmware HR(21) in every seeded device")
    parser.add_argument("--dsp-fw", type=int, default=None, help="override DSP firmware HR(19) in every seeded device")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging (incl. reads)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    plant = plant_from_capture(*args.capture)
    # Match MockPlant.from_capture(): give replayed multi-instance devices distinct serials so the
    # served mock doesn't collide e.g. EMS managed-inverter serials (#283/#288/#290). Building the
    # MockPlant by hand below would otherwise skip this and serve colliding serials.
    _make_device_serials_distinct(plant)
    for reg, val in ((21, args.arm_fw), (19, args.dsp_fw)):  # HR(21)=ARM, HR(19)=DSP firmware version
        if val is not None:
            for cache in plant.register_caches.values():
                if HR(reg) in cache:
                    cache[HR(reg)] = val
    mock = MockPlant(
        plant.register_caches,
        inverter_serial=args.serial or plant.inverter_serial_number,
        adapter_serial=plant.data_adapter_serial_number,
        log_writes=True,
    )

    async def _run() -> None:
        host, port = await mock.start(args.host, args.port)
        _logger.info("serving %d devices on %s:%s — inbound writes logged at INFO", len(mock.devices), host, port)
        await mock.serve_forever()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    # `python -m …mock_plant` double-imports under the package __init__ (RuntimeWarning) and is
    # deprecated; the CLI is the serve tool. Warn once (lastResort handler shows it before main()
    # configures logging), then run anyway so existing scripts don't break.
    _logger.warning(
        "`python -m givenergy_modbus.testing.mock_plant` is deprecated (it double-imports under the "
        "package __init__). Use `givenergy-cli mock-server` to serve a mock, or MockPlant.from_capture() "
        "in-process."
    )
    raise SystemExit(main())
