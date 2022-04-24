from __future__ import annotations

import asyncio
import datetime
import logging
import os
import socket
from asyncio import Queue, StreamReader, StreamWriter, Task
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Mapping, Sequence

import aiofiles  # type: ignore
from metrology import Metrology
from pymodbus.client.sync import ModbusTcpClient

from givenergy_modbus.framer import ClientFramer, PduProcessedCallback
from givenergy_modbus.modbus import SyncClient
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register import HoldingRegister, InputRegister  # type: ignore
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import BasePDU
from givenergy_modbus.pdu.heartbeat import HeartbeatRequest
from givenergy_modbus.pdu.read_registers import (
    ReadHoldingRegistersRequest,
    ReadInputRegistersRequest,
    ReadInputRegistersResponse,
    ReadRegistersRequest,
)
from givenergy_modbus.pdu.transparent import TransparentResponse

_logger = logging.getLogger(__name__)

DEFAULT_SLEEP = 0.5


@dataclass
class Message:
    """Encapsulation for messages in a queue, containing data for debugging, expiry, retries, and prioritisation."""

    pdu: BasePDU
    raw_frame: bytes = b''
    created: datetime.datetime = field(default_factory=datetime.datetime.now)
    ttl: float = 5
    retries_remaining: int = 0

    @property
    def age(self) -> datetime.timedelta:
        """Calculate time since creation."""
        return datetime.datetime.now() - self.created

    @property
    def expiry(self) -> datetime.datetime:
        """Calculate expiry time."""
        return self.created + datetime.timedelta(seconds=self.ttl)

    @property
    def expired(self) -> bool:
        """Returns whether an item has passed its expiry time."""
        return datetime.datetime.now() > self.expiry


class GivEnergyClient:  # type: ignore
    """Synchronous client for end users to conveniently access GivEnergy inverters."""

    def __init__(self, host: str, port: int = 8899, modbus_client: ModbusTcpClient = None):
        self.host = host
        self.port = port
        if modbus_client is None:
            modbus_client = SyncClient(host=self.host, port=self.port)
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

    def set_charge_slot_1(self, times: tuple[datetime.time, datetime.time]):
        """Set first charge slot times."""
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_1_START, int(times[0].strftime('%H%M')))
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_1_END, int(times[1].strftime('%H%M')))

    def reset_charge_slot_1(self):
        """Reset first charge slot times to zero/disabled."""
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_1_START, 0)
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_1_END, 0)

    def set_charge_slot_2(self, times: tuple[datetime.time, datetime.time]):
        """Set second charge slot times."""
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_2_START, int(times[0].strftime('%H%M')))
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_2_END, int(times[1].strftime('%H%M')))

    def reset_charge_slot_2(self):
        """Reset second charge slot times to zero/disabled."""
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_2_START, 0)
        self.modbus_client.write_holding_register(HoldingRegister.CHARGE_SLOT_2_END, 0)

    def set_discharge_slot_1(self, times: tuple[datetime.time, datetime.time]):
        """Set first discharge slot times."""
        self.modbus_client.write_holding_register(
            HoldingRegister.DISCHARGE_SLOT_1_START, int(times[0].strftime('%H%M'))
        )
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_1_END, int(times[1].strftime('%H%M')))

    def reset_discharge_slot_1(self):
        """Reset first discharge slot times to zero/disabled."""
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_1_START, 0)
        self.modbus_client.write_holding_register(HoldingRegister.DISCHARGE_SLOT_1_END, 0)

    def set_discharge_slot_2(self, times: tuple[datetime.time, datetime.time]):
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
        self,
        slot_1: tuple[datetime.time, datetime.time] = (datetime.time(hour=16), datetime.time(hour=7)),
        slot_2: tuple[datetime.time, datetime.time] = None,
        export=False,
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

    def set_datetime(self, dt: datetime.datetime):
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
    seconds_between_pdu_writes: float = 0.3
    seconds_between_main_loop_restarts: float = 5

    # network client
    connect_timeout: float = 2.0
    connect_backoff_initial: float = 1.0
    connect_backoff_ceiling: float = 60.0
    connect_backoff_multiplier: float = 1.2

    rx_messages: Queue[Message]
    tx_messages: Queue[Message]
    anticipated_responses: set[Message]
    rx_bytes: Queue[Message]
    debug_frames: dict[str, Queue[bytes]] = {}

    reader: StreamReader
    writer: StreamWriter

    def __init__(self, host: str, port: int = 8899, pdu_handler: Callable = None):
        self.host = host
        self.port = port
        self.framer = ClientFramer()
        self.pdu_handler = pdu_handler
        self.plant = Plant()

        self.tasks = {}

    def _disconnect(self):
        """Close any existing network connections."""
        self.connected = False
        if self.reader:  # hasattr(self, 'reader'):
            del self.reader
        if self.writer:  # hasattr(self, 'writer'):
            self.writer.close()
            del self.writer

    async def _connect(self):
        """Connect to the given host and store the reader & writer for use elsewhere."""
        backoff = self.connect_backoff_initial
        retries = 0
        while not self.connected:
            try:
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(host=self.host, port=self.port, flags=socket.TCP_NODELAY),
                    timeout=self.connect_timeout,
                )
                self.connected = True
                _logger.info(
                    f'(Re)established connection to {self.host}:{self.port}'
                    f'{f" after {retries} retries" if retries > 0 else ""}'
                )
                return
            except asyncio.exceptions.TimeoutError:
                reason = (
                    f'Timeout establishing connection to {self.host}:{self.port} within {self.connect_timeout:.1f}s'
                )
            except OSError as e:
                reason = f'Error establishing connection to {self.host}:{self.port}: {e}'

            retries += 1
            _logger.error(f'{reason}. Attempting retry #{retries} in {backoff:.1f}s')
            await asyncio.sleep(backoff)
            backoff = min(self.connect_backoff_ceiling, backoff * self.connect_backoff_multiplier)

    def _cancel_tasks(self):
        """Cancel looping tasks."""
        for name in list(self.tasks.keys()):
            self.tasks[name].cancel()
            del self.tasks[name]

    def reset_state(self):
        """Prepare the internal state for a new connection."""
        self.rx_messages = Queue()
        self.tx_messages = Queue()
        self.anticipated_responses = set()
        self.rx_bytes = Queue()
        self.debug_frames = {
            'all': Queue(),
            'error': Queue(),
            'suspicious': Queue(),
            'rejected': Queue(),
        }

    async def enqueue_outbound_pdu(self, pdu: BasePDU):
        """Place a message on the queue for sending to the network."""
        await self.tx_messages.put(Message(pdu))

    #########################################################################################################
    async def schedule_data_refresh_requests(self):
        """Refresh data from the remote system."""

        def enqueue(request_type: type[ReadRegistersRequest], base_register: int, device_number: int = 0):
            return self.enqueue_outbound_pdu(
                request_type(base_register=base_register, register_count=60, slave_address=0x32 + device_number)
            )

        meter = Metrology.meter('refreshes')
        if meter.count % self.full_refresh_interval_count == 0:
            _logger.debug('Doing full refresh & probing all batteries')
            await enqueue(ReadHoldingRegistersRequest, 0)
            await enqueue(ReadHoldingRegistersRequest, 60)
            await enqueue(ReadHoldingRegistersRequest, 120)
            await enqueue(ReadInputRegistersRequest, 120)
            number_batteries = 6
        else:
            number_batteries = self.plant.number_batteries

        await enqueue(ReadInputRegistersRequest, 0)
        await enqueue(ReadInputRegistersRequest, 180)

        _logger.debug(f'Refreshing {number_batteries} batteries')
        for i in range(number_batteries):
            await enqueue(ReadInputRegistersRequest, 60, i)

        meter.mark()

    async def transmit_queued_messages(self):
        """Process outbound messages onto the network."""
        while not self.tx_messages.empty():
            item = await self.tx_messages.get()
            if item.expired:
                _logger.warning(f'Queue item expired, discarding: {item}')
                continue

            _logger.debug(f'Sending {item.pdu}')
            packet = await asyncio.get_event_loop().run_in_executor(None, self.framer.build_packet, item.pdu)
            self.writer.write(packet)
            await asyncio.wait_for(self.writer.drain(), timeout=self.seconds_between_pdu_writes * 2)
            # self.pdus_sent.append(pdu)
            Metrology.meter('tx-pdus').mark()
            Metrology.meter('tx-bytes').mark(len(packet))
            await asyncio.sleep(self.seconds_between_pdu_writes)

    async def await_incoming_data(self):
        """Await incoming data from the network and decode it into complete messages."""
        data = await self.reader.read(15)

        Metrology.meter('rx-bytes').mark(len(data))
        results: PduProcessedCallback[0] = []
        callback: PduProcessedCallback = results.append

        try:
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self.framer.process_incoming_data, data, callback),
                timeout=10,
            )
        except asyncio.TimeoutError:
            _logger.error(
                'Frame processing took >10s, something is stuck. '
                f'Current buffer: len={self.framer.buffer_length} {self.framer._buffer.hex()}'
            )
            return

        if not results:
            _logger.debug(f'No new PDUs, framer buffer length = {self.framer.buffer_length}')
            return

        for pdu, raw_frame in results:
            await self.debug_frames['all'].put(raw_frame)
            if not pdu:
                _logger.error(f'Unable to decode frame {raw_frame.hex()}')
                await self.debug_frames['error'].put(raw_frame)
                Metrology.meter('rx-invalid-frames').mark()
                continue

            _logger.debug(f'Received {pdu}')
            await self.rx_messages.put(Message(pdu, raw_frame=raw_frame))
            Metrology.meter('rx-pdus').mark()
            # Metrology.meter(f'rx-pdus-from-{pdu.slave_address:02x}').mark()
            # Metrology.meter(f'rx-pdus-{pdu.__class__.__name__}').mark()
            if isinstance(pdu, TransparentResponse) and pdu.error:
                _logger.error(f"Received error {pdu}")
                Metrology.meter('rx-errors').mark()
                # Metrology.meter(f'rx-pdus-from-{pdu.slave_address:02x}-error').mark()
                # Metrology.meter(f'rx-pdus-{pdu.__class__.__name__}-error').mark()

    async def dispatch_incoming_messages(self):
        """Dispatch queued incoming messages."""
        _logger.debug(f'PDUs in rx queue: {self.rx_messages.qsize()}')
        while not self.rx_messages.empty():
            item = await self.rx_messages.get()
            if item.expired:
                _logger.warning(f'Processing expired PDU {item}')
            pdu = item.pdu
            loop = asyncio.get_event_loop()

            if isinstance(pdu, HeartbeatRequest):
                _logger.debug('Returning HeartbeatResponse')
                return_pdu = pdu.expected_response_pdu()
                await self.enqueue_outbound_pdu(return_pdu)
                Metrology.meter('heartbeats').mark()
            else:
                _logger.debug(f'Processing {pdu}')

                try:
                    await loop.run_in_executor(None, self.plant.update, pdu)
                except ValueError as e:
                    if (
                        isinstance(pdu, ReadInputRegistersResponse)
                        and pdu.base_register % 60 == 0
                        and pdu.register_count == 60
                    ):
                        count_known_bad_register_values = (
                            pdu.register_values[30] == 0xA119,
                            pdu.register_values[31] == 0x34EA,
                            pdu.register_values[32] == 0xE77F,
                            pdu.register_values[33] == 0xD475,
                            pdu.register_values[35] == 0x4500,
                            pdu.register_values[41] == 0xC0A8,
                            pdu.register_values[43] == 0xC0A8,
                            pdu.register_values[51] == 0x8018,
                            pdu.register_values[52] == 0x43E0,
                            pdu.register_values[53] == 0xF6CE,
                            pdu.register_values[56] == 0x080A,
                            pdu.register_values[58] == 0xFCC1,
                            pdu.register_values[59] == 0x661E,
                        ).count(True)

                        if count_known_bad_register_values > 5:
                            _logger.debug(
                                f'Ignoring known suspicious update with {count_known_bad_register_values} known bad '
                                f'register values {pdu}: {pdu.to_dict()}'
                            )
                            await self.debug_frames['suspicious'].put(item.raw_frame)
                        elif (  # BMS response based on InputRegister block and slave address range:
                            pdu.base_register == 60
                            and 0x30 <= pdu.slave_address <= 0x37
                            and sum(pdu.register_values[50:55]) == 0x0  # all-null serial number
                            and pdu.register_values.count(0) > 55  # mostly null values
                        ):
                            _logger.info(
                                'Ignoring BMS Response PDU with mostly empty values, '
                                f'battery is likely not installed. {pdu}: {e}'
                            )
                        else:
                            await self.debug_frames['rejected'].put(item.raw_frame)
                            _logger.warning(f'Rejecting update {pdu}: {e}')

                        Metrology.meter('rx-invalid').mark()

            if self.pdu_handler:
                return_pdu = await loop.run_in_executor(None, self.pdu_handler, pdu)
                if return_pdu:
                    await self.enqueue_outbound_pdu(return_pdu)

    #########################################################################################################
    async def dump_queues_to_files(self):
        """Dump internal queues of messages to files for debugging."""

        async def dump_queue_to_file(queue: Queue, filename: str):
            """Write any queued items to the specified files."""
            if not queue.empty():
                _logger.debug(f'Logging {queue.qsize()} {filename}')
                async with aiofiles.open(f'{filename}_frames.txt', mode='a') as str_file:
                    await str_file.write(f'# {datetime.datetime.now().timestamp()}\n')
                    while not queue.empty():
                        item = await queue.get()
                        await str_file.write(item.hex() + '\n')

        if self.debug_frames:
            os.makedirs('debug', exist_ok=True)
            tasks = []
            for name, queue in self.debug_frames.items():
                tasks.append(dump_queue_to_file(queue, os.path.join('debug', name)))
            if tasks:
                await asyncio.gather(*tasks)

    async def log_stats(self):
        """Log stats from Metrology."""
        from metrology import registry

        # counters = []
        timers = []
        for meter in registry:
            name, data = meter
            if name.startswith('time-'):
                timers.append(f'{name[5:]}={data.mean:.2f}')
            # else:
            #     counters.append(f'{name}={data.count}')
        # if counters:
        #     _logger.info(f"counters: {' '.join(counters)}")
        if timers:
            _logger.info(f"timers: {' '.join(timers)}")

    async def health_check(self):
        """Proto healthcheck function."""
        all_tasks = asyncio.all_tasks()
        if len(all_tasks) < 5 or len(all_tasks) > 10:
            tasks = "\n".join([f"    {t.get_name():30} {t._state:10} {t.get_coro()}" for t in all_tasks])
            _logger.warning(f'{len(all_tasks)} tasks scheduled:\n{tasks}')

    def run_tasks_forever(self, *funcs: tuple[Callable[[], Awaitable], float, float | None]):
        """Helper method to wrap coros in tasks, run them a permanent loop and handle cancellation."""

        async def coro(f: Callable[[], Awaitable], s: float, name: str, t: float | None):
            while self.connected:
                try:
                    with Metrology.utilization_timer(f'time-{name}'):
                        await asyncio.wait_for(f(), timeout=t)
                    await asyncio.sleep(s)
                except asyncio.CancelledError:
                    _logger.debug(f"Cancelling {name}()")
                    raise
                except asyncio.TimeoutError:
                    _logger.error(f"{name}() took >{t:.1f}s to complete, aborting")
                    # raise
            _logger.debug(f"Stopped {name}()")

        for func, sleep, timeout in funcs:
            func_name = func.__name__
            _logger.debug(f"Forever running {func_name}()")
            self.tasks[func_name] = asyncio.create_task(coro(func, sleep, func_name, timeout), name=func_name)

    # async def chaos(self):
    #     """Inject some chaos."""
    #     await asyncio.sleep(random.randint(300, 6000))
    #     self.writer.close()

    #########################################################################################################
    async def loop_forever(self):
        """Main async client loop."""
        while True:
            self.reset_state()
            await self._connect()
            self.run_tasks_forever(
                (self.dispatch_incoming_messages, 0.1, 10),
                (self.await_incoming_data, 0, 20),
                (self.transmit_queued_messages, self.seconds_between_pdu_writes, 10),
                (self.schedule_data_refresh_requests, self.seconds_between_data_refreshes, 1),
                (self.dump_queues_to_files, 60, 10),
                (self.health_check, 30, 5),
                (self.log_stats, 600, 5),
                # (self.chaos, 0, None),
            )

            try:
                await asyncio.gather(*self.tasks.values())
                _logger.info('All tasks completed, restarting')
            except (OSError, asyncio.exceptions.TimeoutError) as e:
                _logger.error(
                    f'{type(e).__name__}{f": {e}" if str(e) else ""}, '
                    f'restarting in {self.seconds_between_main_loop_restarts:.1f}s'
                )

            self._disconnect()
            self._cancel_tasks()
            await asyncio.sleep(self.seconds_between_main_loop_restarts)
