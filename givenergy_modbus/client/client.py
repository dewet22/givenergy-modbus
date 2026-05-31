import asyncio
import logging
import random
import re
import socket
import warnings
from asyncio import Future, Queue, StreamReader, StreamWriter, Task
from collections.abc import Callable
from typing import Literal

from givenergy_modbus.client import commands
from givenergy_modbus.exceptions import (
    CommunicationError,
    ExceptionBase,
    PlantTopologyMismatch,
    ReadFailure,
    RefreshFailed,
    RefreshPartiallySucceeded,
)
from givenergy_modbus.framer import ClientFramer, Framer
from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.ems import EmsRegisterGetter
from givenergy_modbus.model.inverter import resolve_model
from givenergy_modbus.model.meter import Meter
from givenergy_modbus.model.plant import Plant, PlantCapabilities
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

_logger = logging.getLogger(__name__)

# Standard GE 10-char serial in the textual / decoded form — `[A-Z]{2}\d{4}[A-Z]\d{3}`,
# matches both real serials (e.g. ``CE2231G454``) and the CLI-redacted form
# (``CE0000G000``). Used to sanity-check serial strings decoded out of the EMS rollup.
_GE_SERIAL_STR_PATTERN = re.compile(r"^[A-Z]{2}\d{4}[A-Z]\d{3}$")


# GivEnergy serial numbers are 10 ASCII bytes. Two shapes have been
# observed in real captures:
#
# - Standard form `AAYYWWANNN` (two letters, four-digit YYWW manufacture
#   date, one letter, three-digit unit identifier) — covers inverters,
#   dongles, batteries, meters.
# - EMS plant controller form `AAAYYWWNNN` (three letters, four-digit
#   YYWW date, three-digit unit identifier) — distinct enough to warrant
#   its own pattern.
#
# Redaction preserves the family-prefix letters, the YYWW manufacture
# date, and (for the standard form) the middle letter, while zeroing only
# the trailing three-digit unit identifier — that's the install-unique
# part. The manufacture date is a coarse cohort marker that's useful for
# diagnostics (hardware-revision / firmware-compatibility windows) and a
# far weaker signal than the unit digits. The four-digit cluster is read
# as YYWW: every serial observed parses to a valid week (01–53) and the
# year digits track known install recency. See #113. The middle letter
# is preserved on the principle that it may carry signal (constant "G" in
# every sample so far). Capture group 2 (the date) is kept verbatim.
_SERIAL_PATTERN = re.compile(rb"([A-Z]{2})(\d{4})([A-Z])\d{3}")
_EMS_SERIAL_PATTERN = re.compile(rb"([A-Z]{3})(\d{4})\d{3}")

# Some inverter dongles emit their network configuration as an ASCII
# CSV inside protocol responses — observed as the WO-prefix heartbeat
# carrying `ip,netmask,gateway` every three minutes (see #100). Per-
# octet digit-zeroing preserves the dot-separated structure and total
# length, consistent with the same-offset guarantee the serial
# patterns above already make.
_IPV4_PATTERN = re.compile(rb"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")

Direction = Literal["rx", "tx"]


def _zero_digits(match: re.Match[bytes]) -> bytes:
    """Replace every digit in the matched span with `0`. Length-preserving."""
    return re.sub(rb"\d", b"0", match.group(0))


def redact(frame: bytes) -> bytes:
    """Replace identifying byte runs with their install-unique digits zeroed.

    Currently covers:

    - Standard 10-char GE serials (`AAYYWWANNN`) — family prefix, YYWW
      manufacture date and middle letter preserved; trailing unit digits
      zeroed.
    - EMS plant-controller serials (`AAAYYWWNNN`) — family prefix and
      YYWW date preserved; trailing unit digits zeroed.
    - IPv4 dotted-quads — dots preserved, every digit zeroed. Catches
      LAN topology leaks like the WO-prefix dongle heartbeat (see #100).

    Serial redaction retains the manufacture date (a coarse, diagnostically
    useful cohort marker) while zeroing the install-unique unit identifier;
    see #113 for the rationale. Same length, same byte offsets across all
    substitutions — frame-level CRC/length fields remain consistent so
    offline parsing tools still work on the redacted output.
    """
    frame = _SERIAL_PATTERN.sub(rb"\g<1>\g<2>\g<3>000", frame)
    frame = _EMS_SERIAL_PATTERN.sub(rb"\g<1>\g<2>000", frame)
    frame = _IPV4_PATTERN.sub(_zero_digits, frame)
    return frame


# Longest token redact() matches is a 10-char serial; an IPv4 dotted-quad can be
# up to 15. Holding back the last 14 bytes guarantees any identifier straddling a
# chunk boundary is reassembled before the boundary is emitted.
_REDACT_LOOKBACK = 14


class StreamRedactor:
    """Stateful redactor for a chunked byte stream (e.g. raw socket reads).

    ``redact()`` is per-buffer, so an identifier split across two chunks — the
    prefix in one, the unit-bearing continuation in the next — is seen by neither
    pass and leaks on reassembly (#117; observed in the EMS rollup at IR(2066+)).

    This wrapper carries the trailing ``_REDACT_LOOKBACK`` bytes of each chunk over
    to the next, redacts across the join, and only emits bytes once they're far
    enough from the frontier that no further identifier can overlap them. Byte
    count and offsets are preserved exactly (same guarantee as ``redact()``), so
    the reassembled stream is identical-length to the raw one. Call ``flush()`` at
    end-of-stream to emit the final held tail.

    Not thread-safe; use one instance per capture stream (per direction).
    """

    def __init__(self) -> None:
        # Raw bytes seen but whose redaction isn't yet settled, plus how many of
        # them we've already emitted. We keep the *raw* prefix (not the redacted
        # output) so each pass re-redacts with full left-context, and a match
        # straddling a previous cut is never double-processed.
        self._buffer = b""
        self._emitted = 0

    def feed(self, chunk: bytes) -> bytes:
        """Absorb a chunk; return the bytes that are now safe to emit, redacted.

        Bytes within ``_REDACT_LOOKBACK`` of the buffer end are held back — an
        identifier could still extend into the next chunk — so they aren't emitted
        until enough following bytes arrive (or ``flush()`` is called).
        """
        self._buffer += chunk
        stable_end = len(self._buffer) - _REDACT_LOOKBACK
        if stable_end <= self._emitted:
            return b""
        # Redact the whole buffer for full left-context (offset-preserving), then
        # slice out only the newly-settled span [already-emitted, stable_end).
        redacted = redact(self._buffer)
        out = redacted[self._emitted : stable_end]
        self._emitted = stable_end
        # Prune the settled prefix so a long capture doesn't grow the buffer
        # unbounded. Keep a lookback-sized margin behind the emit frontier as
        # left-context (a match can span at most _REDACT_LOOKBACK bytes), so
        # dropping bytes older than that can't change any future redaction.
        if self._emitted > _REDACT_LOOKBACK:
            drop = self._emitted - _REDACT_LOOKBACK
            self._buffer = self._buffer[drop:]
            self._emitted -= drop
        return out

    def flush(self) -> bytes:
        """Emit the remaining held bytes, redacted. Call once at end of stream."""
        redacted = redact(self._buffer)
        out = redacted[self._emitted :]
        self._buffer = b""
        self._emitted = 0
        return out


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
    - Connection loss is surfaced via ``self.connected`` flipping to ``False``;
      the consumer task logs CRITICAL when this happens. ``connect()`` is
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
    _capture_redactor_rx: "StreamRedactor | None" = None
    _capture_redactor_tx: "StreamRedactor | None" = None
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
        self.plant = Plant()
        self.tx_queue = Queue(maxsize=20)
        self.expected_responses = {}
        self._shutting_down = False
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
            return

        # Cold path: ask the BMS how many BCUs exist, then probe each.
        # 0xA0 is the BMS device address; IR(61) holds the number of BCUs present.
        if not await self._probe(
            ReadInputRegistersRequest(base_register=60, register_count=5, device_address=0xA0),
            timeout=probe_timeout,
            retries=probe_retries,
        ):
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
        """
        if prior is not None:
            _logger.info(
                "detect: hinted mode — assuming device_type=Model.%s, inverter=0x%02x, "
                "meters=[%s], lv_batteries=[%s], bcus=[%s]",
                prior.device_type.name,
                prior.inverter_address,
                ", ".join(f"0x{a:02x}" for a in prior.meter_addresses),
                ", ".join(f"0x{a:02x}" for a in prior.lv_battery_addresses),
                ", ".join(f"0x{0x70 + offset:02x} (x{n})" for offset, n in prior.bcu_stacks),
            )

        # Step 1 — read the inverter's configuration block to get DTC and ARM firmware.
        # 0x11 is the inverter's canonical address; discovery always reads there and the
        # response is cached under 0x11 (issue #119). resolve_model() below maps the DTC to
        # the model, from which PlantCapabilities derives the address used for later polling
        # (0x11, or 0x31 for AC/HYBRID_GEN1).
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

        # Step 3 — meter probing. Hinted: only previously-seen addresses. Cold: full 0x01–0x08 sweep.
        # In both modes, a probe response is necessary but not sufficient — some EMS firmwares
        # ACK every slot in 0x01..0x08 with all-zero registers regardless of whether a meter is
        # actually wired. Validate via Meter.is_valid() to filter those ghosts, matching the
        # convention used for Battery and BCU validation. Per-slot (not break-on-fail) because
        # meters can be non-contiguous (e.g. ports 1 and 3 populated, port 2 empty). See #95.
        meter_candidates = prior.meter_addresses if prior is not None else range(0x01, 0x09)
        for meter_addr in meter_candidates:
            if not await self._probe(
                ReadInputRegistersRequest(base_register=60, register_count=30, device_address=meter_addr),
                timeout=probe_timeout,
                retries=probe_retries,
            ):
                continue
            meter_cache = self.plant.register_caches.get(meter_addr)
            if meter_cache is None or not Meter.from_register_cache(meter_cache).is_valid():
                _logger.debug(
                    "detect: meter probe responded at 0x%02x but is_valid()=False — skipping",
                    meter_addr,
                )
                continue
            caps.meter_addresses.append(meter_addr)
        _logger.info(
            "detect: meter_addresses=[%s]",
            ", ".join(f"0x{a:02x}" for a in caps.meter_addresses),
        )

        # Step 4 — LV battery detection. Battery pack #1 is at 0x32, additional batteries at
        # 0x33–0x37 (the inverter itself now lives at 0x11/0x31, not 0x32 — issue #119). All
        # slots are validated via Battery.is_valid(). Skipped for HV systems (handled at step 2)
        # and EMS plant controllers (don't expose IR at the inverter address — see #86).
        if not caps.is_hv and not caps.is_ems:
            await self.send_request_and_await_response(
                ReadInputRegistersRequest(base_register=60, register_count=60, device_address=0x32),
                timeout=timeout,
                retries=retries,
            )
            batt_candidates = prior.lv_battery_addresses if prior is not None else range(0x32, 0x38)
            for batt_addr in batt_candidates:
                if batt_addr > 0x32:
                    if not await self._probe(
                        ReadInputRegistersRequest(base_register=60, register_count=60, device_address=batt_addr),
                        timeout=probe_timeout,
                        retries=probe_retries,
                    ):
                        break
                    if not self.plant.register_caches.get(batt_addr):
                        break
                try:
                    if not Battery.from_register_cache(self.plant.register_caches[batt_addr]).is_valid():
                        break
                except KeyError, ValueError:
                    break
                caps.lv_battery_addresses.append(batt_addr)
            _logger.info(
                "detect: lv_battery_addresses=[%s]",
                ", ".join(f"0x{a:02x}" for a in caps.lv_battery_addresses),
            )

        # Step 5 — EMS rollup cross-check. See `_ems_rollup_cross_check()` for the contract.
        if caps.is_ems:
            await self._ems_rollup_cross_check(timeout=timeout, retries=retries)

        if prior is not None and prior != caps:
            self.plant.capabilities = None
            raise PlantTopologyMismatch(
                f"detect: plant topology does not match prior — prior={prior!r}, actual={caps!r}",
                prior=prior,
                actual=caps,
            )

        self.plant.capabilities = caps
        return caps

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

    async def _refresh_no_caps(
        self,
        *,
        full_refresh: bool,
        max_batteries: int,
        timeout: float,
        retries: int,
        retry_delay: float,
    ) -> Plant:
        """Legacy capability-free refresh — the pre-detect fallback shape."""
        reqs = commands.refresh_plant_data(full_refresh, self.plant.number_batteries, max_batteries)
        await self._execute_reads(reqs, timeout=timeout, retries=retries, retry_delay=retry_delay)
        return self.plant

    async def load_config(self, timeout: float = 2.0, retries: int = 3, retry_delay: float = 0.5) -> Plant:
        """Read HR configuration blocks for the inverter.

        Returns the populated plant on full success. On partial/total read
        failure raises ``RefreshPartiallySucceeded`` / ``RefreshFailed``.
        """
        caps = self.plant.capabilities
        inverter = caps.inverter_address if caps else 0x32
        is_ems = bool(caps and caps.is_ems)
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
        if caps:
            if caps.is_three_phase:
                reqs += [
                    ReadHoldingRegistersRequest(base_register=1000, register_count=60, device_address=inverter),
                    ReadHoldingRegistersRequest(base_register=1060, register_count=60, device_address=inverter),
                    ReadHoldingRegistersRequest(base_register=1120, register_count=5, device_address=inverter),
                ]
            if caps.has_extended_slots:
                reqs.append(ReadHoldingRegistersRequest(base_register=240, register_count=60, device_address=inverter))
            if caps.is_ems:
                reqs.append(ReadHoldingRegistersRequest(base_register=2040, register_count=36, device_address=inverter))
        await self._execute_reads(reqs, timeout=timeout, retries=retries, retry_delay=retry_delay)
        return self.plant

    async def refresh(self, timeout: float = 2.0, retries: int = 1, retry_delay: float = 0.5) -> Plant:
        """Read IR measurement blocks for all known devices.

        Returns the populated plant on full success. On partial/total read
        failure raises ``RefreshPartiallySucceeded`` / ``RefreshFailed``.

        The ``timeout=2.0, retries=1`` defaults are tuned for a contended bus: the
        inverter serialises requests, so when other clients (GivTCP, the vendor app,
        Predbat) poll the same unit a tighter budget produces spurious timeouts even
        though the device is responsive (#132). Pass a tighter budget if you own the
        bus exclusively and want genuine failures surfaced faster.
        """
        caps = self.plant.capabilities
        if caps is None:
            return await self._refresh_no_caps(
                full_refresh=False, max_batteries=5, timeout=timeout, retries=retries, retry_delay=retry_delay
            )
        inverter = caps.inverter_address
        reqs: list[TransparentRequest] = []
        # EMS plant controllers don't expose IR(0,60) or IR(180,60) — see load_config() and #86.
        if not caps.is_ems:
            reqs += [
                ReadInputRegistersRequest(base_register=0, register_count=60, device_address=inverter),
                ReadInputRegistersRequest(base_register=180, register_count=60, device_address=inverter),
            ]
        if caps.is_three_phase:
            for base in range(1000, 1414, 60):
                reqs.append(
                    ReadInputRegistersRequest(
                        base_register=base,
                        register_count=min(60, 1414 - base),
                        device_address=inverter,
                    )
                )
        if caps.is_ems:
            reqs.append(ReadInputRegistersRequest(base_register=2040, register_count=55, device_address=inverter))
        if caps.is_gateway:
            for base in range(1600, 1860, 60):
                reqs.append(
                    ReadInputRegistersRequest(
                        base_register=base,
                        register_count=min(60, 1860 - base),
                        device_address=inverter,
                    )
                )
        for addr in caps.lv_battery_addresses:
            reqs.append(ReadInputRegistersRequest(base_register=60, register_count=60, device_address=addr))
        for addr in caps.meter_addresses:
            reqs.append(ReadInputRegistersRequest(base_register=60, register_count=30, device_address=addr))
        for offset, _ in caps.bcu_stacks:
            reqs.append(ReadInputRegistersRequest(base_register=60, register_count=60, device_address=0x70 + offset))
        await self._execute_reads(reqs, timeout=timeout, retries=retries, retry_delay=retry_delay)
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
            Will be removed in 3.0. This composes ``load_config()`` + ``refresh()``,
            which is trivial to do in the consumer where the partial-failure policy
            belongs. It now also propagates ``RefreshPartiallySucceeded`` /
            ``RefreshFailed`` like the primitives — note that on a full refresh a
            partial failure in ``load_config()`` short-circuits before ``refresh()``
            runs; call the primitives directly for full control.
        """
        warnings.warn(
            "Client.refresh_plant() is deprecated and will be removed in 3.0. Run detect() once, then "
            "drive your own poll loop over load_config()/refresh(). It now propagates "
            "RefreshPartiallySucceeded/RefreshFailed on partial/total read failure.",
            DeprecationWarning,
            stacklevel=2,
        )
        if self.plant.capabilities:
            if full_refresh:
                await self.load_config(timeout=timeout, retries=retries, retry_delay=retry_delay)
            await self.refresh(timeout=timeout, retries=retries, retry_delay=retry_delay)
            return self.plant
        return await self._refresh_no_caps(
            full_refresh=full_refresh,
            max_batteries=max_batteries,
            timeout=timeout,
            retries=retries,
            retry_delay=retry_delay,
        )

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
        self, requests: list[TransparentRequest], timeout=1.5, retries=0, retry_delay: float = 0.5
    ) -> None:
        """Execute a set of requests. Caller is responsible for connecting first."""
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

        *sink* is called with the direction ('rx' or 'tx') and the *redacted*
        bytes. The library always redacts before invoking the sink so callers
        can't accidentally see raw hardware identifiers; persistence, formatting
        and forwarding are the caller's choice.

        Redaction is cross-chunk-aware: a serial split across two socket reads is
        still caught (#117), at the cost of the sink seeing the stream re-chunked
        (a small trailing tail of each read is deferred to the next sink call, and
        flushed when the capture ends). The reassembled byte stream is identical
        in length and offsets to the raw one. Sinks must not assume one call maps
        to one decodable frame — that was never guaranteed (reads tee raw socket
        buffers, not framer output).

        Runs alongside the normal refresh loop — does not suspend reads or
        writes, just tees a copy of each frame to *sink*. Only one capture
        may run on a Client at a time; calling while one is in flight raises
        RuntimeError.
        """
        if self._capture_sink is not None:
            raise RuntimeError("a frame capture is already running on this client")
        self._capture_sink = sink
        self._capture_redactor_rx = StreamRedactor()
        self._capture_redactor_tx = StreamRedactor()
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
                future = self.expected_responses.get(message.shape_hash(), None)
                if future and not future.done():
                    future.set_result(message)
        if self._shutting_down:
            _logger.debug("network_consumer exiting on intentional shutdown")
        else:
            self.connected = False
            _logger.critical("network_consumer reader at EOF, cannot continue")

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
            self.writer.write(message)
            if self._capture_sink is not None and self._capture_redactor_tx is not None:
                self._emit_to_sink("tx", self._capture_redactor_tx.feed(message))
            await self.writer.drain()
            self.tx_queue.task_done()
            if frame_sent and not frame_sent.done():
                frame_sent.set_result(True)
            # B311: plain random is appropriate for non-cryptographic burst-dispersal jitter.
            await asyncio.sleep(self.tx_message_wait + random.uniform(0, self.tx_jitter))  # nosec B311
        if self._shutting_down:
            _logger.debug("network_producer exiting on intentional shutdown")
        else:
            self.connected = False
            _logger.critical("network_producer writer is closing, cannot continue")

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

    async def send_request_and_await_response(
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
        # mark the expected response
        expected_response = request.expected_response()
        expected_shape_hash = expected_response.shape_hash()
        existing_response_future = self.expected_responses.get(expected_shape_hash, None)
        if existing_response_future and not existing_response_future.done():
            _logger.debug(f"Cancelling existing in-flight request and replacing: {request}")
            existing_response_future.cancel()

        raw_frame = request.encode()

        tries = 0
        while tries <= retries:
            response_future: Future[TransparentResponse] = asyncio.get_running_loop().create_future()
            self.expected_responses[expected_shape_hash] = response_future
            frame_sent = asyncio.get_running_loop().create_future()
            try:
                await asyncio.wait_for(self.tx_queue.put((raw_frame, frame_sent, response_future)), timeout=5.0)
            except TimeoutError as exc:
                raise TimeoutError("TX queue full — producer task has likely died") from exc
            await asyncio.wait_for(
                frame_sent, timeout=self.tx_queue.qsize() + 1
            )  # this should only happen if the producer task is stuck
            try:
                await asyncio.wait_for(response_future, timeout=timeout)
            except TimeoutError:
                tries += 1
                _logger.debug(
                    f"Timeout awaiting {expected_response} (future: {response_future}), "
                    f"attempting retry {tries} of {retries}"
                )
                if tries <= retries and retry_delay > 0:
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
                if tries <= retries and retry_delay > 0:
                    await asyncio.sleep(retry_delay)
                continue
            return response

        if warn_timeout:
            _logger.warning(f"Timeout awaiting {expected_response} after {tries} tries at {timeout}s, giving up")
        else:
            _logger.debug(f"Timeout awaiting {expected_response} after {tries} tries at {timeout}s (probe miss)")
        raise TimeoutError()
