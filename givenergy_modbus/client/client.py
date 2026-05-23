import asyncio
import logging
import re
import socket
from asyncio import Future, Queue, StreamReader, StreamWriter, Task
from collections.abc import Callable
from typing import Literal

from givenergy_modbus.client import commands
from givenergy_modbus.exceptions import CommunicationError, ExceptionBase, PlantTopologyMismatch
from givenergy_modbus.framer import ClientFramer, Framer
from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import resolve_model
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

# GivEnergy serial numbers are 10 ASCII bytes: AA0000A000 (two letters, four
# digits, one letter, three digits). Only the digits identify the unit; the
# prefix is documented to indicate hardware family (Gen 2 vs Gen 3 vs AIO,
# dongle vs inverter). The middle letter's semantics aren't documented — we
# preserve it on the same principle in case it later turns out to carry
# signal worth keeping. Zero only the digits so the family info survives for
# diagnostics.
_SERIAL_PATTERN = re.compile(rb"([A-Z]{2})\d{4}([A-Z])\d{3}")

Direction = Literal["rx", "tx"]


def redact(frame: bytes) -> bytes:
    """Replace serial-number byte runs with the unit's digits zeroed.

    Preserves the surrounding letters (the prefix carries documented family
    info; the middle letter is preserved on the same principle, in case it
    later turns out to be diagnostically useful). Same length, same byte
    offsets — frame-level CRC/length fields remain consistent so offline
    parsing tools still work on the redacted output.
    """
    return _SERIAL_PATTERN.sub(rb"\g<1>0000\g<2>000", frame)


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
    reader: StreamReader
    writer: StreamWriter
    network_consumer_task: Task | None
    network_producer_task: Task | None

    # (raw_frame, frame_sent_future, response_future). frame_sent_future is signalled by
    # the producer once the frame has been written; response_future, when present, is
    # consulted before writing so a frame whose response already arrived (e.g. as a late
    # arrival to a previous attempt) is skipped rather than duplicated on the wire.
    tx_queue: Queue[tuple[bytes, Future | None, Future | None]]

    def __init__(self, host: str, port: int, connect_timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
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
        # 0x11 is the address used during initial discovery; plant.update() rewrites it to 0x32.
        await self.send_request_and_await_response(
            ReadHoldingRegistersRequest(base_register=0, register_count=60, device_address=0x11),
            timeout=timeout,
            retries=retries,
        )
        cache: RegisterCache = self.plant.register_caches.get(0x32, RegisterCache())
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
        meter_candidates = prior.meter_addresses if prior is not None else range(0x01, 0x09)
        for meter_addr in meter_candidates:
            if await self._probe(
                ReadInputRegistersRequest(base_register=60, register_count=30, device_address=meter_addr),
                timeout=probe_timeout,
                retries=probe_retries,
            ):
                caps.meter_addresses.append(meter_addr)
        _logger.info(
            "detect: meter_addresses=[%s]",
            ", ".join(f"0x{a:02x}" for a in caps.meter_addresses),
        )

        # Step 4 — LV battery detection. Battery #1 shares the inverter's IR bank at 0x32;
        # additional batteries are at 0x33–0x37. All slots are validated via Battery.is_valid().
        if not caps.is_hv:
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
                except (KeyError, ValueError):  # fmt: skip  # TODO: drop parens when 3.13 support ends (PEP 758)
                    break
                caps.lv_battery_addresses.append(batt_addr)
            _logger.info(
                "detect: lv_battery_addresses=[%s]",
                ", ".join(f"0x{a:02x}" for a in caps.lv_battery_addresses),
            )

        if prior is not None and prior != caps:
            self.plant.capabilities = None
            raise PlantTopologyMismatch(
                f"detect: plant topology does not match prior — prior={prior!r}, actual={caps!r}",
                prior=prior,
                actual=caps,
            )

        self.plant.capabilities = caps
        return caps

    async def load_config(self, timeout: float = 2.0, retries: int = 3, retry_delay: float = 0.5) -> Plant:
        """Read HR configuration blocks for the inverter."""
        caps = self.plant.capabilities
        inverter = caps.inverter_address if caps else 0x32
        reqs: list[TransparentRequest] = [
            ReadHoldingRegistersRequest(base_register=0, register_count=60, device_address=inverter),
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
        await self.execute(reqs, timeout=timeout, retries=retries, retry_delay=retry_delay)
        return self.plant

    async def refresh(self, timeout: float = 1.0, retries: int = 0, retry_delay: float = 0.5) -> Plant:
        """Read IR measurement blocks for all known devices."""
        caps = self.plant.capabilities
        if caps is None:
            return await self.refresh_plant(full_refresh=False)
        inverter = caps.inverter_address
        reqs: list[TransparentRequest] = [
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
        await self.execute(reqs, timeout=timeout, retries=retries, retry_delay=retry_delay)
        return self.plant

    async def refresh_plant(
        self,
        full_refresh: bool = True,
        max_batteries: int = 5,
        timeout: float = 1.0,
        retries: int = 0,
        retry_delay: float = 0.5,
    ) -> Plant:
        """Refresh data about the Plant."""
        if self.plant.capabilities:
            if full_refresh:
                await self.load_config(timeout=timeout, retries=retries, retry_delay=retry_delay)
            await self.refresh(timeout=timeout, retries=retries, retry_delay=retry_delay)
            return self.plant
        reqs = commands.refresh_plant_data(full_refresh, self.plant.number_batteries, max_batteries)
        await self.execute(reqs, timeout=timeout, retries=retries, retry_delay=retry_delay)
        return self.plant

    async def watch_plant(
        self,
        handler: Callable | None = None,
        refresh_period: float = 15.0,
        max_batteries: int = 5,
        timeout: float = 1.0,
        retries: int = 0,
        retry_delay: float = 0.5,
        passive: bool = False,
    ):
        """Refresh data about the Plant."""
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

    async def capture_frames(
        self,
        sink: Callable[[Direction, bytes], None],
        duration: float = 60.0,
    ) -> None:
        """Tee redacted TX/RX wire frames to *sink* for *duration* seconds.

        *sink* is called once per frame with the direction ('rx' or 'tx') and
        the *redacted* bytes. The library always redacts before invoking the
        sink so callers can't accidentally see raw hardware identifiers;
        persistence, formatting and forwarding are the caller's choice.

        Runs alongside the normal refresh loop — does not suspend reads or
        writes, just tees a copy of each frame to *sink*. Only one capture
        may run on a Client at a time; calling while one is in flight raises
        RuntimeError.
        """
        if self._capture_sink is not None:
            raise RuntimeError("a frame capture is already running on this client")
        self._capture_sink = sink
        try:
            await asyncio.sleep(duration)
        finally:
            self._capture_sink = None

    async def _task_network_consumer(self):
        """Task for orchestrating incoming data."""
        while hasattr(self, "reader") and self.reader and not self.reader.at_eof():
            frame = await self.reader.read(300)
            if self._capture_sink is not None and frame:
                self._capture_sink("rx", redact(frame))
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

    async def _task_network_producer(self, tx_message_wait: float = 0.25):
        """Producer loop to transmit queued frames with an appropriate delay.

        Frames whose response_future is already done (i.e. resolved by a late
        arrival from a previous attempt that happened to arrive in the queueing
        window) are skipped — there's no point writing a request whose answer
        we already have. The frame_sent future is still signalled so the
        caller-side awaiter unblocks normally.
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
            if self._capture_sink is not None:
                self._capture_sink("tx", redact(message))
            await self.writer.drain()
            self.tx_queue.task_done()
            if frame_sent and not frame_sent.done():
                frame_sent.set_result(True)
            await asyncio.sleep(tx_message_wait)
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
