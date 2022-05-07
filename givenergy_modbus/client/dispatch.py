from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
import os
import socket
import sys
from asyncio import Queue, StreamReader, StreamWriter

import aiofiles  # type: ignore[import]
from metrology import Metrology

from givenergy_modbus.client import Message
from givenergy_modbus.framer import ClientFramer, Framer
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.pdu import BasePDU, ClientOutgoingMessage
from givenergy_modbus.pdu.heartbeat import HeartbeatRequest
from givenergy_modbus.pdu.read_registers import ReadRegistersResponse
from givenergy_modbus.pdu.transparent import TransparentResponse

_logger = logging.getLogger(__name__)


class DispatchingMixin:
    """Network and Message handling functions."""

    host: str
    port: int

    reader: StreamReader
    writer: StreamWriter

    rx_messages: Queue[Message]
    tx_messages: Queue[Message]
    expected_responses: dict[int, Message]
    framer: Framer
    debug_frames: dict[str, Queue[bytes]]

    connected: bool = False
    connect_timeout: float = 2.0
    connect_backoff_initial: float = 1.0
    connect_backoff_ceiling: float = 60.0
    connect_backoff_multiplier: float = 1.2

    refresh_count: int
    seconds_between_data_refreshes: float = 5
    full_refresh_interval_count: int = 60  # 5s * 60 = 5m
    seconds_between_pdu_writes: float = 0.35

    # provided by other mixins
    plant: Plant
    number_batteries: int

    def __init__(self, *args, **kwargs) -> None:
        super().__init__()
        self.host = kwargs.get('host', 'localhost')
        self.port = kwargs.get('port', 8899)
        self.framer = kwargs.get('framer_class', ClientFramer)()

    def __repr__(self):
        return f"{self.__class__.__name__}({self.host}:{self.port})"

    async def disconnect_and_reset(self):
        """Close any existing network connections."""
        self.connected = False
        if hasattr(self, 'reader') and self.reader:
            del self.reader
        if hasattr(self, 'writer') and self.writer:
            self.writer.close()
            del self.writer

    async def connect_with_retry(self):
        """Connect to the given host and start background network processing tasks."""
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
                    f'Connection established to {self.host}:{self.port}'
                    f'{f" after {retries} retries" if retries > 0 else ""}'
                )
                break
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

        self.refresh_count = 0
        self.rx_messages = Queue(maxsize=100)
        self.tx_messages = Queue(maxsize=100)
        self.expected_responses = {}
        self.debug_frames = {
            'all': Queue(maxsize=1000),  # all frames received
            'error': Queue(maxsize=1000),  # frames unable to be decoded to PDUs
            'suspicious': Queue(maxsize=100),  # messages that look suspicious based on known-bad values observed before
            'rejected': Queue(maxsize=100),  # messages that were rejected as Plant updates
        }

    #########################################################################################################
    async def read_incoming_network_data(self):
        """Await incoming data from the network and pass onto the Framer for decoding."""
        data = await self.reader.read(300)
        Metrology.meter('rx-bytes').mark(len(data))

        results: list[BasePDU | None, bytes] = []
        await asyncio.get_event_loop().run_in_executor(
            None, self.framer.process_incoming_data, data, lambda x, y: results.append((x, y))
        )
        for pdu, raw_frame in results:
            await self.debug_frames['all'].put(raw_frame)
            if not pdu:
                _logger.error(f'Unable to decode frame {raw_frame.hex()}')
                await self.debug_frames['error'].put(raw_frame)
                Metrology.meter('rx-invalid-frames').mark()
                continue

            _logger.debug(f'Received {pdu}')
            await self.rx_messages.put(Message(pdu, raw_frame=raw_frame, transceived=datetime.datetime.now()))
            Metrology.meter('rx-pdus').mark()
            if isinstance(pdu, TransparentResponse) and pdu.error:
                _logger.debug(f"Received error {pdu}")
                Metrology.meter('rx-errors').mark()

    async def transmit_next_queued_message(self):
        """Process the next outbound message onto the network."""
        item = await self.tx_messages.get()
        if item.age > datetime.timedelta(seconds=10):
            _logger.warning(f'Queue item >10s old, discarding: {item}')
            item.future.cancel(f'expired, age={item.age}')
            return

        _logger.debug(f'Sending {item.pdu}')
        packet = await asyncio.get_event_loop().run_in_executor(None, self.framer.build_packet, item.pdu)
        item.transceived = datetime.datetime.now()
        item.raw_frame = packet
        await self.track_expected_response(item)
        self.writer.write(packet)
        await asyncio.wait_for(self.writer.drain(), timeout=self.seconds_between_pdu_writes * 2)

        Metrology.meter('tx-pdus').mark()
        Metrology.meter('tx-bytes').mark(len(packet))

    async def enqueue_message_for_sending(self, message: Message) -> None:
        """Helper to enqueue outbound Messages, adjusting for higher ttl if the queue builds."""
        orig_ttl = message.ttl
        message.ttl += self.tx_messages.qsize() * self.seconds_between_pdu_writes
        _logger.debug(f'New message ttl: {message.ttl}s (from {orig_ttl}s)')
        await self.tx_messages.put(message)

    #########################################################################################################
    async def track_expected_response(self, item: Message):
        """Record that an outgoing Request message will generate a matching Response soon."""
        if isinstance(item.pdu, ClientOutgoingMessage):
            expected_response = item.pdu.expected_response()
            if not expected_response:
                return
            shape_hash = expected_response.shape_hash()
            if shape_hash in self.expected_responses:
                existing_expectation = self.expected_responses[shape_hash]
                if existing_expectation.expired:
                    _logger.warning(
                        f'Expiring existing expectation {existing_expectation} age={existing_expectation.age}'
                    )
                    if sys.version_info < (3, 8):
                        existing_expectation.future.cancel()
                    else:
                        existing_expectation.future.cancel('expired')
                else:
                    _logger.warning(
                        f'New {item.pdu} being sent while still awaiting outstanding {expected_response}; '
                        f'age={self.expected_responses[shape_hash].age}'
                    )
                    existing_expectation.future.set_result(item)
            self.expected_responses[shape_hash] = dataclasses.replace(
                item,
                pdu=expected_response,
                provenance=item,
            )
            _logger.debug(f'Recording expected response {shape_hash}/{expected_response} to {item.pdu}')
            Metrology.meter('expected-responses').mark(len(self.expected_responses))

    async def dispatch_next_incoming_message(self):
        """Dispatch the next waiting decoded Message."""
        message = await self.rx_messages.get()
        _logger.debug(f'Dispatching {message}')
        pdu = message.pdu
        self.reconcile_if_expected_message(message)
        if isinstance(message.pdu, HeartbeatRequest):
            response = message.pdu.expected_response()
            _logger.debug(f'Returning {response} to request {message.pdu}')
            await self.enqueue_message_for_sending(
                dataclasses.replace(
                    message,
                    pdu=response,
                    provenance=message,
                    created=datetime.datetime.now(),
                    future=message.future,
                )
            )
        try:
            if hasattr(self, 'plant'):
                self.plant.update(message)
            if message.future.done() or message.future.cancelled():
                _logger.error(f'Message {message} future already complete')
            else:
                _logger.debug(f'Setting future result: {message}')
                message.future.set_result(message)
        except ValueError as e:
            pdu = message.pdu
            if isinstance(pdu, ReadRegistersResponse) and pdu.is_suspicious():
                await self.debug_frames['suspicious'].put(message.raw_frame)
                Metrology.meter('rx-suspicious').mark()
                return

            await self.debug_frames['rejected'].put(message.raw_frame)
            _logger.warning(f'Rejecting update {pdu}: {e}')
            Metrology.meter('rx-invalid').mark()

    def reconcile_if_expected_message(self, item: Message):
        """Complete references to originating messages if it can be found."""
        key = item.pdu.shape_hash()
        if key in self.expected_responses:
            expected_response = self.expected_responses[key]
            _logger.debug(f'Expected response {item} to {expected_response.provenance}')
            item.created = expected_response.created
            item.provenance = expected_response.provenance
            if sys.version_info < (3, 9):
                item.future.cancel()
            else:
                item.future.cancel('Replacing with originating request future')
            item.future = expected_response.future
            Metrology.timer('time-roundtrip').update(int(item.network_roundtrip.total_seconds() * 1000))
            if item.network_roundtrip > datetime.timedelta(seconds=1) and not isinstance(
                item.pdu, ReadRegistersResponse
            ):
                _logger.warning(
                    f'Expected response {item.pdu} arrived after {item.network_roundtrip.total_seconds():.2f}s: '
                    f'req:{item.provenance.transceived.time()} '  # type: ignore[union-attr]
                    f'res:{item.transceived.time()}'  # type: ignore[union-attr]
                )
            _logger.debug(f'Handled expected response: {item}')
            del expected_response
            del self.expected_responses[key]
        else:
            _logger.debug(f'Not an expected response: {key} {item}')

    #########################################################################################################
    async def generate_retries_for_expired_expected_responses(self):
        """Issue retries for expected responses that can be retried."""
        retries = []
        for k, exp in self.expected_responses.copy().items():
            if exp.expired:
                _logger.debug(f'Found expired expected response: {exp}')
                del self.expected_responses[k]
                req = exp.provenance
                if exp.retries_remaining > 0:
                    _logger.warning(f'Retrying {req.pdu}, retries remaining = {req.retries_remaining}')
                    retries.append(
                        dataclasses.replace(
                            req,
                            created=datetime.datetime.now(),
                            transceived=None,
                            retries_remaining=req.retries_remaining - 1,
                        )
                    )
                elif isinstance(exp.pdu, ReadRegistersResponse):
                    _logger.debug(f'Refusing to retry {req.pdu} after {exp.age.total_seconds():.2f}s')
                else:
                    _logger.warning(f'Refusing to retry {req.pdu} after {exp.age.total_seconds():.2f}s')
        if retries:
            _logger.debug(f'Scheduling {len(retries)} retries')
            await asyncio.gather(*[self.enqueue_message_for_sending(m) for m in retries])

    async def dump_queues_to_files(self):
        """Dump internal queues of messages to files for debugging."""
        if self.debug_frames:
            os.makedirs('debug', exist_ok=True)
            for name, queue in self.debug_frames.items():
                if not queue.empty():
                    async with aiofiles.open(f'{os.path.join("debug", name)}_frames.txt', mode='a') as str_file:
                        await str_file.write(f'# {datetime.datetime.now().timestamp()}\n')
                        while not queue.empty():
                            item = await queue.get()
                            await str_file.write(item.hex() + '\n')
