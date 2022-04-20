from __future__ import annotations

import asyncio
import logging
import random
import socket
from asyncio import PriorityQueue, Queue, StreamReader, StreamWriter, Task
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Awaitable, Callable, Mapping, Sequence

import aiofiles  # type: ignore
from metrology import Metrology
from pymodbus.client.sync import ModbusTcpClient

from givenergy_modbus.decoder import GivEnergyResponseDecoder
from givenergy_modbus.framer import GivEnergyModbusFramer
from givenergy_modbus.modbus import GivEnergyModbusSyncClient
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register import HoldingRegister, InputRegister  # type: ignore
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import (
    HeartbeatRequest,
    HeartbeatResponse,
    ModbusPDU,
    ReadHoldingRegistersRequest,
    ReadInputRegistersRequest,
    ReadInputRegistersResponse,
    WriteHoldingRegisterRequest,
)

_logger = logging.getLogger(__package__)

DEFAULT_SLEEP = 0.5


@dataclass(order=True)
class QueueItem:
    """Encapsulation for messages in a queue, containing data for debugging, expiry, retries, and prioritisation."""

    priority: int
    pdu: ModbusPDU = field(compare=False)
    raw_frame: bytes = field(compare=False)
    expiry: datetime
    ttl: float
    retries_remaining: int

    def __init__(self, pdu: ModbusPDU, raw_frame: bytes = b'', ttl: float = 5.0, retries_remaining: int = 0) -> None:
        super().__init__()
        self.pdu = pdu
        self.raw_frame = raw_frame
        if isinstance(pdu, HeartbeatResponse):
            self.priority = 1
        elif isinstance(pdu, WriteHoldingRegisterRequest):
            self.priority = 2
        else:
            self.priority = 3
        self.expiry = datetime.now() + timedelta(seconds=ttl)
        self.ttl = ttl
        self.retries_remaining = retries_remaining

    @property
    def expired(self) -> bool:
        """Returns whether an item has passed its expiry time."""
        return self.expiry < datetime.now()


# class ExpiringQueue(PriorityQueue[QueueItem]):
#     stats: Counter
#
#     def __init__(self, *args, **kwargs) -> None:
#         super().__init__(*args, **kwargs)
#         self.stats = Counter()
#
#     async def put(self, item: QueueItem) -> None:
#         """Place an item onto the queue."""
#         self.stats['put'] += 1
#         # return await super().put((item.priority, item))
#         return await super().put(item)
#
#     async def get(self) -> QueueItem:
#         """Pop the highest priority item from the queue."""
#         self.stats['get'] += 1
#         return await super().get()


class GivEnergyClient:
    """Synchronous client for end users to conveniently access GivEnergy inverters."""

    def __init__(self, host: str, port: int = 8899, modbus_client: ModbusTcpClient = None):
        self.host = host
        self.port = port
        if modbus_client is None:
            modbus_client = GivEnergyModbusSyncClient(host=self.host, port=self.port)
        self.modbus_client = modbus_client

    def __repr__(self):
        return f"GivEnergyClient({self.host}:{self.port}))"

    def fetch_register_pages(
        self,
        pages: Mapping[type[HoldingRegister | InputRegister], Sequence[int]],
        register_cache: RegisterCache,
        slave_address: int = 0x32,
        sleep_between_queries: float = DEFAULT_SLEEP,
    ) -> None:
        """Reload all inverter data from the device."""
        import time

        for register, base_registers in pages.items():
            for base_register in base_registers:
                data = self.modbus_client.read_registers(register, base_register, 60, slave_address=slave_address)
                register_cache.set_registers(register, data)
                time.sleep(sleep_between_queries)

    def refresh_plant(self, plant: Plant, full_refresh: bool, sleep_between_queries=DEFAULT_SLEEP):
        """Refresh the internal caches for a plant. Optionally refresh only data that changes frequently."""
        inverter_registers = {
            InputRegister: [0, 180],
        }

        if full_refresh:
            inverter_registers[HoldingRegister] = [0, 60, 120]

        self.fetch_register_pages(
            inverter_registers,
            plant.register_caches[0x32],
            slave_address=0x32,
            sleep_between_queries=sleep_between_queries,
        )
        for i in range(plant.number_batteries):
            self.fetch_register_pages(
                {InputRegister: [60]},
                plant.register_caches[0x32 + i],
                slave_address=0x32 + i,
                sleep_between_queries=sleep_between_queries,
            )

    def enable_charge_target(self, target_soc: int):
        """Sets inverter to stop charging when SOC reaches the desired level. Also referred to as "winter mode"."""
        if not 4 <= target_soc <= 100:
            raise ValueError(f'Specified Charge Target SOC ({target_soc}) is not in [4-100]')
        if target_soc == 100:
            self.disable_charge_target()
        else:
            self.modbus_client.write_holding_register(HoldingRegister.ENABLE_CHARGE_TARGET, True)
            self.modbus_client.write_holding_register(HoldingRegister.CHARGE_TARGET_SOC, target_soc)

    def disable_charge_target(self):
        """Removes SOC limit and target 100% charging."""
        self.modbus_client.write_holding_register(HoldingRegister.ENABLE_CHARGE_TARGET, False)
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_TARGET_SOC, 100)

    def enable_charge(self):
        """Set the battery to charge, depending on the mode and slots set."""
        self.modbus_client.write_holding_register(HoldingRegister.ENABLE_CHARGE, True)

    def disable_charge(self):
        """Disable the battery from charging."""
        self.modbus_client.write_holding_register(HoldingRegister.ENABLE_CHARGE, False)

    def enable_discharge(self):
        """Set the battery to discharge, depending on the mode and slots set."""
        self.modbus_client.write_holding_register(HoldingRegister.ENABLE_DISCHARGE, True)

    def disable_discharge(self):
        """Set the battery to not discharge at all."""
        self.modbus_client.write_holding_register(HoldingRegister.ENABLE_DISCHARGE, False)

    def set_battery_discharge_mode_max_power(self):
        """Set the battery to discharge at maximum power (export) when discharging."""
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_POWER_MODE, 0)

    def set_battery_discharge_mode_demand(self):
        """Set the battery to discharge to match demand (no export) when discharging."""
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_POWER_MODE, 1)

    def set_charge_slot_1(self, times: tuple[time, time]):
        """Set first charge slot times."""
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_1_START, int(times[0].strftime('%H%M')))
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_1_END, int(times[1].strftime('%H%M')))

    def reset_charge_slot_1(self):
        """Reset first charge slot times to zero/disabled."""
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_1_START, 0)
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_1_END, 0)

    def set_charge_slot_2(self, times: tuple[time, time]):
        """Set second charge slot times."""
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_2_START, int(times[0].strftime('%H%M')))
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_2_END, int(times[1].strftime('%H%M')))

    def reset_charge_slot_2(self):
        """Reset second charge slot times to zero/disabled."""
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_2_START, 0)
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_2_END, 0)

    def set_discharge_slot_1(self, times: tuple[time, time]):
        """Set first discharge slot times."""
        self.modbus_client.write_holding_register(
            HoldingRegister.DISCHARGE_SLOT_1_START, int(times[0].strftime('%H%M'))
        )
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_1_END, int(times[1].strftime('%H%M')))

    def reset_discharge_slot_1(self):
        """Reset first discharge slot times to zero/disabled."""
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_1_START, 0)
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_1_END, 0)

    def set_discharge_slot_2(self, times: tuple[time, time]):
        """Set second discharge slot times."""
        self.modbus_client.write_holding_register(
            HoldingRegister.DISCHARGE_SLOT_2_START, int(times[0].strftime('%H%M'))
        )
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_2_END, int(times[1].strftime('%H%M')))

    def reset_discharge_slot_2(self):
        """Reset first discharge slot times to zero/disabled."""
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_2_START, 0)
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_2_END, 0)

    def set_mode_dynamic(self):
        """Set system to Dynamic / Eco mode.

        This mode is designed to maximise use of solar generation. The battery will charge when
        there is excess power being generated from your solar panels. The battery will store and hold this energy
        until your demand increases. The system will try and balance the use of solar and battery so that you are
        importing and exporting as little energy as possible. This mode is useful if you want to maximise
        self-consumption of renewable generation and minimise the amount of energy drawn from the grid.
        """
        self.set_battery_discharge_mode_demand()  # r27=1
        self.set_shallow_charge(4)  # r110=4
        self.disable_discharge()  # r59=0

    def set_mode_storage(
        self, slot_1: tuple[time, time] = (time(hour=16), time(hour=7)), slot_2: tuple[time, time] = None, export=False
    ):
        """Set system to storage mode with specific discharge slots(s).

        This mode stores excess solar generation during the day and holds that energy ready for use later in the day.
        By default, the battery will start to discharge from 4pm-7am to cover energy demand during typical peak hours.
        This mode is particularly useful if you get charged more for your electricity at certain times to utilise the
        battery when it is most effective. If the second time slot isn't specified, it will be cleared.

        You can optionally also choose to export excess energy: instead of discharging to meet only your home demand,
        the battery will discharge at full power and any excess will be exported to the grid. This is useful if you
        have a variable export tariff (e.g. Agile export) and you want to target the peak times of day (e.g. 4pm-7pm)
        when it is both most expensive to import and most valuable to export energy.
        """
        if export:
            self.set_battery_discharge_mode_max_power()  # r27=0
        else:
            self.set_battery_discharge_mode_demand()  # r27=1
        self.set_shallow_charge(100)  # r110=100
        self.enable_discharge()  # r59=1
        self.set_discharge_slot_1(slot_1)  # r56=1600, r57=700
        if slot_2:
            self.set_discharge_slot_1(slot_2)  # r56=1600, r57=700
        else:
            self.reset_discharge_slot_2()

    def set_datetime(self, dt: datetime):
        """Set the date & time of the inverter."""
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_YEAR, dt.year)
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_MONTH, dt.month)
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_DAY, dt.day)
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_HOUR, dt.hour)
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_MINUTE, dt.minute)
        self.modbus_client.write_holding_register(HoldingRegister.SYSTEM_TIME_SECOND, dt.second)

    def set_discharge_enable(self, mode: bool):
        """Set the battery to discharge."""
        self.modbus_client.write_holding_register(HoldingRegister.ENABLE_DISCHARGE, int(mode))

    def set_shallow_charge(self, val: int):
        """Set the minimum level of charge to keep."""
        # TODO what are valid values? 4-100?
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_SOC_RESERVE, val)

    def set_battery_charge_limit(self, val: int):
        """Set the battery charge power limit as percentage. 50% (2.6 kW) is the maximum for most inverters."""
        if not 0 <= val <= 50:
            raise ValueError(f'Specified Charge Limit ({val}%) is not in [0-50]%')
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_CHARGE_LIMIT, val)

    def set_battery_discharge_limit(self, val: int):
        """Set the battery discharge power limit as percentage. 50% (2.6 kW) is the maximum for most inverters."""
        if not 0 <= val <= 50:
            raise ValueError(f'Specified Discharge Limit ({val}%) is not in [0-50]%')
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_DISCHARGE_LIMIT, val)

    def set_battery_power_reserve(self, val: int):
        """Set the battery power reserve to maintain."""
        # TODO what are valid values?
        self.modbus_client.write_holding_register(HoldingRegister.BATTERY_DISCHARGE_MIN_POWER_RESERVE, val)

    def set_battery_target_soc(self, val: int):
        """Set the target SOC when the battery charges."""
        # TODO what are valid values?
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_TARGET_SOC, val)


class GivEnergyAsyncClient:
    """Asynchronous client utilising long-lived connections to a network device."""

    host: str
    port: int
    plant: Plant
    connected: bool = False
    tasks: dict[str, Task] = {}

    seconds_between_data_refreshes: float = 5
    full_refresh_interval_count: int = 60  # 5s * 60 = 5m
    wait_between_pdu_writes: float = 0.3

    rx_queue: PriorityQueue[QueueItem] = PriorityQueue()
    tx_queue: PriorityQueue[QueueItem] = PriorityQueue()
    anticipated_responses: set[QueueItem] = set()
    raw_frames_queue: Queue[bytes] = Queue()
    error_frames_queue: Queue[bytes] = Queue()

    reader: StreamReader
    writer: StreamWriter

    def __init__(self, host: str, port: int = 8899, pdu_handler: Callable = None):
        self.host = host
        self.port = port
        self.framer = GivEnergyModbusFramer(GivEnergyResponseDecoder())
        self.pdu_handler = pdu_handler
        self.plant = Plant()
        self.reset_state()

    def reset_state(self):
        """Prepare the internal state for a new connection."""
        if self.connected:
            _logger.warning('Still connected')
        self.connected = False

        if self.tasks:
            _logger.warning(f'Tasks remain: {self.tasks.keys()}')
        self.tasks = {}

        if self.rx_queue and not self.rx_queue.empty():
            _logger.warning(f'{self.rx_queue.qsize()} queued incoming messages discarded.')
        self.rx_queue = PriorityQueue()

        if self.tx_queue and not self.tx_queue.empty():
            _logger.warning(f'{self.tx_queue.qsize()} queued outgoing messages discarded.')
        self.tx_queue = PriorityQueue()

        self.anticipated_responses = set()
        self.raw_frames_queue = Queue()
        self.error_frames_queue = Queue()

        from metrology import registry

        registry.clear()

    async def refresh_data(self):
        """Refresh data from the remote system."""
        meter = Metrology.meter('refreshes')
        if meter.count % self.full_refresh_interval_count == 0:
            _logger.debug('Doing full refresh & probing all batteries')
            await self.enqueue_outbound_pdu(ReadHoldingRegistersRequest(base_register=0, slave_address=0x32))
            await self.enqueue_outbound_pdu(ReadHoldingRegistersRequest(base_register=60, slave_address=0x32))
            await self.enqueue_outbound_pdu(ReadHoldingRegistersRequest(base_register=120, slave_address=0x32))
            await self.enqueue_outbound_pdu(ReadInputRegistersRequest(base_register=120, slave_address=0x32))
            number_batteries = 6
        else:
            number_batteries = self.plant.number_batteries

        await self.enqueue_outbound_pdu(ReadInputRegistersRequest(base_register=0, slave_address=0x32))
        await self.enqueue_outbound_pdu(ReadInputRegistersRequest(base_register=180, slave_address=0x32))

        _logger.debug(f'Refreshing {number_batteries} batteries')
        for i in range(number_batteries):
            await self.enqueue_outbound_pdu(ReadInputRegistersRequest(base_register=60, slave_address=0x32 + i))

        meter.mark()

    async def enqueue_outbound_pdu(self, pdu: ModbusPDU):
        """Place a message on the queue for sending to the network."""
        await self.tx_queue.put(QueueItem(pdu))

    async def send_queued_messages(self):
        """Process outbound messages back onto the network."""
        while not self.tx_queue.empty():
            item = await self.tx_queue.get()
            if item.expired:
                _logger.warning(f'Too old queue item, discarding: {item}')
                continue

            loop = asyncio.get_event_loop()
            packet = await loop.run_in_executor(None, self.framer.build_packet, item.pdu)
            self.writer.write(packet)
            await asyncio.wait_for(self.writer.drain(), timeout=self.wait_between_pdu_writes * 2)
            # self.pdus_sent.append(pdu)
            Metrology.meter('tx-pdus').mark()
            Metrology.meter(f'tx-pdus-{item.pdu.__class__.__name__}').mark()
            Metrology.meter('tx-bytes').mark(len(packet))
            await asyncio.sleep(self.wait_between_pdu_writes)

    async def handle_incoming_packet_data(self):
        """Process the raw incoming bytestream through a Framer to try and decode messages."""

        def pdu_result(new_pdu: ModbusPDU, raw_frame: bytes):
            raw_frames.append(raw_frame)
            if new_pdu:
                new_pdus.append((new_pdu, raw_frame))
            else:
                _logger.error(f'Unable to decode frame {raw_frame.hex()}')
                error_frames.append(raw_frame)
                Metrology.meter('rx-pdus-discarded').mark()

        data = await asyncio.wait_for(self.reader.read(15), timeout=self.seconds_between_data_refreshes * 3)
        Metrology.meter('rx-bytes').mark(len(data))

        new_pdus: list[tuple[ModbusPDU, bytes]] = []
        raw_frames: list[bytes] = []
        error_frames: list[bytes] = []
        loop = asyncio.get_event_loop()

        await loop.run_in_executor(None, self.framer.process_incoming_packet, data, pdu_result)

        if new_pdus:
            for pdu, raw_frame in new_pdus:
                _logger.debug(f'Received {pdu}')
                await self.rx_queue.put(QueueItem(pdu, raw_frame=raw_frame))
                Metrology.meter('rx-pdus').mark()
                Metrology.meter(f'rx-pdus-from-{pdu.slave_address:02x}').mark()
                Metrology.meter(f'rx-pdus-{pdu.__class__.__name__}').mark()
                if pdu.error:
                    Metrology.meter('rx-pdus-error').mark()
                    Metrology.meter(f'rx-pdus-from-{pdu.slave_address:02x}-error').mark()
                    Metrology.meter(f'rx-pdus-{pdu.__class__.__name__}-error').mark()
        else:
            _logger.debug(f'No new PDUs, framer buffer length = {self.framer.buffer_length}')

        if raw_frames:
            for frame in raw_frames:
                await self.raw_frames_queue.put(frame)

        if error_frames:
            for frame in error_frames:
                await self.error_frames_queue.put(frame)

    async def dispatch_incoming_messages(self):
        """Dispatch queued incoming messages."""
        _logger.debug(f'PDUs in rx queue: {self.rx_queue.qsize()}')
        while not self.rx_queue.empty():
            item = await self.rx_queue.get()
            if item.expired:
                _logger.warning(f'Processing expired PDU {item}')
            pdu = item.pdu
            loop = asyncio.get_event_loop()

            if isinstance(pdu, HeartbeatRequest):
                _logger.debug('Returning HeartbeatResponse')
                return_pdu = pdu.expected_response_pdu()
                await self.enqueue_outbound_pdu(return_pdu)
                Metrology.meter('heartbeat').mark()
            else:
                _logger.debug(f'Processing {pdu}')

                try:
                    await loop.run_in_executor(None, self.plant.update, pdu)
                    Metrology.meter(
                        {
                            'name': 'pdu',
                            'direction': 'rx',
                            'type': pdu.__class__.__name__,
                            'slave_address': pdu.slave_address,
                            'result': 'ok',
                        }
                    ).mark()
                except ValueError as e:
                    await self.error_frames_queue.put(item.raw_frame)
                    Metrology.meter('rx-pdus-invalid').mark()
                    Metrology.meter(f'rx-pdus-from-{pdu.slave_address:02x}-invalid').mark()
                    Metrology.meter(f'rx-pdus-{pdu.__class__.__name__}-invalid').mark()

                    # Metrology.meter({'name': 'pdu', 'direction': 'rx', 'result': 'invalid'}).mark()
                    Metrology.meter(
                        {
                            'name': 'pdu',
                            'direction': 'rx',
                            'type': pdu.__class__.__name__,
                            'slave_address': pdu.slave_address,
                            'result': 'invalid',
                        }
                    ).mark()
                    if (  # BMS response based on InputRegister block and slave address range:
                        isinstance(pdu, ReadInputRegistersResponse)
                        and pdu.base_register == 60
                        and pdu.register_count == 60
                        and 0x30 <= pdu.slave_address <= 0x37
                        and sum(pdu.register_values[50:55]) == 0x0  # all-null serial number
                    ):
                        _logger.debug(
                            'Ignoring BMS Response PDU with empty serial number, '
                            f'battery is likely not installed. {pdu}: {e}'
                        )
                    else:
                        _logger.debug(f'Rejecting corrupt-looking {pdu}: {e}')

            if self.pdu_handler:
                return_pdu = await loop.run_in_executor(None, self.pdu_handler, pdu)
                if return_pdu:
                    await self.enqueue_outbound_pdu(return_pdu)

    async def dump_queues_to_files(self):
        """Dump internal queues of messages to files for debugging."""

        async def dump_queue_to_file(queue: Queue, filename: str):
            """Write any queued items to the specified files."""
            if not queue.empty():
                _logger.debug(f'Logging {queue.qsize()} {filename}')
                async with aiofiles.open(f'{filename}.txt', mode='a') as str_file:
                    await str_file.write(f'# {datetime.now().timestamp()}\n')
                    while not queue.empty():
                        item = await queue.get()
                        await str_file.write(item.hex() + '\n')

        await asyncio.gather(
            dump_queue_to_file(self.raw_frames_queue, 'raw_frames'),
            dump_queue_to_file(self.error_frames_queue, 'error_frames'),
        )

    async def health_check(self):
        """Proto healthcheck function."""
        all_tasks = asyncio.all_tasks()
        if len(all_tasks) < 5 or len(all_tasks) > 15:
            tasks = "\n".join([f"    {t.get_name():30} {t._state:10} {t.get_coro()}" for t in all_tasks])
            _logger.warning(f'{len(all_tasks)} tasks scheduled:\n{tasks}')

        # for f in registry:
        #     _logger.info(f'{f[0]}: {f[1].count}')
        # for name, metric in registry.with_tags:
        #     if name[0] == 'pdu':
        #         _logger.info(f'{name}: {metric.count}')
        #     if isinstance(metric, Meter):
        #         self.log_metric(name, 'meter', metric, [
        #             'count', 'one_minute_rate', 'five_minute_rate',
        #             'fifteen_minute_rate', 'mean_rate'
        #         ])

        r = Metrology.meter('refreshes')
        if r.count < 5:
            return
        if r.fifteen_minute_rate < 0.1:
            _logger.error(f'Long-term low refresh rate: {r.fifteen_minute_rate}/s < 0.1/s')
        elif r.five_minute_rate < 0.1:
            _logger.warning(f'Persistently low refresh rate: {r.five_minute_rate} < 0.1/s')
        elif r.one_minute_rate < 0.1:
            _logger.info(f'Low refresh rate: {r.one_minute_rate} < 0.1/s')

        r = Metrology.meter('tx-pdus')
        if r.fifteen_minute_rate < 0.1:
            _logger.error(f'Long-term low tx rate: {r.fifteen_minute_rate}/s << 0.2/s')
        elif r.five_minute_rate < 0.1:
            _logger.warning(f'Persistently low tx rate: {r.five_minute_rate} < 0.2/s')
        elif r.one_minute_rate < 0.1:
            _logger.info(f'Low tx rate: {r.one_minute_rate} < 0.2/s')

    async def connect(self):
        """Connect to the given host and store the reader & writer for use elsewhere."""
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(host=self.host, port=self.port, flags=socket.TCP_NODELAY), timeout=2.0
        )
        self.connected = True
        Metrology.meter('refreshes').clear()
        _logger.info(f'Connected to {self.host}:{self.port}')

    def run_tasks_forever(self, *funcs: tuple[Callable[[], Awaitable], float]):
        """Helper method to wrap coros in tasks, run them a permanent loop and handle cancellation."""

        async def coro(f: Callable[[], Awaitable], s: float, name: str):
            while self.connected:
                try:
                    await f()
                    await asyncio.sleep(s)
                except asyncio.CancelledError as e:
                    _logger.info(f"Cancelling {name}(): {e}")
                    raise
            _logger.info(f"Disconnected, stopping {name}()")

        for func, sleep in funcs:
            func_name = func.__name__
            _logger.debug(f"Forever running {func_name}()")
            self.tasks[func_name] = asyncio.create_task(coro(func, sleep, func_name), name=func_name)

    async def chaos(self):
        """Inject some chaos."""
        await asyncio.sleep(random.randint(60, 600))
        self.writer.close()

    async def loop_forever(self):
        """Main async client loop."""
        while True:
            asyncio.create_task(self.chaos(), name='chaos')
            self.reset_state()
            try:
                await self.connect()
            except (OSError, TimeoutError, asyncio.exceptions.TimeoutError) as e:
                self.connected = False
                _logger.error(f'Error connecting, retrying in 10s: {e}')
                await asyncio.sleep(10)
                continue

            self.run_tasks_forever(
                (self.dispatch_incoming_messages, 0.1),
                (self.handle_incoming_packet_data, 0),
                (self.send_queued_messages, self.wait_between_pdu_writes),
                (self.refresh_data, self.seconds_between_data_refreshes),
                (self.dump_queues_to_files, 60),
                (self.health_check, 10),
            )

            try:
                await asyncio.gather(*self.tasks.values())
                _logger.info('All tasks completed, restarting')
            except (ConnectionError, asyncio.exceptions.TimeoutError) as e:  # TimeoutError
                _logger.error(f'Restarting: {type(e).__name__}{f": {e}" if str(e) else ""}')

            self.cancel_tasks()
            self.writer.close()  # this _should_ never throw an exception regardless of the socket state
            await asyncio.sleep(10)

    def cancel_tasks(self):
        """Cancel looping tasks."""
        self.connected = False
        for name in list(self.tasks.keys()):
            self.tasks[name].cancel()
            del self.tasks[name]
