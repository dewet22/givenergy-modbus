import asyncio
import logging
import os
import socket
from asyncio import Future, Queue, StreamReader, StreamWriter, Task
from typing import AsyncIterator, Callable, Dict, List

import aiofiles
import arrow

from givenergy_modbus.client import commands
from givenergy_modbus.exceptions import CommunicationError, ExceptionBase
from givenergy_modbus.framer import ClientFramer, Framer
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register_cache import RegisterCacheUpdateFailed
from givenergy_modbus.pdu import HeartbeatRequest, TransparentRequest, TransparentResponse, WriteHoldingRegisterResponse

_logger = logging.getLogger(__name__)


class Client:
    """Asynchronous client utilising long-lived connections to a network device."""

    framer: Framer
    expected_responses: 'Dict[int, Future[TransparentResponse]]' = {}
    plant: Plant
    refresh_count: int = 0
    debug_frames: Dict[str, Queue]
    reader: StreamReader
    writer: StreamWriter
    network_consumer_task: Task
    network_producer_task: Task

    tx_queue: 'Queue[tuple[bytes, Future]]'

    def __init__(self, host: str, port: int, connect_timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.framer = ClientFramer()
        self.plant = Plant()
        self.tx_queue = Queue()
        self.debug_frames = {
            'all': Queue(maxsize=1000),
            'error': Queue(maxsize=1000),
        }

    async def connect(self) -> None:
        """Connect to the remote host and start background tasks."""
        try:
            connection = asyncio.open_connection(host=self.host, port=self.port, flags=socket.TCP_NODELAY)
            self.reader, self.writer = await asyncio.wait_for(connection, timeout=self.connect_timeout)
        except OSError as e:
            raise CommunicationError(f'Error connecting to {self.host}:{self.port}') from e
        self.network_consumer_task = asyncio.create_task(self._task_network_consumer(), name='network_consumer')
        self.network_producer_task = asyncio.create_task(self._task_network_producer(), name='network_producer')
        # asyncio.create_task(self._task_dump_queues_to_files(), name='dump_queues_to_files'),
        _logger.info(f'Connection established to {self.host}:{self.port}')

    async def close(self):
        """Disconnect from the remote host and clean up tasks and queues."""
        if self.tx_queue:
            while not self.tx_queue.empty():
                message, future = self.tx_queue.get_nowait()
                future.cancel()
        self.network_producer_task.cancel()
        if hasattr(self, 'writer') and self.writer:
            self.writer.close()
            del self.writer

        self.network_consumer_task.cancel()
        if hasattr(self, 'reader') and self.reader:
            self.reader.set_exception(RuntimeError('cancelling'))
            del self.reader

    async def refresh_plant(
        self, full_refresh: bool = True, max_batteries: int = 5, timeout: float = 1.0, retries: int = 0
    ):
        """Refresh data about the Plant."""
        reqs = commands.refresh_plant_data(full_refresh, self.plant.number_batteries, max_batteries)
        await self.execute(reqs, timeout=timeout, retries=retries)
        return self.plant

    async def watch_plant(
        self,
        handler: Callable,
        refresh_period: float = 5.0,
        full_refresh_interval: int = 12,
        max_batteries: int = 5,
        timeout: float = 1.0,
        retries: int = 0,
    ):
        """Refresh data about the Plant."""
        await self.connect()
        while True:
            reqs = commands.refresh_plant_data(
                self.refresh_count % full_refresh_interval == 0,
                self.plant.number_batteries,
                max_batteries=max_batteries,
            )
            await self.execute(reqs, timeout=timeout, retries=retries, return_exceptions=True)
            self.refresh_count += 1
            if self.refresh_count % 100 == 0:
                _logger.info(f'Refresh #{self.refresh_count}')
            handler(self.plant)
            await asyncio.sleep(refresh_period)

    async def one_shot_command(self, requests: List[TransparentRequest], timeout=1.0, retries=0) -> None:
        """Run a single set of requests and return."""
        await self.execute(requests, timeout=timeout, retries=retries)

    async def await_frames(self) -> AsyncIterator[bytes]:
        """Await data from the network."""
        while True:
            yield await self.reader.read(300)

    async def _enqueue_frame(self, frame: bytes):
        """Queue and await an outgoing frame to be transmitted."""
        future = asyncio.get_event_loop().create_future()
        await self.tx_queue.put((frame, future))
        await future
        _logger.debug(f'Sent {frame.hex()}')

    async def _task_network_consumer(self):
        """Task for orchestrating incoming data."""
        async for frame in self.await_frames():
            await self.debug_frames['all'].put(frame)
            async for message in self.framer.decode(frame):
                if isinstance(message, ExceptionBase):
                    _logger.warning(f'Expected response never arrived but resulted in exception: {message}')
                    continue
                if isinstance(message, HeartbeatRequest):
                    await self._enqueue_frame(message.expected_response().encode())
                    continue
                if not isinstance(message, TransparentResponse):
                    _logger.warning(f'Received unexpected message type for a client: {message}')
                    continue
                if isinstance(message, WriteHoldingRegisterResponse):
                    if message.error:
                        _logger.warning(f'{message}')
                    else:
                        _logger.info(f'{message}')

                future = self.expected_responses.get(message.shape_hash(), None)
                if future and not future.done():
                    future.set_result(message)
                try:
                    self.plant.update(message)
                except RegisterCacheUpdateFailed as e:
                    await self.debug_frames['error'].put(frame)
                    _logger.debug(f'Ignoring {message}: {e}')

    async def _task_network_producer(self, tx_message_wait: float = 0.25):
        """Producer loop to transmit queued frames with an appropriate delay."""
        while True:
            message, future = await self.tx_queue.get()
            self.writer.write(message)
            future.set_result(message)
            await asyncio.gather(
                self.writer.drain(),
                asyncio.sleep(tx_message_wait),
            )
            if self.tx_queue.qsize() > 20:
                _logger.warning(f'tx_queue size = {self.tx_queue.qsize()}')

    async def _task_dump_queues_to_files(self):
        """Task to periodically dump debug message frames to disk for debugging."""
        while True:
            await asyncio.sleep(30)
            if self.debug_frames:
                os.makedirs('debug', exist_ok=True)
                for name, queue in self.debug_frames.items():
                    if not queue.empty():
                        async with aiofiles.open(f'{os.path.join("debug", name)}_frames.txt', mode='a') as str_file:
                            await str_file.write(f'# {arrow.utcnow().timestamp()}\n')
                            while not queue.empty():
                                item = await queue.get()
                                await str_file.write(item.hex() + '\n')

    def execute(
        self, requests: List[TransparentRequest], timeout: float, retries: int, return_exceptions: bool = False
    ) -> 'Future[List[TransparentResponse]]':
        """Helper to perform multiple requests in bulk."""
        return asyncio.gather(
            *[self._execute_request(m, timeout=timeout, retries=retries) for m in requests],
            return_exceptions=return_exceptions,
        )

    async def _execute_request(self, request: TransparentRequest, timeout: float, retries: int) -> TransparentResponse:
        """Send a request to the remote, await and return the response."""
        # mark the expected response
        expected_response = request.expected_response()
        expected_shape_hash = expected_response.shape_hash()
        existing_response_future = self.expected_responses.get(expected_shape_hash, None)
        if existing_response_future and not existing_response_future.done():
            _logger.debug(f'Cancelling existing in-flight request and replacing: {request}')
            existing_response_future.cancel()
        response_future: Future[TransparentResponse] = asyncio.get_event_loop().create_future()
        self.expected_responses[expected_shape_hash] = response_future

        raw_frame = request.encode()

        tries = 0
        while tries <= retries:
            if tries > 0:
                _logger.debug(f'Timeout awaiting {expected_response}, attempting retry {tries} of {retries}')
            await self._enqueue_frame(raw_frame)
            timeout_task: Task = asyncio.create_task(asyncio.sleep(timeout))
            # either we get a response, or time out while waiting for one
            await asyncio.wait((response_future, timeout_task), return_when=asyncio.FIRST_COMPLETED)
            if response_future.done():
                timeout_task.cancel()
                response = response_future.result()
                if tries > 0:
                    _logger.debug(f'Received {response} after {tries} tries')
                if response.error:
                    _logger.error(f'Received error response, retrying: {response}')
                else:
                    return response
            tries += 1

        _logger.error(f'Timeout awaiting {expected_response} after {tries} tries at {timeout}s, giving up')
        raise asyncio.TimeoutError()

    # async def run_commands(self, commands: dict):
    #     """Run the coordinator in a loop forever."""
    #     async with self.session():
    #         tasks = []
    #         for name, command in commands.items():
    #             _logger.info(f'{name}: {command}')
    #             tasks.append(asyncio.create_task(command, name=name))
    #
    #         done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
    #
    #         for t in done:
    #             t_name = t.get_name()
    #             if t.cancelled():
    #                 _logger.info(f'{t_name}: cancelled')
    #             elif t.exception():
    #                 e = t.exception()
    #                 if isinstance(e, asyncio.CancelledError):
    #                     _logger.error(f'{t_name} cancelled {e}')
    #                 if isinstance(e, asyncio.TimeoutError):
    #                     _logger.error(f'{t_name} timeout {e}')
    #                 elif isinstance(e, OSError):
    #                     _logger.error(f'{t_name}: OSError {e}')
    #                 elif isinstance(e, ExceptionBase):
    #                     _logger.error(f'{t_name} internal error: {e}', exc_info=e)
    #                 else:
    #                     _logger.error(f'{t_name}: {e}', exc_info=e)
    #             else:
    #                 _logger.info(f'{t_name} finished normally: {t}')
    #         for t in pending:
    #             t.cancel()
    #
    #         for future in self.expected_responses.values():
    #             future.cancel('client restarting')
    #
    # async def run(self):
    #     """Run the coordinator in a loop forever."""
    #     while True:
    #         async with self.network_client.session():
    #             tasks = []
    #             for coro in (
    #                 self.refresh_plant,
    #                 # self.chaos,
    #                 self.process_incoming_data_loop,
    #                 # self.update_setting,
    #                 self.dump_queues_to_files_loop,
    #             ):
    #                 tasks.append(asyncio.create_task(coro(), name=coro.__name__))
    #             done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    #
    #             for t in done:
    #                 t_name = t.get_name()
    #                 if t.cancelled():
    #                     _logger.info(f'{t_name}: cancelled')
    #                 elif t.exception():
    #                     e = t.exception()
    #                     if isinstance(e, asyncio.CancelledError):
    #                         _logger.error(f'{t_name} cancelled {e}')
    #                     if isinstance(e, asyncio.TimeoutError):
    #                         _logger.error(f'{t_name} timeout {e}')
    #                     elif isinstance(e, OSError):
    #                         _logger.error(f'{t_name}: OSError {e}')
    #                     elif isinstance(e, ExceptionBase):
    #                         _logger.error(f'{t_name} internal error: {e}', exc_info=e)
    #                     else:
    #                         _logger.error(f'{t_name}: {e}', exc_info=e)
    #                 else:
    #                     _logger.info(f'{t_name} finished normally: {t}')
    #             for t in pending:
    #                 t.cancel()
    #
    #             for future in self.expected_responses.values():
    #                 future.cancel('client restarting')
    #
    #             _logger.info(f'Restarting client in {self.seconds_between_main_loop_restarts}s')
    #             await asyncio.sleep(self.seconds_between_main_loop_restarts)
