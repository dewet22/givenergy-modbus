import asyncio
import logging
import socket
from asyncio import Future, Queue, StreamReader, StreamWriter, Task
from collections.abc import Callable

from givenergy_modbus.client import commands
from givenergy_modbus.exceptions import CommunicationError, ExceptionBase
from givenergy_modbus.framer import ClientFramer, Framer
from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import resolve_model
from givenergy_modbus.model.plant import Plant, PlantCapabilities
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.pdu import (
    HeartbeatRequest,
    ReadHoldingRegistersRequest,
    ReadInputRegistersRequest,
    TransparentRequest,
    TransparentResponse,
    WriteHoldingRegisterResponse,
)

_logger = logging.getLogger(__name__)


class Client:
    """Asynchronous client utilising long-lived connections to a network device."""

    framer: Framer
    expected_responses: dict[int, Future[TransparentResponse]] = {}
    plant: Plant
    # refresh_count: int = 0
    # debug_frames: Dict[str, Queue]
    connected = False
    _shutting_down = False
    reader: StreamReader
    writer: StreamWriter
    network_consumer_task: Task | None
    network_producer_task: Task | None

    tx_queue: Queue[tuple[bytes, Future | None]]

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
        """Connect to the remote host and start background tasks."""
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
                _, future = self.tx_queue.get_nowait()
                if future:
                    future.cancel()
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
        """Send a request; return True on success, False on TimeoutError."""
        try:
            await self.send_request_and_await_response(request, timeout=timeout, retries=retries, warn_timeout=False)
            return True
        except TimeoutError:
            return False

    async def detect(
        self,
        timeout: float = 2.0,
        retries: int = 3,
        probe_timeout: float = 0.5,
        probe_retries: int = 1,
    ) -> PlantCapabilities:
        """Discover device type and peripheral topology.

        Reads HR(0) and HR(21) from the inverter to resolve the model, then
        probes for BCUs (HV systems), meters, and LV battery slaves.

        Returns a PlantCapabilities instance; the caller is responsible for
        assigning it (e.g. to plant.capabilities) and for passing it to
        Client.refresh() once that method exists.

        Uses a two-tier timeout: `timeout`/`retries` for the known inverter slave
        (where a response is expected), and `probe_timeout`/`probe_retries` for
        speculative probes where absence is the common case.
        """
        # Step 1 — read the inverter's configuration block to get DTC and ARM firmware.
        # 0x11 is the address used during initial discovery; plant.update() rewrites it to 0x32.
        await self.send_request_and_await_response(
            ReadHoldingRegistersRequest(base_register=0, register_count=60, slave_address=0x11),
            timeout=timeout,
            retries=retries,
        )
        cache = self.plant.register_caches.get(0x32, {})
        raw_dtc = cache.get(HR(0))
        if raw_dtc is None:
            raise CommunicationError("detect: HR(0) not populated after reading slave 0x11 — cannot determine device type")
        arm_fw = cache.get(HR(21)) or 0
        caps = PlantCapabilities(device_type=resolve_model(raw_dtc, arm_fw))
        _logger.info("detect: device_type=%s", caps.device_type)

        # Step 2 — BCU probing for HV systems.
        if caps.is_hv:
            # 0xA0 is the BMS slave; IR(61) holds the number of BCUs present.
            if await self._probe(
                ReadInputRegistersRequest(base_register=60, register_count=5, slave_address=0xA0),
                timeout=probe_timeout,
                retries=probe_retries,
            ):
                bms_cache = self.plant.register_caches.get(0xA0, {})
                num_bcus = bms_cache.get(IR(61)) or 0
                for i in range(num_bcus):
                    if await self._probe(
                        ReadInputRegistersRequest(base_register=60, register_count=60, slave_address=0x70 + i),
                        timeout=probe_timeout,
                        retries=probe_retries,
                    ):
                        bcu_cache = self.plant.register_caches.get(0x70 + i, {})
                        num_modules = bcu_cache.get(IR(64)) or 0
                        caps.bcu_slaves.append((i, num_modules))
            _logger.info("detect: bcu_slaves=%s", caps.bcu_slaves)

        # Step 3 — meter probing (slaves 0x01–0x08).
        for meter_addr in range(0x01, 0x09):
            if await self._probe(
                ReadInputRegistersRequest(base_register=60, register_count=30, slave_address=meter_addr),
                timeout=probe_timeout,
                retries=probe_retries,
            ):
                caps.meter_slaves.append(meter_addr)
        _logger.info("detect: meter_slaves=%s", caps.meter_slaves)

        # Step 4 — LV battery detection. Battery #1 shares the inverter's IR bank at 0x32;
        # additional batteries are at 0x33–0x37. All slots are validated via Battery.is_valid().
        if not caps.is_hv:
            await self.send_request_and_await_response(
                ReadInputRegistersRequest(base_register=60, register_count=60, slave_address=0x32),
                timeout=timeout,
                retries=retries,
            )
            for batt_addr in range(0x32, 0x38):
                if batt_addr > 0x32:
                    if not await self._probe(
                        ReadInputRegistersRequest(base_register=60, register_count=60, slave_address=batt_addr),
                        timeout=probe_timeout,
                        retries=probe_retries,
                    ):
                        break
                    if not self.plant.register_caches.get(batt_addr):
                        break
                try:
                    if not Battery.from_register_cache(self.plant.register_caches[batt_addr]).is_valid():
                        break
                except (KeyError, ValueError):
                    break
                caps.lv_battery_slaves.append(batt_addr)
            _logger.info("detect: lv_battery_slaves=%s", caps.lv_battery_slaves)

        return caps

    async def refresh_plant(
        self, full_refresh: bool = True, max_batteries: int = 5, timeout: float = 1.0, retries: int = 0
    ):
        """Refresh data about the Plant."""
        reqs = commands.refresh_plant_data(full_refresh, self.plant.number_batteries, max_batteries)
        await self.execute(reqs, timeout=timeout, retries=retries)
        return self.plant

    async def watch_plant(
        self,
        handler: Callable | None = None,
        refresh_period: float = 15.0,
        max_batteries: int = 5,
        timeout: float = 1.0,
        retries: int = 0,
        passive: bool = False,
    ):
        """Refresh data about the Plant."""
        await self.connect()
        await self.refresh_plant(True, max_batteries=max_batteries)
        while True:
            if handler:
                handler()
            await asyncio.sleep(refresh_period)
            if not passive:
                reqs = commands.refresh_plant_data(False, self.plant.number_batteries)
                await self.execute(reqs, timeout=timeout, retries=retries, return_exceptions=True)

    async def one_shot_command(self, requests: list[TransparentRequest], timeout=1.5, retries=0) -> None:
        """Run a single set of requests and return."""
        await self.connect()
        await self.execute(requests, timeout=timeout, retries=retries)

    async def _task_network_consumer(self):
        """Task for orchestrating incoming data."""
        while hasattr(self, "reader") and self.reader and not self.reader.at_eof():
            frame = await self.reader.read(300)
            # await self.debug_frames['all'].put(frame)
            async for message in self.framer.decode(frame):
                _logger.debug(f"Processing {message}")
                if isinstance(message, ExceptionBase):
                    _logger.warning(f"Expected response never arrived but resulted in exception: {message}")
                    continue
                if isinstance(message, HeartbeatRequest):
                    _logger.debug("Responding to HeartbeatRequest")
                    await self.tx_queue.put((message.expected_response().encode(), None))
                    continue
                if not isinstance(message, TransparentResponse):
                    _logger.warning(f"Received unexpected message type for a client: {message}")
                    continue
                if isinstance(message, WriteHoldingRegisterResponse):
                    if message.error:
                        _logger.warning(f"{message}")
                    else:
                        _logger.info(f"{message}")

                future = self.expected_responses.get(message.shape_hash(), None)
                if future and not future.done():
                    future.set_result(message)
                # try:
                self.plant.update(message)
                # except RegisterCacheUpdateFailed as e:
                #     # await self.debug_frames['error'].put(frame)
                #     _logger.debug(f'Ignoring {message}: {e}')
        if self._shutting_down:
            _logger.debug("network_consumer exiting on intentional shutdown")
        else:
            self.connected = False
            _logger.critical("network_consumer reader at EOF, cannot continue")

    async def _task_network_producer(self, tx_message_wait: float = 0.25):
        """Producer loop to transmit queued frames with an appropriate delay."""
        while hasattr(self, "writer") and self.writer and not self.writer.is_closing():
            message, future = await self.tx_queue.get()
            self.writer.write(message)
            await self.writer.drain()
            self.tx_queue.task_done()
            if future and not future.done():
                future.set_result(True)
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
        self, requests: list[TransparentRequest], timeout: float, retries: int, return_exceptions: bool = False
    ) -> Future[list[TransparentResponse]]:
        """Helper to perform multiple requests in bulk."""
        return asyncio.gather(  # type: ignore[return-value]
            *[self.send_request_and_await_response(m, timeout=timeout, retries=retries) for m in requests],
            return_exceptions=return_exceptions,
        )

    async def send_request_and_await_response(
        self, request: TransparentRequest, timeout: float, retries: int, warn_timeout: bool = True
    ) -> TransparentResponse:
        """Send a request to the remote, await and return the response."""
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
                await asyncio.wait_for(self.tx_queue.put((raw_frame, frame_sent)), timeout=5.0)
            except asyncio.TimeoutError as exc:
                raise TimeoutError("TX queue full — producer task has likely died") from exc
            await asyncio.wait_for(
                frame_sent, timeout=self.tx_queue.qsize() + 1
            )  # this should only happen if the producer task is stuck
            try:
                await asyncio.wait_for(response_future, timeout=timeout)
            except asyncio.TimeoutError:
                tries += 1
                _logger.debug(
                    f"Timeout awaiting {expected_response} (future: {response_future}), "
                    f"attempting retry {tries} of {retries}"
                )
                continue
            response = response_future.result()
            if tries > 0:
                _logger.debug(f"Received {response} after {tries} tries")
            if response.error:
                _logger.error(f"Received error response, retrying: {response}")
                tries += 1
                continue
            return response

        if warn_timeout:
            _logger.warning(f"Timeout awaiting {expected_response} after {tries} tries at {timeout}s, giving up")
        else:
            _logger.debug(f"Timeout awaiting {expected_response} after {tries} tries at {timeout}s (probe miss)")
        raise TimeoutError()
