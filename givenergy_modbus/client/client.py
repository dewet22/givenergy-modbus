import asyncio
import logging
import random
import re
import socket
import warnings
from asyncio import Future, Queue, StreamReader, StreamWriter, Task
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from givenergy_modbus.client.commands import (
    _AC_CONFIG_WRITE_SAFE_REGISTERS,
    _EmsCommands,
    _InverterCommands,
    _ThreePhaseCommands,
)
from givenergy_modbus.exceptions import (
    CommunicationError,
    ConnectionLost,
    ExceptionBase,
    InvalidPduState,
    PlantNotDetected,
    PlantTopologyMismatch,
    ReadFailure,
    RefreshFailed,
    RefreshPartiallySucceeded,
)
from givenergy_modbus.framer import ClientFramer, Framer
from givenergy_modbus.model.ems import EmsRegisterGetter
from givenergy_modbus.model.inverter import Model, resolve_model
from givenergy_modbus.model.lv_bcu import LV_BCU_ADDRESS
from givenergy_modbus.model.plant import (
    _COLD_LV_BATTERY_RANGE,
    _COLD_METER_RANGE,
    Plant,
    PlantCapabilities,
    _aio_module_candidates,
    _derive_capabilities,
    _hv_bmu_candidates,
)
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import (
    HeartbeatRequest,
    ReadHoldingRegistersRequest,
    ReadInputRegistersRequest,
    TransparentRequest,
    TransparentResponse,
    WriteHoldingRegisterResponse,
)
from givenergy_modbus.pdu.write_registers import INSTALLER_WRITE_REGISTERS, WriteHoldingRegisterRequest

_logger = logging.getLogger(__name__)

# Standard GE 10-char serial in the textual / decoded form — `[A-Z]{2}\d{4}[A-Z]\d{3}`,
# matches both real serials (e.g. ``CE2231G454``) and the CLI-redacted form
# (``CE0000G000``). Used to sanity-check serial strings decoded out of the EMS rollup.
_GE_SERIAL_STR_PATTERN = re.compile(r"^[A-Z]{2}\d{4}[A-Z]\d{3}$")

Direction = Literal["rx", "tx"]


# ---------------------------------------------------------------------------
# Serial-register lookup — which register addresses carry C.serial values
# ---------------------------------------------------------------------------
#
# Built once at import time by walking every registered RegisterGetter LUT and
# collecting all Defs whose pre_conv is Converter.serial.  The result maps
# (register_type_name, address) → field_name. Register addresses are globally
# unique per type across all models (HR_13 is always the inverter serial, etc.),
# so no device-address filter is needed.
#
# Populated set (verified at B-3 implementation time):
#   HR: 8-12 (battery serial), 13-17 (inverter serial)
#   IR: 110-114 (battery), 1627-1631 (gateway first_inverter),
#       1831-1835/1838-1842/1845-1849 (gateway v1 AIO 1-3),
#       1841-1845/1848-1852/1855-1859 (gateway v2 AIO 1-3),
#       2066-2085 (EMS rollup ×4)
def _build_serial_register_groups() -> "list[tuple[str, int, int]]":
    """Build a list of (reg_type, base_address, count) for every C.serial register group.

    A serial field spans `count` consecutive registers starting at `base_address`.
    Addresses are globally unique per type across all models (HR_13 is always the
    inverter serial, etc.), so no device-address filter is needed.
    """
    from givenergy_modbus.model import battery, ems, gateway, inverter
    from givenergy_modbus.model.register import Converter

    seen: set[tuple[str, int, int]] = set()
    groups: list[tuple[str, int, int]] = []
    for module in (inverter, battery, ems, gateway):
        for attr in dir(module):
            cls = getattr(module, attr)
            if not isinstance(cls, type):
                continue
            lut = getattr(cls, "REGISTER_LUT", None)
            if not lut:
                continue
            for _field, defn in lut.items():
                pre_conv = defn.pre_conv[0] if isinstance(defn.pre_conv, tuple) else defn.pre_conv
                if pre_conv is Converter.serial and defn.registers:
                    reg_type = type(defn.registers[0]).__name__  # "HR" or "IR"
                    base = defn.registers[0]._idx
                    count = len(defn.registers)
                    key = (reg_type, base, count)
                    if key not in seen:
                        seen.add(key)
                        groups.append(key)
    # Legacy first_battery_serial_number registers (HR 8-12) — removed from the LUT
    # (#191: GivTCP-heritage, unused, unverifiable), but still redacted: AIO firmware
    # stores the unit serial here byte-swapped (CH… → HC…), recoverable to the real
    # serial, so it must not leak in shared captures. Appended unconditionally — no LUT
    # Def carries it any more, and a duplicate (if a future field reused HR 8) would
    # only redact it twice, which is idempotent.
    groups.append(("HR", 8, 5))
    return groups


# List of (reg_type, base_address, count) for all C.serial register groups.
_SERIAL_GROUPS: "list[tuple[str, int, int]]" = _build_serial_register_groups()

# MBAP start marker used by the framer to locate frames within a byte stream.
_FRAME_MARKER = bytes.fromhex("59590001")

# Floor for the "producer hasn't sent our frame yet" safety-net timeout. The actual wait
# also scales with the queue backlog (see send_request_and_await_response); this floor keeps
# it sane when the queue is idle. Module-level so tests can shrink it.
_FRAME_SENT_MIN_TIMEOUT = 5.0

# Upper bound on writer.drain() inside the producer loop (#356). On a healthy link
# drain completes near-instantly (it's local socket-buffer backpressure); a stall
# means the peer stopped ACKing — a half-open connection — so it's treated as
# connection loss rather than left to wedge the producer until close() (hass#233).
_DRAIN_TIMEOUT = 10.0


class FrameRedactor:
    """Frame-aware stateful redactor for a captured GivEnergy byte stream.

    Replaces ``StreamRedactor``: instead of running byte-level regex over raw socket
    chunks, it reassembles complete GivEnergy frames (using the same 0x5959 marker
    scan the ``Framer`` uses), decodes each one, redacts only the known-sensitive
    fields by type (envelope serials, C.serial-tagged register values, LAN-config IPs),
    and re-encodes with a freshly-computed CRC.

    Any bytes that cannot be decoded — ``InvalidFrame`` results, inter-frame garbage,
    or a partial frame held at stream end — are emitted **intact** (not mangled) with
    a log message.  Nothing on the wire is ever dropped: the capture is always complete.

    Not thread-safe; use one instance per capture direction.

    See #158 B-3 for the design rationale and the ``LanConfigBroadcast`` PDU that
    handles the #100 WO-dongle LAN-config broadcasts.
    """

    def __init__(self, direction: "Direction" = "rx") -> None:
        self._buf = b""
        self._direction = direction  # determines which PDU decoder to use

    def feed(self, chunk: bytes) -> bytes:
        """Absorb raw bytes; return redacted output for any complete frames found."""
        self._buf += chunk
        return self._process()

    def flush(self) -> bytes:
        """Emit any remaining buffered bytes intact and reset. Call at stream end."""
        tail = self._buf
        self._buf = b""
        if tail:
            _logger.debug("FrameRedactor flushing %db of incomplete/trailing bytes intact", len(tail))
        return tail

    def _process(self) -> bytes:
        out = b""
        while self._buf:
            marker_pos = self._buf.find(_FRAME_MARKER)
            if marker_pos < 0:
                # No frame marker in buffer — keep the last 3 bytes (a split marker
                # could arrive next chunk) and emit the rest intact.
                keep = len(_FRAME_MARKER) - 1
                if len(self._buf) > keep:
                    garbage, self._buf = self._buf[:-keep], self._buf[-keep:]
                    _logger.debug("FrameRedactor: %db pre-marker garbage emitted intact", len(garbage))
                    out += garbage
                break
            if marker_pos > 0:
                # Garbage before the marker — emit intact.
                garbage, self._buf = self._buf[:marker_pos], self._buf[marker_pos:]
                _logger.debug("FrameRedactor: %db inter-frame garbage emitted intact", len(garbage))
                out += garbage
                continue
            # Marker is at position 0. Read the length field to know frame size.
            if len(self._buf) < 6:
                break  # not enough bytes for the MBAP length field yet
            hdr_len = int.from_bytes(self._buf[4:6], "big")
            if hdr_len > 300:
                # A real frame's MBAP length never exceeds ~300 (60-register cap). A larger
                # value means this marker is a false positive (random bytes that happen to
                # match) — emit it intact as garbage and resume scanning, rather than buffering
                # up to ~64 KB for a frame that will never complete. Mirrors framer.py's guard.
                skip = len(_FRAME_MARKER)
                garbage, self._buf = self._buf[:skip], self._buf[skip:]
                _logger.debug("FrameRedactor: false marker (len=0x%04x), %db emitted intact", hdr_len, len(garbage))
                out += garbage
                continue
            frame_len = 6 + hdr_len
            if len(self._buf) < frame_len:
                break  # partial frame — wait for more data
            frame, self._buf = self._buf[:frame_len], self._buf[frame_len:]
            out += self._redact_frame(frame)
        return out

    def _redact_frame(self, frame: bytes) -> bytes:
        from givenergy_modbus.model.register import Converter
        from givenergy_modbus.pdu import ClientIncomingMessage, ClientOutgoingMessage
        from givenergy_modbus.pdu.lan_config import LanConfigBroadcast
        from givenergy_modbus.pdu.read_registers import ReadRegistersResponse

        # TX frames are ClientOutgoingMessage (requests); RX frames are
        # ClientIncomingMessage (responses/heartbeats).  Using the wrong decoder
        # silently falls through to intact-passthrough, leaking the adapter serial
        # in every captured request.  Pass the right decoder by direction.
        decoder_class = ClientOutgoingMessage if self._direction == "tx" else ClientIncomingMessage
        try:
            pdu = decoder_class.decode_bytes(frame)
        except Exception:
            _logger.warning("FrameRedactor: undecodable frame (%db) emitted intact", len(frame))
            return frame

        # LanConfigBroadcast: delegate to its own redact() — handles serial + IPs
        if isinstance(pdu, LanConfigBroadcast):
            return pdu.redact().encode()

        # Redact envelope serials (present on all Transparent PDUs)
        if hasattr(pdu, "data_adapter_serial_number"):
            pdu.data_adapter_serial_number = Converter.redact_serial(pdu.data_adapter_serial_number) or ""
        if hasattr(pdu, "inverter_serial_number"):
            pdu.inverter_serial_number = Converter.redact_serial(pdu.inverter_serial_number) or ""

        # Redact payload serials in register responses.
        # A serial is stored across 5 consecutive registers; decode the group as a
        # string, apply redact_serial, and re-encode back into register values.
        if isinstance(pdu, ReadRegistersResponse) and not pdu.error:
            reg_type = "HR" if pdu.transparent_function_code == 3 else "IR"
            win_base = pdu.base_register
            win_end = win_base + len(pdu.register_values)  # safer than register_count
            for g_type, g_base, g_count in _SERIAL_GROUPS:
                if g_type != reg_type:
                    continue
                g_end = g_base + g_count
                if g_base < win_base or g_end > win_end:
                    continue  # group not fully within this response window
                offset = g_base - win_base
                raw_bytes = b"".join(v.to_bytes(2, "big") for v in pdu.register_values[offset : offset + g_count])
                serial_str = raw_bytes.decode("latin1").replace("\x00", "").upper()
                redacted = Converter.redact_serial(serial_str) or ""
                # Re-encode: right-pad to g_count*2 bytes, split back into registers
                redacted_bytes = redacted.encode("latin1").ljust(g_count * 2, b"\x00")[: g_count * 2]
                for i in range(g_count):
                    pdu.register_values[offset + i] = int.from_bytes(redacted_bytes[i * 2 : i * 2 + 2], "big")

        return pdu.encode()


@dataclass(frozen=True)
class ProbeRange:
    """A single Modbus read to issue during detect, with its timeout tier.

    ``tier="known"`` → full ``timeout``/``retries``; ``tier="probe"`` → fast
    ``probe_timeout``/``probe_retries`` and ``retry_delay=0``.
    """

    reg_type: str  # "HR" or "IR"
    device_address: int
    base_register: int
    register_count: int
    tier: str  # "known" | "probe"


def _strategise(
    caps: PlantCapabilities,
    prior: PlantCapabilities | None,
    step: str,
) -> list[ProbeRange]:
    """Pure: return the ProbeRanges for one detect step given current caps and prior hint.

    Calls the same candidate helpers as ``_derive_capabilities`` so candidate generation
    has one implementation.  No I/O.
    """
    ranges: list[ProbeRange]

    if step == "aio_modules":
        num = caps.bcu_stacks[0][1] if caps.bcu_stacks else 0
        addrs: list[int] | range = (
            list(prior.aio_battery_module_addresses) if prior is not None else _aio_module_candidates(num)
        )
        ranges = [ProbeRange("IR", addr, 60, 60, "probe") for addr in addrs]

    elif step == "hv_bmus":
        if not (caps.is_hv and caps.device_type is not Model.ALL_IN_ONE and caps.bcu_stacks):
            ranges = []
        else:
            addrs = (
                list(prior.hv_bmu_addresses)
                if prior is not None and prior.hv_bmu_addresses
                else _hv_bmu_candidates(caps.bcu_stacks)
            )
            ranges = [ProbeRange("IR", addr, 60, 60, "probe") for addr in addrs]

    elif step == "meters":
        addrs = prior.meter_addresses if prior is not None else _COLD_METER_RANGE
        ranges = [ProbeRange("IR", addr, 60, 30, "probe") for addr in addrs]

    elif step == "lv_bcu":
        addr = prior.lv_bcu_address if prior is not None else LV_BCU_ADDRESS
        if addr is None:
            ranges = []
        else:
            ranges = [ProbeRange("IR", addr, 60, 60, "probe")]

    else:
        raise ValueError(f"_strategise: unknown step {step!r}")

    _logger.debug(
        "_strategise(%s, prior=%s): %d range(s) → %s",
        step,
        "hinted" if prior is not None else "cold",
        len(ranges),
        [(f"0x{r.device_address:02x}", r.reg_type, r.base_register, r.register_count) for r in ranges],
    )
    return ranges


def _refresh_banks(caps: PlantCapabilities) -> list[tuple[int, int, int]]:
    """Return (device_address, base_register, register_count) for every IR bank to poll."""
    inverter = caps.inverter_address
    banks: list[tuple[int, int, int]] = []
    if not caps.is_ems:
        banks += [(inverter, 0, 60), (inverter, 180, 60)]
    if caps.is_three_phase:
        for base in range(1000, 1414, 60):
            banks.append((inverter, base, min(60, 1414 - base)))
    if caps.is_ems:
        banks.append((inverter, 2040, 55))
    if caps.is_gateway:
        for base in range(1600, 1860, 60):
            banks.append((inverter, base, min(60, 1860 - base)))
    for addr in caps.lv_battery_addresses:
        banks.append((addr, 60, 60))
    if caps.lv_bcu_address is not None:
        banks.append((caps.lv_bcu_address, 60, 60))
    for addr in caps.meter_addresses:
        banks.append((addr, 60, 30))
    for offset, _ in caps.bcu_stacks:
        banks.append((0x70 + offset, 60, 60))
    for addr in caps.aio_battery_module_addresses:
        banks.append((addr, 60, 60))
    for addr in caps.hv_bmu_addresses:
        banks.append((addr, 60, 60))
    return banks


def _refresh_ranges(
    caps: PlantCapabilities,
    max_age: float | None,
    plant: Plant,
    *,
    now: datetime | None = None,
) -> list[TransparentRequest]:
    """Return the TransparentRequests for one refresh cycle, skipping absent and fresh banks.

    A bank that detect marked ABSENT (``plant.block_present()`` is False) is skipped
    unconditionally — the presence marker is a stronger, cheaper signal than a timeout,
    so a known-absent device is never re-solicited (call ``detect()`` or
    ``invalidate_presence()`` to recheck). Of the remaining banks, when ``max_age`` is
    set any whose ``plant.block_age()`` is not None and ≤ ``max_age`` seconds is also
    omitted. With ``max_age`` None and no absent banks every bank is included
    (bit-identical to the pre-#268 behaviour). No I/O.
    """
    reqs: list[TransparentRequest] = []
    for addr, base, count in _refresh_banks(caps):
        if plant.block_present(addr, "IR", base, count) is False:
            _logger.debug("refresh: skipping IR(%d,%d)@0x%02x — detect marked it absent", base, count, addr)
            continue
        if max_age is not None:
            age = plant.block_age(addr, "IR", base, count, now=now)
            if age is not None and age <= max_age:
                _logger.debug(
                    "refresh: skipping IR(%d,%d)@0x%02x — %.1fs ≤ %.1fs max_age",
                    base,
                    count,
                    addr,
                    age,
                    max_age,
                )
                continue
        reqs.append(ReadInputRegistersRequest(base_register=base, register_count=count, device_address=addr))
    return reqs


class Client:
    """Asynchronous client for talking to a GivEnergy inverter over Modbus TCP.

    Holds a long-lived connection drained by a single producer/consumer task pair.
    All public methods are coroutines and assume they're awaited from the same
    asyncio event loop.

    Concurrency contract
    --------------------

    The client is designed to be used from multiple concurrent callers — e.g. a
    polling loop calling ``refresh_plant()`` and entity-write handlers calling
    ``one_shot_command()`` independently. The following invariants hold:

    **Safe to interleave**

    - Reads (``refresh_plant``, ``load_config``, ``refresh``) and writes
      (``one_shot_command``) may run concurrently. Their request/response pairs
      occupy disjoint shape-hash spaces, so they never collide in the in-flight
      tracking dict.
    - ``tx_queue`` is a FIFO drained by a single producer task with rate limiting
      between frames; bytes from one frame never interleave with another. A queued
      frame whose response future is already done (i.e. resolved by a late arrival
      from a previous attempt) is skipped at dequeue time rather than written to
      the wire, so retry storms don't duplicate work the inverter has already done.
    - Incoming frames are reassembled and dispatched serially by the consumer
      task, so register-cache mutations are applied one PDU at a time.

    **Must be serialised**

    - ``detect()`` mutates ``plant.capabilities`` (including in-place appends to
      its address lists) and must not run concurrently with anything that reads
      those fields — most importantly ``refresh()`` and ``load_config()``.
      In typical use ``detect()`` runs once at connect time before the polling
      loop starts, which satisfies this naturally. Downstream consumers caching
      capabilities across restarts can bypass ``detect()`` on reconnect entirely.

    **Practical guidance for downstream consumers**

    - Take a per-client lock around ``refresh_plant()`` so successive polls don't
      overlap. Writes don't need the same lock — they're free to land between
      polls.
    - Connection loss is surfaced three ways: ``self.connected`` flips to
      ``False``, the noticing task logs a WARNING, and every in-flight or
      subsequently attempted request raises ``ConnectionLost`` (a
      ``CommunicationError`` that is also a ``TimeoutError``, so legacy
      ``except TimeoutError`` handling keeps working — catch ``ConnectionLost``
      first to distinguish reconnect-me from a genuine stall). ``connect()`` is
      idempotent and tears down the previous connection on its own, so it can
      be called directly as a reconnect primitive.
    """

    framer: Framer
    expected_responses: dict[int, Future[TransparentResponse]] = {}
    plant: Plant
    # refresh_count: int = 0
    # debug_frames: Dict[str, Queue]
    connected = False
    _shutting_down = False
    _capture_sink: Callable[[Direction, bytes], None] | None = None
    # Per-direction stream redactors for an active capture — carry a small tail
    # across socket-read chunks so a serial split across a boundary is still
    # redacted (#117). Created in capture_frames(), None when no capture runs.
    _capture_redactor_rx: "FrameRedactor | None" = None
    _capture_redactor_tx: "FrameRedactor | None" = None
    reader: StreamReader
    writer: StreamWriter
    network_consumer_task: Task | None
    network_producer_task: Task | None

    # (raw_frame, frame_sent_future, response_future). frame_sent_future is signalled by
    # the producer once the frame has been written; response_future, when present, is
    # consulted before writing so a frame whose response already arrived (e.g. as a late
    # arrival to a previous attempt) is skipped rather than duplicated on the wire.
    tx_queue: Queue[tuple[bytes, Future | None, Future | None]]

    def __init__(
        self,
        host: str,
        port: int,
        connect_timeout: float = 2.0,
        tx_message_wait: float = 0.25,
        tx_jitter: float = 0.1,
        plant: Plant | None = None,
        splice_heal_seconds: float | None = None,
        splice_reject_heal_seconds: float | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        # Minimum gap between consecutive frames hitting the wire. Empirically
        # load-bearing across hardware generations — see issue #71 for context.
        self.tx_message_wait = tx_message_wait
        # Upper bound on the additive random jitter applied on top of
        # tx_message_wait. Disperses concurrent bursts (polling ticks, retry
        # storms) so they don't clump at fixed 250 ms boundaries. Asymmetric
        # by design — preserves the historic tx_message_wait floor and only
        # ever lengthens the gap; set to 0 to disable.
        self.tx_jitter = tx_jitter
        self.framer = ClientFramer()
        # ``plant`` is for single-owner pre-built plants only (e.g. restoring a
        # persisted PlantCapabilities). Do NOT share one Plant across two active
        # Clients: both call plant.update() into the same register_caches, and
        # two devices that answer at the same Modbus address (e.g. EMS + direct
        # inverter both at 0x11) will overwrite each other's cache. The safe
        # multi-Client path is separate Plants + plant.add_direct_source().
        self.plant = plant if plant is not None else Plant()
        # How long to hold last-good for a disputed *constant* battery register (num_cells,
        # bms_firmware_version) before healing to a sustained new value (#286). Applied only when
        # explicitly given, so an injected plant's own splice_heal_seconds isn't silently clobbered;
        # otherwise the Plant field's own default (900 s) stands. Larger = more robust against
        # ongoing splice corruption (which reverts in minutes); smaller = faster recovery from a
        # genuinely poisoned cold-start baseline. Consumers can watch plant.splice_held_count +
        # plant.block_age() to see when data is being held.
        if splice_heal_seconds is not None:
            self.plant.splice_heal_seconds = splice_heal_seconds
        # Opt-in recovery for a sustained *legitimate* >=2-physics battery step — the near-full-SOC
        # charge knee, which otherwise hard-rejects and freezes telemetry until it settles (#299).
        # None (default) leaves it disabled (the >=2-physics reject stays terminal); a float (e.g.
        # 300) enables the heal with that time bound. Off by default because the positive path can't
        # be validated against the existing corpus — opt in on a pack that tops out regularly.
        # Applied only when explicitly given, so an injected plant's own value isn't clobbered.
        if splice_reject_heal_seconds is not None:
            self.plant.splice_reject_heal_seconds = splice_reject_heal_seconds
        self.tx_queue = Queue(maxsize=20)
        self.expected_responses = {}
        self._shutting_down = False
        self._connection_lost = False
        self.network_producer_task: Task | None = None
        self.network_consumer_task: Task | None = None
        # self.debug_frames = {
        #     'all': Queue(maxsize=1000),
        #     'error': Queue(maxsize=1000),
        # }

    async def connect(self) -> None:
        """Connect to the remote host and start background tasks.

        Idempotent: if the client is already connected, the existing connection
        and background tasks are torn down before establishing a new one. This
        makes ``connect()`` safe to use as a reconnect primitive without a
        separate ``close()`` step, and guarantees the new background tasks see
        ``_shutting_down`` as False even after a prior ``close()``.
        """
        # After an unexpected EOF the consumer sets ``connected = False`` and exits,
        # but the reader/writer/producer-task can still be live — calling
        # ``connect()`` again without a tear-down would leave the old producer task
        # running against shared state alongside the new one. Treat any of those
        # leftover resources as "needs cleanup", not just the ``connected`` flag.
        if (
            self.connected
            or self.network_consumer_task is not None
            or self.network_producer_task is not None
            or getattr(self, "reader", None) is not None
            or getattr(self, "writer", None) is not None
        ):
            await self.close()
        self._shutting_down = False
        self._connection_lost = False
        try:
            connection = asyncio.open_connection(host=self.host, port=self.port, flags=socket.TCP_NODELAY)
            self.reader, self.writer = await asyncio.wait_for(connection, timeout=self.connect_timeout)
        except OSError as e:
            raise CommunicationError(f"Error connecting to {self.host}:{self.port}") from e
        self.network_consumer_task = asyncio.create_task(self._task_network_consumer(), name="network_consumer")
        self.network_producer_task = asyncio.create_task(self._task_network_producer(), name="network_producer")
        # asyncio.create_task(self._task_dump_queues_to_files(), name='dump_queues_to_files'),
        self.connected = True
        _logger.info(f"Connection established to {self.host}:{self.port}")

    async def close(self):
        """Disconnect from the remote host and clean up tasks and queues."""
        self.connected = False
        self._shutting_down = True
        if self.tx_queue:
            while not self.tx_queue.empty():
                _, frame_sent, _ = self.tx_queue.get_nowait()
                if frame_sent:
                    frame_sent.cancel()
        if self.network_producer_task:
            self.network_producer_task.cancel()
        if hasattr(self, "writer") and self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except ConnectionResetError:
                pass
            del self.writer

        if self.network_consumer_task:
            self.network_consumer_task.cancel()
        if hasattr(self, "reader") and self.reader:
            self.reader.feed_eof()
            self.reader.set_exception(RuntimeError("cancelling"))
            del self.reader

        self.expected_responses = {}
        # self.debug_frames = {
        #     'all': Queue(maxsize=1000),
        #     'error': Queue(maxsize=1000),
        # }

    def _abort_connection(self, exc: ConnectionLost) -> None:
        """Tear down shared state after an UNEXPECTED connection drop (#356).

        Called by whichever network task notices death (reader EOF, writer
        closing, stalled drain) — and by the send path's stuck-producer
        safety net. Idempotent: the ``_connection_lost`` flag guards re-entry,
        and every operation is a no-op the second time. Intentional shutdown
        (``close()``) early-returns: the #50 quiet paths stay close()'s job.

        Deliberately does NOT touch reader/writer/task attributes — connect()'s
        leftover-check and close() own that cleanup (#274 atomicity).
        """
        if self._shutting_down or self._connection_lost:
            return
        self._connection_lost = True
        self.connected = False
        # Unblock in-flight senders awaiting a response.
        aborted = 0
        for fut in self.expected_responses.values():
            if not fut.done():
                fut.set_exception(exc)
                aborted += 1
        self.expected_responses = {}
        # Unblock senders awaiting frame-sent for still-queued frames.
        drained = 0
        while not self.tx_queue.empty():
            _, frame_sent, response_future = self.tx_queue.get_nowait()
            for queued_fut in (frame_sent, response_future):
                if queued_fut is not None and not queued_fut.done():
                    queued_fut.set_exception(exc)
            drained += 1
        # Cancel the sibling task; the noticing task (if any) exits on its own.
        current = asyncio.current_task()
        for task in (self.network_consumer_task, self.network_producer_task):
            if task is not None and task is not current and not task.done():
                task.cancel()
        _logger.debug(
            "Connection teardown: aborted %d in-flight request(s), drained %d queued frame(s) (%s)",
            aborted,
            drained,
            exc,
        )

    async def _probe(self, request: TransparentRequest, timeout: float, retries: int) -> bool:
        """Send a request; return True on success, False on TimeoutError.

        Uses ``retry_delay=0`` so absent-device probes don't pay the silent-
        window-survival cost — detect() does many of these and most are
        expected to fail.
        """
        try:
            await self.send_request_and_await_response(
                request, timeout=timeout, retries=retries, retry_delay=0, warn_timeout=False
            )
            return True
        except TimeoutError:
            return False

    async def _probe_ranges(
        self,
        ranges: list[ProbeRange],
        timeout: float,
        retries: int,
        probe_timeout: float,
        probe_retries: int,
    ) -> None:
        """Issue each ProbeRange in order by tier; mark_absent on probe-tier failures."""
        for pr in ranges:
            req_cls = ReadHoldingRegistersRequest if pr.reg_type == "HR" else ReadInputRegistersRequest
            request = req_cls(
                base_register=pr.base_register,
                register_count=pr.register_count,
                device_address=pr.device_address,
            )
            if pr.tier == "known":
                await self.send_request_and_await_response(request, timeout=timeout, retries=retries)
            else:
                ok = await self._probe(request, timeout=probe_timeout, retries=probe_retries)
                _logger.debug(
                    "_probe_ranges: 0x%02x %s(%d,%d) → %s",
                    pr.device_address,
                    pr.reg_type,
                    pr.base_register,
                    pr.register_count,
                    "present" if ok else "absent",
                )
                if not ok:
                    self.plant.mark_absent(pr.device_address, pr.reg_type, pr.base_register, pr.register_count)
                    self.plant.register_caches.pop(pr.device_address, None)

    async def _detect_bcu_stacks(
        self,
        caps: PlantCapabilities,
        prior: PlantCapabilities | None,
        probe_timeout: float,
        probe_retries: int,
    ) -> None:
        """Populate caps.bcu_stacks. Hinted mode trusts prior layout; cold mode reads BMS at 0xA0."""
        if prior is not None:
            # Hinted: probe each previously-seen BCU and record what the BCU actually
            # reports for its module count (rather than trusting `prior`). The probe
            # populates IR(60–64) into the register cache; IR(64) is the BCU's own
            # module count. Letting actual values flow into `caps` here means a
            # change in stack composition is surfaced by the subsequent comparison
            # against `prior` rather than silently accepted. BMS read at 0xA0 is
            # skipped entirely — prior already tells us which BCUs to look at.
            for offset, _stored_modules in prior.bcu_stacks:
                if await self._probe(
                    ReadInputRegistersRequest(base_register=60, register_count=5, device_address=0x70 + offset),
                    timeout=probe_timeout,
                    retries=probe_retries,
                ):
                    bcu_cache = self.plant.register_caches.get(0x70 + offset, RegisterCache())
                    actual_modules = bcu_cache.get(IR(64)) or 0
                    caps.bcu_stacks.append((offset, actual_modules))
                else:
                    self.plant.mark_absent(0x70 + offset, "IR", 60, 5)
                    self.plant.register_caches.pop(0x70 + offset, None)
            return

        # Cold path: ask the BMS how many BCUs exist, then probe each.
        # 0xA0 is the BMS device address; IR(61) holds the number of BCUs present.
        if not await self._probe(
            ReadInputRegistersRequest(base_register=60, register_count=5, device_address=0xA0),
            timeout=probe_timeout,
            retries=probe_retries,
        ):
            self.plant.mark_absent(0xA0, "IR", 60, 5)
            self.plant.register_caches.pop(0xA0, None)
            return
        bms_cache: RegisterCache = self.plant.register_caches.get(0xA0, RegisterCache())
        num_bcus = bms_cache.get(IR(61)) or 0
        for i in range(num_bcus):
            if await self._probe(
                ReadInputRegistersRequest(base_register=60, register_count=60, device_address=0x70 + i),
                timeout=probe_timeout,
                retries=probe_retries,
            ):
                bcu_cache = self.plant.register_caches.get(0x70 + i, RegisterCache())
                num_modules = bcu_cache.get(IR(64)) or 0
                caps.bcu_stacks.append((i, num_modules))
            else:
                self.plant.mark_absent(0x70 + i, "IR", 60, 60)
                self.plant.register_caches.pop(0x70 + i, None)

    #: Maximum number of battery modules on a single-BCU AIO (addresses 0x50–0x53).
    _AIO_MAX_MODULES = 4

    async def _ems_rollup_cross_check(self, timeout: float, retries: int) -> None:
        """Read IR(2040,55) at detect time and sanity-check the per-managed-inverter rollup.

        Populating the rollup during discovery means consumers don't need to
        wait for the first refresh cycle to see per-managed-inverter and
        per-meter data. The sanity check catches malformed rollups (or
        parser regressions) early.

        Best-effort end-to-end: a timeout on the read, or any anomaly during
        validation, only logs a warning — discovery never fails on this soft
        data check. See #95.
        """
        try:
            await self.send_request_and_await_response(
                ReadInputRegistersRequest(base_register=2040, register_count=55, device_address=0x11),
                timeout=timeout,
                retries=retries,
            )
        except TimeoutError:
            _logger.warning("detect: EMS rollup read at IR(2040,55) timed out — skipping cross-check")
            return
        self._validate_ems_rollup()

    def _validate_ems_rollup(self) -> None:
        """Sanity-check the EMS IR(2040,55) rollup decoded into the inverter's register cache.

        Logs warnings for any anomaly (no data, decode failure, implausible
        ``inverter_count``, malformed serial strings) but never raises —
        ``detect()`` shouldn't fail discovery on a soft data check. The
        intent is to surface parser regressions early without breaking the
        rest of the discovery flow.
        """
        cache = self.plant.register_caches.get(0x11)
        # EMS data is served at 0x11 (the rollup read above targets it, and Step 1's
        # HR(0,60) read populated the same cache). `cache is None` is therefore
        # unreachable in practice — the meaningful check is whether the rollup's IR
        # registers actually landed. `RegisterCache` is a defaultdict returning 0 for
        # missing keys, so without this guard a silently-failed rollup read would decode
        # as inverter_count=0 and mis-fire the implausible-count warning.
        if cache is None or IR(2040) not in cache:
            _logger.warning("detect: EMS rollup read returned no data at 0x11 — skipping cross-check")
            return
        try:
            ems = EmsRegisterGetter(cache).build()
        except Exception as e:  # noqa: BLE001 — best-effort sanity check, log and move on
            _logger.warning("detect: EMS rollup decode failed during cross-check: %s", e)
            return
        inverter_count = ems.get("inverter_count")
        if inverter_count is None or not (0 < inverter_count <= 4):
            _logger.warning(
                "detect: EMS rollup reports implausible inverter_count=%r (expected 1..4)",
                inverter_count,
            )
            return
        serials: list[str | None] = []
        for i in range(1, inverter_count + 1):
            raw = ems.get(f"inverter_{i}_serial_number")
            # Decoded serial fields can carry trailing NUL or space padding when the
            # underlying registers were partially populated; strip before matching so
            # a padded-but-valid serial doesn't fire a false warning.
            cleaned = raw.strip("\x00 ") if isinstance(raw, str) else raw
            serials.append(cleaned)
            if not (isinstance(cleaned, str) and _GE_SERIAL_STR_PATTERN.fullmatch(cleaned)):
                _logger.warning(
                    "detect: EMS rollup inverter_%d_serial_number=%r doesn't match GE serial format",
                    i,
                    cleaned,
                )
        # Decoded serials carry identifying information; keep them out of INFO-level
        # application logs to stay consistent with the wire-capture redaction posture
        # (`redact()` / PR #99). The per-slot WARNING already surfaces anomalies.
        _logger.debug(
            "detect: EMS rollup cross-check — inverter_count=%d, serials=[%s]",
            inverter_count,
            ", ".join(repr(s) for s in serials),
        )

    async def detect(
        self,
        timeout: float = 2.0,
        retries: int = 3,
        probe_timeout: float = 0.5,
        probe_retries: int = 1,
        prior: PlantCapabilities | None = None,
    ) -> PlantCapabilities:
        """Discover device type and peripheral topology.

        Reads HR(0) and HR(21) from the inverter to resolve the model, then
        probes for BCUs (HV systems), meters, and LV battery devices.

        Both returns the PlantCapabilities instance and assigns it to
        `self.plant.capabilities` — the returned object and the one stored on
        the plant are the same. Subsequent calls to Client.refresh() and
        Client.load_config() will use it automatically.

        When `prior` is supplied, the probe sweep restricts itself to the
        addresses listed in it — empty addresses from a cold sweep are skipped.
        If reality doesn't match prior (device_type changed, or any hinted
        address fails to confirm), raises PlantTopologyMismatch and leaves
        `self.plant.capabilities` as None. The exception carries `prior` and
        `actual` so callers can decide whether to retry, fall back to a cold
        detect(), or surface the change to the user.

        Uses a two-tier timeout: `timeout`/`retries` for the known inverter device
        (where a response is expected), and `probe_timeout`/`probe_retries` for
        speculative probes where absence is the common case.

        On a connection-level failure (TimeoutError / CommunicationError) the
        connection is torn down via close(), so connect()+detect() is atomic:
        `connected` flips to False and the standard "reconnect if not connected"
        idiom recovers (#274). A PlantTopologyMismatch is raised on a healthy
        connection (only the hint was wrong) and leaves it up so the caller can
        retry a cold detect().
        """
        try:
            return await self._detect(
                timeout=timeout,
                retries=retries,
                probe_timeout=probe_timeout,
                probe_retries=probe_retries,
                prior=prior,
            )
        except PlantTopologyMismatch:
            # Healthy connection — only the hint was wrong; capabilities already cleared.
            raise
        except (TimeoutError, CommunicationError):
            # A connection-level failure leaves a half-open socket with capabilities
            # unset. Tear down so connect()+detect() is atomic (#274). Guard close()
            # so a teardown error (e.g. a flaky writer.wait_closed()) can't mask the
            # original failure we're propagating.
            try:
                await self.close()
            except Exception:
                _logger.exception("detect: error during connection teardown after failure")
            raise

    async def _detect_lv_batteries(
        self,
        prior: PlantCapabilities | None,
        timeout: float,
        retries: int,
        probe_timeout: float,
        probe_retries: int,
    ) -> None:
        """Populate register caches for LV battery addresses (detect step 4).

        Battery pack #1 is at 0x32, additional packs at 0x33–0x37 (the inverter lives at 0x11, not
        0x32 — issues #119/#189). Per-slot (not break-on-fail) like the meter sweep: addresses can be
        non-contiguous and a transient BMS timeout on pack N must not drop pack N+1 onward.
        is_valid() gating and caps population are handled by _derive_capabilities.
        """
        await self.send_request_and_await_response(
            ReadInputRegistersRequest(base_register=60, register_count=60, device_address=0x32),
            timeout=timeout,
            retries=retries,
        )
        # #352/#289: since #352 a caps-absent 0x32 read routes through the battery getter, so its first
        # preamble frame is held by the cold-start splice guard (the cache stays empty pending a
        # corroborating re-read) exactly like 0x33+. detect() reads each address once, so without this
        # confirming read the primary pack is dropped at the _derive_capabilities gate below and
        # refresh() never re-polls it. One healthy re-read corroborates and commits; a flapping/spliced
        # bank fails to corroborate and correctly stays out (#289 anti-poison intact).
        if not self.plant.register_caches.get(0x32):
            await self.send_request_and_await_response(
                ReadInputRegistersRequest(base_register=60, register_count=60, device_address=0x32),
                timeout=timeout,
                retries=retries,
            )
        batt_candidates = prior.lv_battery_addresses if prior is not None else _COLD_LV_BATTERY_RANGE
        for batt_addr in batt_candidates:
            if batt_addr > 0x32:
                if not await self._probe(
                    ReadInputRegistersRequest(base_register=60, register_count=60, device_address=batt_addr),
                    timeout=probe_timeout,
                    retries=probe_retries,
                ):
                    self.plant.mark_absent(batt_addr, "IR", 60, 60)
                    self.plant.register_caches.pop(batt_addr, None)
                    continue
                # #233/#289: the first battery bank against an empty cache is held by the cold-start
                # splice guard (the cache stays empty pending a corroborating re-read). detect()
                # probes each address once, so without this confirming read the address is dropped at
                # the gate below and refresh() never re-polls it — a permanent hold for a recovered/
                # returned pack. One healthy re-read corroborates and commits; a flapping/spliced bank
                # fails to corroborate and correctly stays out (#289 anti-poison intact). Removed once
                # #213's placeholder model decouples enumeration from data adoption.
                if not self.plant.register_caches.get(batt_addr):
                    await self._probe(
                        ReadInputRegistersRequest(base_register=60, register_count=60, device_address=batt_addr),
                        timeout=probe_timeout,
                        retries=probe_retries,
                    )
                if not self.plant.register_caches.get(batt_addr):
                    self.plant.mark_absent(batt_addr, "IR", 60, 60)

    async def _detect(
        self,
        timeout: float,
        retries: int,
        probe_timeout: float,
        probe_retries: int,
        prior: PlantCapabilities | None,
    ) -> PlantCapabilities:
        """Implementation of detect(); see detect() for the contract and error semantics."""
        if prior is not None:
            _logger.info(
                "detect: hinted mode — assuming device_type=Model.%s, inverter=0x%02x, "
                "meters=[%s], lv_batteries=[%s], bcus=[%s], lv_bcu=%s",
                prior.device_type.name,
                prior.inverter_address,
                ", ".join(f"0x{a:02x}" for a in prior.meter_addresses),
                ", ".join(f"0x{a:02x}" for a in prior.lv_battery_addresses),
                ", ".join(f"0x{0x70 + offset:02x} (x{n})" for offset, n in prior.bcu_stacks),
                f"0x{prior.lv_bcu_address:02x}" if prior.lv_bcu_address is not None else "None",
            )

        # Step 1 — read the inverter's configuration block to get DTC and ARM firmware.
        # 0x11 is the inverter's canonical address for every model (#189); discovery reads
        # there and the response is cached under 0x11 (issue #119). resolve_model() below maps
        # the DTC to the model; PlantCapabilities derives the same 0x11 for later polling.
        await self.send_request_and_await_response(
            ReadHoldingRegistersRequest(base_register=0, register_count=60, device_address=0x11),
            timeout=timeout,
            retries=retries,
        )
        cache: RegisterCache = self.plant.register_caches.get(0x11, RegisterCache())
        raw_dtc = cache.get(HR(0))
        if raw_dtc is None:
            raise CommunicationError(
                "detect: HR(0) not populated after reading device 0x11 — cannot determine device type"
            )
        arm_fw = cache.get(HR(21)) or 0
        caps = PlantCapabilities(device_type=resolve_model(raw_dtc, arm_fw))
        _logger.info("detect: device_type=Model.%s", caps.device_type.name)

        if prior is not None and prior.device_type != caps.device_type:
            self.plant.capabilities = None
            raise PlantTopologyMismatch(
                f"detect: device_type changed since prior capture "
                f"(prior={prior.device_type}, actual={caps.device_type}) — discarding hint",
                prior=prior,
                actual=caps,
            )

        # Step 2 — BCU probing for HV systems.
        if caps.is_hv:
            await self._detect_bcu_stacks(caps, prior, probe_timeout, probe_retries)
            _logger.info(
                "detect: bcu_stacks=[%s]",
                ", ".join(f"0x{0x70 + o:02x} (x{n})" for o, n in caps.bcu_stacks),
            )

        # Step 2b — AIO per-module battery probing (#192). The All-in-One exposes each
        # battery module at its own device address (0x50+), distinct from the bcu_stacks
        # stride layout, so its per-module cell/temperature/serial data is reachable.
        if caps.device_type is Model.ALL_IN_ONE and caps.bcu_stacks:
            _offset, num_modules = caps.bcu_stacks[0]
            if num_modules > self._AIO_MAX_MODULES:
                _logger.warning(
                    "detect: BCU reports %d modules but AIO maximum is %d — clamping",
                    num_modules,
                    self._AIO_MAX_MODULES,
                )
            await self._probe_ranges(
                _strategise(caps, prior, "aio_modules"), timeout, retries, probe_timeout, probe_retries
            )

        # Step 2c — HV BMU per-module probing (#265). Non-AIO HV stacks expose per-cell data at
        # their own BMU addresses (0x50+), distinct from the bcu_stacks stride decode (which read
        # the BCU's cluster registers as cells). Self-gated inside _strategise to non-AIO HV.
        await self._probe_ranges(_strategise(caps, prior, "hv_bmus"), timeout, retries, probe_timeout, probe_retries)

        # Step 3 — meter probing. Hinted: only previously-seen addresses. Cold: full 0x01–0x08 sweep.
        # In both modes, a probe response is necessary but not sufficient — some EMS firmwares
        # ACK every slot in 0x01..0x08 with all-zero registers regardless of whether a meter is
        # actually wired. Validate via Meter.is_valid() to filter those ghosts (in the validate step
        # below). Per-slot (not break-on-fail): meters can be non-contiguous. See #95.
        await self._probe_ranges(_strategise(caps, prior, "meters"), timeout, retries, probe_timeout, probe_retries)

        # Step 4 — LV battery + LV BCU detection. Skipped for HV systems (handled at step 2) and
        # EMS plant controllers (don't expose IR at the inverter address — see #86).
        if not caps.is_hv and not caps.is_ems:
            # _detect_lv_batteries stays imperative: it issues a known-tier preamble read
            # at 0x32 and contains the cold-start splice-guard reprobe (#233/#289/#213).
            await self._detect_lv_batteries(prior, timeout, retries, probe_timeout, probe_retries)

            # Step 4b — LV BCU page probe (#241).
            await self._probe_ranges(_strategise(caps, prior, "lv_bcu"), timeout, retries, probe_timeout, probe_retries)

        # Step 5 — EMS rollup cross-check. See `_ems_rollup_cross_check()` for the contract.
        if caps.is_ems:
            await self._ems_rollup_cross_check(timeout=timeout, retries=retries)

        # Validate: derive the authoritative capabilities from the now-populated register_caches.
        # is_valid() gating, mark_absent on invalid, and all candidate logic live in _derive_capabilities;
        # no duplicated enumeration here. on_reject threads mark_absent into the validate step.
        final_caps = _derive_capabilities(self.plant.register_caches, prior, on_reject=self.plant.mark_absent)
        _logger.info(
            "detect: meters=[%s], lv_batteries=[%s], lv_bcu=%s, aio_modules=[%s], hv_bmus=[%s]",
            ", ".join(f"0x{a:02x}" for a in final_caps.meter_addresses),
            ", ".join(f"0x{a:02x}" for a in final_caps.lv_battery_addresses),
            f"0x{final_caps.lv_bcu_address:02x}" if final_caps.lv_bcu_address is not None else "None",
            ", ".join(f"0x{a:02x}" for a in final_caps.aio_battery_module_addresses),
            ", ".join(f"0x{a:02x}" for a in final_caps.hv_bmu_addresses),
        )

        if prior is not None and prior != final_caps:
            self.plant.capabilities = None
            raise PlantTopologyMismatch(
                f"detect: plant topology does not match prior — prior={prior!r}, actual={final_caps!r}",
                prior=prior,
                actual=final_caps,
            )

        self.plant.capabilities = final_caps
        return final_caps

    async def _execute_reads(
        self,
        requests: list[TransparentRequest],
        *,
        timeout: float,
        retries: int,
        retry_delay: float,
    ) -> None:
        """Run a batch of register reads, tolerating partial failure.

        Successful reads have already been written to the register caches by the
        network consumer task, so this only decides how to *signal* the failures:

        - no failures → return (the caller returns the populated plant);
        - some failed → raise ``RefreshPartiallySucceeded`` carrying the partial
          plant plus the structured failures — the caller's one chance to use
          the data that did come back;
        - all failed → raise ``RefreshFailed`` (link effectively dead).
        """
        if not requests:
            return
        results = await self.execute(
            requests, timeout=timeout, retries=retries, retry_delay=retry_delay, return_exceptions=True
        )
        failures: list[ReadFailure] = []
        causes: list[Exception] = []
        for req, res in zip(requests, results, strict=True):
            if isinstance(res, Exception):
                # base_register/register_count live on read requests, which is all
                # _execute_reads is ever handed; getattr keeps mypy happy without a
                # never-taken else branch.
                failures.append(
                    ReadFailure(
                        req.device_address,
                        type(req).__name__,
                        getattr(req, "base_register", 0),
                        getattr(req, "register_count", 0),
                    )
                )
                causes.append(res)
            elif isinstance(res, BaseException):
                # Control-flow exceptions (e.g. CancelledError) must never be swallowed.
                raise res
        if not failures:
            return
        group = ExceptionGroup(f"{len(failures)}/{len(requests)} register reads failed", causes)
        summary = ", ".join(f"{f.request_type}(0x{f.device_address:02x},{f.base_register})" for f in failures)
        if len(failures) == len(requests):
            _logger.warning("All %d register reads failed; treating plant as unreachable", len(requests))
            raise RefreshFailed(f"all {len(requests)} register reads failed", failures=failures, cause=group)
        _logger.warning("%d of %d register reads failed: %s", len(failures), len(requests), summary)
        raise RefreshPartiallySucceeded(
            f"{len(failures)} of {len(requests)} register reads failed",
            plant=self.plant,
            failures=failures,
            cause=group,
        )

    async def load_config(self, timeout: float = 2.0, retries: int = 3, retry_delay: float = 0.5) -> Plant:
        """Read HR configuration blocks for the inverter.

        Returns the populated plant on full success. On partial/total read
        failure raises ``RefreshPartiallySucceeded`` / ``RefreshFailed``.

        Success does not imply *fresh*: the keep-last-good guards (CRC #255, sub-bus
        splice #256, bank holds) report a successful poll while serving last-known-good
        content for a device whose live read was rejected. Display consumers should gate
        on ``Plant.register_age()`` / ``Plant.block_age()``, not on a poll returning.
        """
        caps = self.plant.capabilities
        if caps is None:
            raise PlantNotDetected(
                "load_config() requires plant capabilities — call detect() once first, "
                "or restore a persisted PlantCapabilities onto client.plant.capabilities."
            )
        inverter = caps.inverter_address
        is_ems = caps.is_ems
        # HR(0,60) is the identity/firmware/serial bank that every device type — including EMS —
        # answers; it's the same bank detect() reads to identify the device. The HR(60,60),
        # HR(120,60) and IR(120,60) banks are inverter-specific; EMS plant controllers don't
        # expose them and the reads time out every poll. The EMS's own window at HR(2040,36)
        # is covered by the EMS-conditional append below. See #86 (wire capture confirmed via
        # dewet22/givenergy-hass#52).
        reqs: list[TransparentRequest] = [
            ReadHoldingRegistersRequest(base_register=0, register_count=60, device_address=inverter),
        ]
        if not is_ems:
            reqs += [
                ReadHoldingRegistersRequest(base_register=60, register_count=60, device_address=inverter),
                ReadHoldingRegistersRequest(base_register=120, register_count=60, device_address=inverter),
                ReadInputRegistersRequest(base_register=120, register_count=60, device_address=inverter),
            ]
        if caps.is_three_phase:
            reqs += [
                ReadHoldingRegistersRequest(base_register=1000, register_count=60, device_address=inverter),
                ReadHoldingRegistersRequest(base_register=1060, register_count=60, device_address=inverter),
                ReadHoldingRegistersRequest(base_register=1120, register_count=5, device_address=inverter),
            ]
        if caps.has_extended_slots:
            reqs.append(ReadHoldingRegistersRequest(base_register=240, register_count=60, device_address=inverter))
        if caps.has_smart_load_block:
            # HR(540-599) — Smart Load scheduling slots 1–10 (HR554-573). Gated because
            # the block was added from the app's Direct Control catalogue (writable
            # surface only — never confirmed to answer a live read) and HYBRID_GEN1 times
            # out on it (#179). The gate set is currently empty, so this is off for every
            # model pending hardware confirmation; the smart_load_slot_* decode Defs and
            # set_smart_load_slot_* write helpers are unaffected. Unmodelled registers in
            # 540-553 and 574-599 are silently ignored by Plant.update(). (#48, #179)
            reqs.append(ReadHoldingRegistersRequest(base_register=540, register_count=60, device_address=inverter))
        if caps.has_hv_cabinet_block:
            # HR(499-510) — HV cabinet topology (12 registers: counts, ratings). Gated
            # because the block is from the GivEnergy app v4.0.7 and no model
            # has been confirmed to answer a live read. The gate set is empty until a
            # capture confirms the block responds. (#265)
            reqs.append(ReadHoldingRegistersRequest(base_register=499, register_count=12, device_address=inverter))
        if caps.has_peak_shaving_block:
            # HR(20000-20051) — peak-shaving / valley-filling (sparse: 20000-20003,
            # 20020-20021, 20050-20051). Gated because the block is from the
            # GivEnergy app v4.0.7 and no model has been confirmed to answer a live read.
            # The 52-register window covers all defined offsets; undefined registers in
            # the middle are silently ignored by Plant.update().
            reqs.append(ReadHoldingRegistersRequest(base_register=20000, register_count=52, device_address=inverter))
        if caps.has_ac_config_block:
            # HR(300-359) — AC-output config: export_priority (HR311), battery_*_limit_ac
            # (HR313/314), enable_eps (HR317), pause mode/slot (HR318-320). Present on
            # AC-coupled inverters AND the All-in-One; DC-coupled/hybrid models time out on
            # this block (#162). Confirmed present on Model.AC (hass#52 portal writes) and
            # the AIO (live poll populated these fields, #105).
            reqs.append(ReadHoldingRegistersRequest(base_register=300, register_count=60, device_address=inverter))
        if caps.is_ems:
            reqs.append(ReadHoldingRegistersRequest(base_register=2040, register_count=36, device_address=inverter))
        await self._execute_reads(reqs, timeout=timeout, retries=retries, retry_delay=retry_delay)
        return self.plant

    async def refresh(
        self,
        timeout: float = 2.0,
        retries: int = 1,
        retry_delay: float = 0.5,
        ir0_max_age: float | None = None,
        *,
        max_age: float | None = None,
    ) -> Plant:
        """Read IR measurement blocks for all known devices.

        Returns the populated plant on full success. On partial/total read
        failure raises ``RefreshPartiallySucceeded`` / ``RefreshFailed``.

        Success does not imply *fresh*: the keep-last-good guards (CRC #255, sub-bus
        splice #256, bank holds) report a successful poll while serving last-known-good
        content for a device whose live read was rejected. Display consumers should gate
        on ``Plant.register_age()`` / ``Plant.block_age()``, not on a poll returning.

        The ``timeout=2.0, retries=1`` defaults are tuned for a contended bus: the
        inverter serialises requests, so when other clients (GivTCP, the vendor app,
        Predbat) poll the same unit a tighter budget produces spurious timeouts even
        though the device is responsive (#132). Pass a tighter budget if you own the
        bus exclusively and want genuine failures surfaced faster.

        ``max_age`` (seconds) opts in to skip-if-fresh for any IR bank (#196, #207):
        GivEnergy dongles fan out the responses to whoever is polling them (the cloud,
        the app, another client), so the consumer often already has recent data in cache
        without us asking. When set, any IR bank committed within ``max_age`` seconds
        is not re-solicited this cycle. Defaults to ``None`` — always solicit, the
        historic behaviour. Note the fan-out only exists while something else is polling
        the unit; on a cloud-disconnected dongle the blocks age out and we solicit them.

        ``ir0_max_age`` is deprecated — use ``max_age`` instead. It applied the same
        logic to IR(0,60) only; ``max_age`` extends it to every bank. Will be removed
        in 3.0.
        """
        caps = self.plant.capabilities
        if caps is None:
            raise PlantNotDetected(
                "refresh() requires plant capabilities — call detect() once first, "
                "or restore a persisted PlantCapabilities onto client.plant.capabilities."
            )
        if ir0_max_age is not None:
            warnings.warn(
                "refresh(ir0_max_age=...) is deprecated; use max_age= instead "
                "(applies to all banks, not just IR(0,60)). ir0_max_age will be "
                "removed in 3.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            if max_age is None:
                max_age = ir0_max_age
        await self._execute_reads(
            _refresh_ranges(caps, max_age, self.plant),
            timeout=timeout,
            retries=retries,
            retry_delay=retry_delay,
        )
        return self.plant

    async def refresh_plant(
        self,
        full_refresh: bool = True,
        max_batteries: int = 5,
        timeout: float = 2.0,
        retries: int = 1,
        retry_delay: float = 0.5,
    ) -> Plant:
        """Deprecated orchestrator — run ``detect()`` once, then drive your own loop.

        .. deprecated::
            Will be removed in 3.0 (soon). This composes ``detect()`` (when needed) +
            ``load_config()`` + ``refresh()``, which is trivial to do in the consumer
            where the partial-failure policy belongs. It propagates
            ``RefreshPartiallySucceeded`` / ``RefreshFailed`` like the primitives —
            note that on a full refresh a partial failure in ``load_config()``
            short-circuits before ``refresh()`` runs; call the primitives directly for
            full control.

            Unlike the primitives, this wrapper runs ``detect()`` for you if
            capabilities are absent (preserving the legacy connect-then-refresh shape).
            New code should call ``detect()`` then ``load_config()`` / ``refresh()``
            directly — the primitives raise ``PlantNotDetected`` rather than guessing
            an address.
        """
        warnings.warn(
            "Client.refresh_plant() is deprecated and will be removed in 3.0. Run detect() once, then "
            "drive your own poll loop over load_config()/refresh(). It now propagates "
            "RefreshPartiallySucceeded/RefreshFailed on partial/total read failure.",
            DeprecationWarning,
            stacklevel=2,
        )
        if max_batteries != 5:
            # Battery addresses now come from detect()/capabilities, so this argument
            # no longer does anything — warn rather than silently ignore a custom value.
            warnings.warn(
                "The max_batteries argument to refresh_plant() is ignored — battery "
                "addresses are now discovered by detect(). It will be removed with "
                "refresh_plant() in 3.0.",
                DeprecationWarning,
                stacklevel=2,
            )
        # The primitives require capabilities; as the legacy one-call wrapper, detect
        # them here if the caller hasn't, so connect()-then-refresh_plant() still works
        # (it now addresses correctly per model — issue #105, where an AIO answering at
        # 0x11 timed out under the old 0x32 fallback).
        if self.plant.capabilities is None:
            self.plant.capabilities = await self.detect(timeout=timeout, retries=retries)
        if full_refresh:
            await self.load_config(timeout=timeout, retries=retries, retry_delay=retry_delay)
        await self.refresh(timeout=timeout, retries=retries, retry_delay=retry_delay)
        return self.plant

    async def watch_plant(
        self,
        handler: Callable | None = None,
        refresh_period: float = 15.0,
        max_batteries: int = 5,
        timeout: float = 2.0,
        retries: int = 1,
        retry_delay: float = 0.5,
        passive: bool = False,
    ):
        """Deprecated poll loop — own the loop in the consumer instead.

        .. deprecated::
            Will be removed in 3.0. Connect, ``detect()``, then loop over
            ``load_config()`` / ``refresh()`` yourself, handling
            ``RefreshPartiallySucceeded`` / ``RefreshFailed`` as suits the consumer.
        """
        warnings.warn(
            "Client.watch_plant() is deprecated and will be removed in 3.0. Own your poll loop: "
            "connect(), detect(), then loop over load_config()/refresh() handling "
            "RefreshPartiallySucceeded/RefreshFailed as you see fit.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.connect()
        await self.refresh_plant(
            True,
            max_batteries=max_batteries,
            timeout=timeout,
            retries=retries,
            retry_delay=retry_delay,
        )
        while True:
            if handler:
                handler()
            await asyncio.sleep(refresh_period)
            if not passive:
                # Defer to refresh_plant so capability-aware polling (EMS, gateway,
                # three-phase, HV stacks, meters) is included on each tick rather
                # than the legacy single-phase IR(0)/IR(180) + battery shape.
                await self.refresh_plant(
                    full_refresh=False,
                    max_batteries=max_batteries,
                    timeout=timeout,
                    retries=retries,
                    retry_delay=retry_delay,
                )

    async def one_shot_command(
        self,
        requests: list[TransparentRequest],
        timeout: float = 1.5,
        retries: int = 0,
        retry_delay: float = 0.5,
        dry_run: bool = False,
    ) -> None:
        """Execute write requests, validating each against the detected inverter model.

        Raises InvalidPduState for any write to a register not permitted for the
        detected model. When capabilities are not yet known, falls back to the
        universally-applicable single-phase register set (conservative).

        If dry_run is True, validates but does not transmit — running the same PDU
        validation (``ensure_valid_state``) the live encode path runs, so a dry run
        never passes for a request real execution would reject.
        """
        caps = self.plant.capabilities
        if caps is not None and caps.is_ems:
            safe = _EmsCommands.WRITE_SAFE_REGISTERS
        elif caps is not None and caps.is_three_phase:
            safe = _ThreePhaseCommands.WRITE_SAFE_REGISTERS
        else:
            safe = _InverterCommands.WRITE_SAFE_REGISTERS
        # HR(300-359) AC-output config-block writes (battery_*_limit_ac, #295) are gated on the
        # capability, not the model class: only a model that exposes the block (Model.AC / AIO)
        # accepts them — never a DC-coupled hybrid, a three-phase unit (it remaps to HR1110/1108),
        # or an undetected client (#296 review).
        if caps is not None and caps.has_ac_config_block and not caps.is_three_phase:
            safe = safe | _AC_CONFIG_WRITE_SAFE_REGISTERS
        model_label = caps.device_type.name if caps is not None else "undetected"
        for req in requests:
            if isinstance(req, WriteHoldingRegisterRequest):
                if req.installer:
                    raise InvalidPduState(
                        f"HR({req.register}) is an installer-tier request; use installer_command() instead",
                        req,
                    )
                if req.register not in safe:
                    raise InvalidPduState(f"HR({req.register}) is not permitted for {model_label} inverter", req)
            # Run the same PDU-level validation encode() runs (value bounds, global
            # safe-register set), so dry-run and live paths reject identically.
            req.ensure_valid_state()
        if not dry_run:
            await self.execute(requests, timeout=timeout, retries=retries, retry_delay=retry_delay)

    async def installer_command(
        self,
        requests: list[TransparentRequest],
        timeout: float = 1.5,
        retries: int = 0,
        retry_delay: float = 0.5,
        dry_run: bool = False,
    ) -> None:
        """Execute installer-tier write requests.

        Like one_shot_command() but admits registers from INSTALLER_WRITE_REGISTERS.
        Requests must be constructed with installer=True via the dedicated helpers in
        client.commands (e.g. set_battery_nominal_power, restore_factory_defaults).

        one_shot_command() always rejects installer-flagged requests — the two methods
        are non-overlapping by design (dual-gate separation).

        If dry_run is True, validates but does not transmit.
        """
        caps = self.plant.capabilities
        if caps is not None and caps.is_ems:
            model_safe = _EmsCommands.WRITE_SAFE_REGISTERS
        elif caps is not None and caps.is_three_phase:
            model_safe = _ThreePhaseCommands.WRITE_SAFE_REGISTERS
        else:
            model_safe = _InverterCommands.WRITE_SAFE_REGISTERS
        if caps is not None and caps.has_ac_config_block and not caps.is_three_phase:
            model_safe = model_safe | _AC_CONFIG_WRITE_SAFE_REGISTERS
        installer_safe = model_safe | INSTALLER_WRITE_REGISTERS
        model_label = caps.device_type.name if caps is not None else "undetected"
        for req in requests:
            if isinstance(req, WriteHoldingRegisterRequest):
                effective_safe = installer_safe if req.installer else model_safe
                if req.register not in effective_safe:
                    raise InvalidPduState(f"HR({req.register}) is not permitted for {model_label} inverter", req)
            req.ensure_valid_state()
        if not dry_run:
            await self.execute(requests, timeout=timeout, retries=retries, retry_delay=retry_delay)

    def _emit_to_sink(self, direction: "Direction", data: bytes) -> None:
        """Hand redacted bytes to the active capture sink, swallowing sink errors.

        The sink is a user-supplied callback. It runs inside the long-lived network
        consumer/producer tasks (and the capture-close flush), so an exception it
        raises would otherwise crash that background task and break the client. A
        capture is a diagnostic tee, never load-bearing — log and carry on.
        """
        sink = self._capture_sink
        if sink is None or not data:
            return
        try:
            sink(direction, data)
        except Exception:  # noqa: BLE001 — a capture sink must never break the client
            _logger.exception("capture sink raised on %s frame; dropping it and continuing", direction)

    async def capture_frames(
        self,
        sink: Callable[[Direction, bytes], None],
        duration: float = 60.0,
    ) -> None:
        """Tee redacted TX/RX wire frames to *sink* for *duration* seconds.

        *sink* is called with the direction ('rx' or 'tx') and the redacted bytes.
        The library always redacts before invoking the sink so callers can't
        accidentally see raw hardware identifiers; persistence, formatting and
        forwarding are the caller's choice.

        Redaction is frame-aware: each complete GivEnergy frame is decoded, its
        serial-bearing fields (envelope serials, C.serial-tagged register values,
        LAN-config IPs) are zeroed by type, and the frame is re-encoded with a
        freshly-computed CRC. Frames that cannot be decoded (unknown function codes,
        malformed/truncated frames) are emitted intact with a log message — they are
        never dropped or mangled. The sink sees complete frames (one call per
        complete frame) rather than raw socket chunks.

        Runs alongside the normal refresh loop — does not suspend reads or writes,
        just tees a copy of each frame to *sink*. Only one capture may run on a
        Client at a time; calling while one is in flight raises RuntimeError.
        """
        if self._capture_sink is not None:
            raise RuntimeError("a frame capture is already running on this client")
        self._capture_sink = sink
        self._capture_redactor_rx = FrameRedactor("rx")
        self._capture_redactor_tx = FrameRedactor("tx")
        try:
            await asyncio.sleep(duration)
        finally:
            # Flush each direction's held tail so the final bytes aren't lost.
            for direction, redactor in (("rx", self._capture_redactor_rx), ("tx", self._capture_redactor_tx)):
                if redactor is not None:
                    self._emit_to_sink(direction, redactor.flush())  # type: ignore[arg-type]
            self._capture_sink = None
            self._capture_redactor_rx = None
            self._capture_redactor_tx = None

    async def _task_network_consumer(self):
        """Task for orchestrating incoming data."""
        while hasattr(self, "reader") and self.reader and not self.reader.at_eof():
            frame = await self.reader.read(300)
            if self._capture_sink is not None and frame and self._capture_redactor_rx is not None:
                self._emit_to_sink("rx", self._capture_redactor_rx.feed(frame))
            async for message in self.framer.decode(frame):
                _logger.debug(f"Processing {message}")
                if isinstance(message, ExceptionBase):
                    _logger.warning(f"Expected response never arrived but resulted in exception: {message}")
                    continue
                if isinstance(message, HeartbeatRequest):
                    _logger.debug("Responding to HeartbeatRequest")
                    await self.tx_queue.put((message.expected_response().encode(), None, None))
                    continue
                if not isinstance(message, TransparentResponse):
                    _logger.warning(f"Received unexpected message type for a client: {message}")
                    continue
                if isinstance(message, WriteHoldingRegisterResponse):
                    if message.error:
                        _logger.warning(f"{message}")
                    else:
                        _logger.info(f"{message}")

                # Update the plant cache *before* resolving the awaiting future so
                # the awaiter is guaranteed to see the updated cache regardless of
                # asyncio scheduling order. Today this happens to work either way
                # because nothing yields between set_result and plant.update, but
                # that's fragile to future refactors — make it explicit.
                self.plant.update(message)
                # Don't resolve the future for a discarded CRC-failed frame — leave it
                # pending so send_request_and_await_response's timeout/retry fires a fresh
                # request rather than treating a corrupt frame as a successful read.
                if getattr(message, "crc_failed", False) and not getattr(message, "lenient_crc_commit", False):
                    continue
                future = self.expected_responses.get(message.shape_hash(), None)
                if future and not future.done():
                    future.set_result(message)
        if self._shutting_down:
            _logger.debug("network_consumer exiting on intentional shutdown")
        else:
            self.connected = False
            _logger.warning("network_consumer: connection lost (reader at EOF)")
            self._abort_connection(ConnectionLost("reader at EOF — connection lost"))

    async def _task_network_producer(self):
        """Producer loop to transmit queued frames with an appropriate delay.

        Frames whose response_future is already done (i.e. resolved by a late
        arrival from a previous attempt that happened to arrive in the queueing
        window) are skipped — there's no point writing a request whose answer
        we already have. The frame_sent future is still signalled so the
        caller-side awaiter unblocks normally.

        Inter-frame sleep is ``tx_message_wait + uniform(0, tx_jitter)``. The
        jitter is asymmetric — it never reduces the gap below ``tx_message_wait``
        — so existing hardware-derived minimum spacing is preserved while
        coordinated bursts (polling ticks, retry storms) disperse naturally.
        """
        while hasattr(self, "writer") and self.writer and not self.writer.is_closing():
            message, frame_sent, response_future = await self.tx_queue.get()
            if response_future is not None and response_future.done():
                _logger.debug("Skipping wire send — response already resolved")
                self.tx_queue.task_done()
                if frame_sent and not frame_sent.done():
                    frame_sent.set_result(True)
                continue
            try:
                self.writer.write(message)
                if self._capture_sink is not None and self._capture_redactor_tx is not None:
                    self._emit_to_sink("tx", self._capture_redactor_tx.feed(message))
                await asyncio.wait_for(self.writer.drain(), timeout=_DRAIN_TIMEOUT)
            except TimeoutError:
                _logger.warning(
                    "network_producer: writer drain stalled >%.0fs — treating connection as lost",
                    _DRAIN_TIMEOUT,
                )
                exc = ConnectionLost("writer drain stalled — connection lost")
                # This frame is already dequeued, so the teardown's queue-drain
                # can't reach it — fail its futures here.
                for fut in (frame_sent, response_future):
                    if fut is not None and not fut.done():
                        fut.set_exception(exc)
                self.tx_queue.task_done()
                self._abort_connection(exc)
                return
            except OSError as e:
                _logger.warning(
                    "network_producer: socket error during write/drain (%s) — treating connection as lost", e
                )
                exc = ConnectionLost(f"socket error during write/drain — connection lost: {e}")
                # This frame is already dequeued, so the teardown's queue-drain
                # can't reach it — fail its futures here.
                for fut in (frame_sent, response_future):
                    if fut is not None and not fut.done():
                        fut.set_exception(exc)
                self.tx_queue.task_done()
                self._abort_connection(exc)
                return
            self.tx_queue.task_done()
            if frame_sent and not frame_sent.done():
                frame_sent.set_result(True)
            # B311: plain random is appropriate for non-cryptographic burst-dispersal jitter.
            await asyncio.sleep(self.tx_message_wait + random.uniform(0, self.tx_jitter))  # nosec B311
        if self._shutting_down:
            _logger.debug("network_producer exiting on intentional shutdown")
        else:
            self.connected = False
            _logger.warning("network_producer: connection lost (writer closing)")
            self._abort_connection(ConnectionLost("writer closing — connection lost"))

    # async def _task_dump_queues_to_files(self):
    #     """Task to periodically dump debug message frames to disk for debugging."""
    #     while True:
    #         await asyncio.sleep(30)
    #         if self.debug_frames:
    #             os.makedirs('debug', exist_ok=True)
    #             for name, queue in self.debug_frames.items():
    #                 if not queue.empty():
    #                     async with aiofiles.open(f'{os.path.join("debug", name)}_frames.txt', mode='a') as str_file:
    #                         await str_file.write(f'# {arrow.utcnow().timestamp()}\n')
    #                         while not queue.empty():
    #                             item = await queue.get()
    #                             await str_file.write(item.hex() + '\n')

    def execute(
        self,
        requests: list[TransparentRequest],
        timeout: float,
        retries: int,
        retry_delay: float = 0.5,
        return_exceptions: bool = False,
    ) -> Future[list[TransparentResponse]]:
        """Helper to perform multiple requests in bulk."""
        return asyncio.gather(  # type: ignore[return-value]
            *[
                self.send_request_and_await_response(m, timeout=timeout, retries=retries, retry_delay=retry_delay)
                for m in requests
            ],
            return_exceptions=return_exceptions,
        )

    async def send_request_and_await_response(  # noqa: C901
        self,
        request: TransparentRequest,
        timeout: float,
        retries: int,
        retry_delay: float = 0.5,
        warn_timeout: bool = True,
    ) -> TransparentResponse:
        """Send a request to the remote, await and return the response.

        On timeout, ``retry_delay`` seconds pass before the next attempt is
        enqueued. The default of 0.5s was chosen to overcome the multi-second
        silent-window failure mode observed in the field — firing the retry
        immediately tends to land it inside the same silent window as the
        original request, accomplishing nothing. Callers that want the
        original "retry immediately" behaviour (e.g. fast probes, latency-
        sensitive interactive commands) should pass ``retry_delay=0``.
        """
        if self._connection_lost:
            raise ConnectionLost("connection lost — reconnect before sending")

        # mark the expected response
        expected_response = request.expected_response()
        expected_shape_hash = expected_response.shape_hash()
        existing_response_future = self.expected_responses.get(expected_shape_hash, None)
        if existing_response_future and not existing_response_future.done():
            _logger.debug(f"Cancelling existing in-flight request and replacing: {request}")
            existing_response_future.cancel()

        raw_frame = request.encode()

        def _discard(fut: "Future[TransparentResponse]") -> None:
            # Abandon a future and remove its registration — but only if it's still the one
            # mapped under expected_shape_hash. A newer same-shaped caller may have replaced it
            # (see existing_response_future above); evicting that newer mapping would leave the
            # newer caller unable to receive its response.
            fut.cancel()
            if self.expected_responses.get(expected_shape_hash) is fut:
                del self.expected_responses[expected_shape_hash]

        tries = 0
        while tries <= retries:
            response_future: Future[TransparentResponse] = asyncio.get_running_loop().create_future()
            self.expected_responses[expected_shape_hash] = response_future
            frame_sent = asyncio.get_running_loop().create_future()
            try:
                await asyncio.wait_for(self.tx_queue.put((raw_frame, frame_sent, response_future)), timeout=5.0)
            except TimeoutError as exc:
                _discard(response_future)
                raise TimeoutError("TX queue full — producer task has likely died") from exc
            if self._connection_lost:
                # Lost the race with _abort_connection's queue-drain: our frame was
                # enqueued after the drain and will never be sent. _discard cancels the
                # response future, so a post-reconnect producer skips the stale frame
                # (the queue-front skip-if-resolved check).
                _discard(response_future)
                raise ConnectionLost("connection lost while enqueueing — reconnect before sending")
            # Safety-net wait for the producer to actually send this frame. Worst case the
            # frame sits behind a full queue, and the producer sleeps tx_message_wait + up to
            # tx_jitter (plus a drain) between sends — so scale the bound by the full queue
            # depth, not a flat constant. The old `qsize() + 1`, sampled *after* put() returned,
            # could undershoot to ~1 s and fail a legitimately backlogged-but-healthy producer;
            # a flat 5 s would do the same once the queue filled (20 × ~0.35 s ≈ 7 s). The 1.5×
            # headroom covers per-frame drain and scheduling. Only fires if the producer is stuck.
            frame_sent_timeout = max(
                _FRAME_SENT_MIN_TIMEOUT,
                self.tx_queue.maxsize * (self.tx_message_wait + self.tx_jitter) * 1.5,
            )
            try:
                await asyncio.wait_for(frame_sent, timeout=frame_sent_timeout)
            except ConnectionLost:
                # Teardown failed this frame's future — propagate the typed signal.
                _discard(response_future)
                raise
            except TimeoutError as exc:
                # Drain is bounded (#356), so reaching this means the producer is
                # wedged somewhere unknown — a genuine bug. Tear down so the
                # system recovers, and keep the honest 'stuck' signal.
                _discard(response_future)
                self._abort_connection(ConnectionLost("producer stuck — tearing down"))
                raise TimeoutError("Producer task is stuck — frame not sent") from exc
            try:
                await asyncio.wait_for(response_future, timeout=timeout)
            except ConnectionLost:
                raise  # a drop mid-await propagates immediately; never a retry
            except TimeoutError:
                tries += 1
                _logger.debug(
                    f"Timeout awaiting {expected_response} (future: {response_future}), "
                    f"attempting retry {tries} of {retries}"
                )
                if tries <= retries:
                    # Count the consumed retry (#284), but only where a response was genuinely
                    # expected — absent-device detect probes pass warn_timeout=False and their
                    # expected timeouts shouldn't pollute the per-device retry noise floor.
                    if warn_timeout:
                        self.plant.record_retry(request.device_address)
                    if retry_delay > 0:
                        # Discard the orphaned future so a late response from this attempt
                        # doesn't accidentally resolve into the next attempt's future.
                        response_future.cancel()
                        await asyncio.sleep(retry_delay)
                continue
            response = response_future.result()
            if tries > 0:
                _logger.debug(f"Received {response} after {tries} tries")
            if response.error:
                _logger.error(f"Received error response, retrying: {response}")
                tries += 1
                # Unlike the timeout path above, no response_future.cancel() is needed here:
                # the future is already resolved (we just called .result()), so cancel() would
                # be a no-op, and the next attempt overwrites expected_responses[hash] anyway.
                if tries <= retries:
                    if warn_timeout:  # count the consumed retry (#284); skip absent-device probes
                        self.plant.record_retry(request.device_address)
                    if retry_delay > 0:
                        await asyncio.sleep(retry_delay)
                continue
            return response

        if warn_timeout:
            _logger.warning(f"Timeout awaiting {expected_response} after {tries} tries at {timeout}s, giving up")
        else:
            _logger.debug(f"Timeout awaiting {expected_response} after {tries} tries at {timeout}s (probe miss)")
        raise TimeoutError()
