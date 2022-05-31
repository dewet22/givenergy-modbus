import asyncio
import logging
import os
import sys
from asyncio import Future, Queue, Task
from typing import Dict, List

import aiofiles
import arrow

from givenergy_modbus.client import commands
from givenergy_modbus.client.network import NetworkClient
from givenergy_modbus.exceptions import ExceptionBase
from givenergy_modbus.framer import ClientFramer, Framer
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register_cache import RegisterCacheUpdateFailed
from givenergy_modbus.pdu import HeartbeatRequest, TransparentRequest, TransparentResponse, WriteHoldingRegisterResponse

_logger = logging.getLogger(__name__)


class Coordinator:
    """Asynchronous client utilising long-lived connections to a network device."""

    network_client: NetworkClient
    seconds_between_main_loop_restarts: float = 5
    framer: Framer
    expected_responses: 'Dict[int, Future[TransparentResponse]]' = {}
    plant: Plant
    refresh_count: int = 0
    debug_frames: Dict[str, Queue]

    def __init__(self, host: str = 'localhost', port: int = 8899) -> None:
        self.network_client = NetworkClient(host, port)
        self.framer = ClientFramer()
        self.plant = Plant()
        self.debug_frames = {
            'all': Queue(),
            'error': Queue(),
        }

    async def update_setting(self) -> None:
        """Prototype for sending commands."""
        while True:
            await asyncio.sleep(2.7)
            await self.do_requests(commands.set_charge_target(85), timeout=1.0, retries=1)
            await self.do_requests(commands.set_mode_dynamic(), timeout=1.0, retries=1)
            await self.do_requests(commands.reset_discharge_slot_1(), timeout=1.0, retries=1)
            await self.do_requests(commands.reset_discharge_slot_2(), timeout=1.0, retries=1)
            # _logger.info(f'Update result: {[str(r) for r in res]}')
            await asyncio.sleep(46.2)

    async def dump_queues_to_files_loop(self):
        """Dump internal queues of messages to files for debugging."""
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

    async def refresh_plant_loop(
        self, refresh_period: float = 5.0, full_refresh_interval: int = 12, max_batteries: int = 5
    ):
        """Refresh data about the Plant."""
        while True:
            messages = commands.refresh_plant_data(
                self.refresh_count % full_refresh_interval == 0, self.plant.number_batteries, max_batteries
            )
            # tasks = [self.do_request(m, timeout=1.0, retries=1) for m in messages]
            # await asyncio.gather(*tasks, return_exceptions=True)
            await self.do_requests(messages, timeout=1.0, retries=0, return_exceptions=True)
            self.refresh_count += 1
            if self.refresh_count % 100 == 0:
                _logger.info(f'Refresh #{self.refresh_count}')
            await asyncio.sleep(refresh_period)

    async def process_incoming_data_loop(self):
        """Loop for handling incoming data."""
        async for frame in self.network_client.await_frames():
            await self.debug_frames['all'].put(frame)
            async for message in self.framer.decode(frame):
                if isinstance(message, ExceptionBase):
                    _logger.warning(f'Expected response never arrived but resulted in exception: {message}')
                    continue
                if isinstance(message, HeartbeatRequest):
                    await self.network_client.transmit_frame(message.expected_response().encode())
                    continue
                if not isinstance(message, TransparentResponse):
                    _logger.warning(f'Received unexpected message type for a client: {message}')
                    continue
                if isinstance(message, WriteHoldingRegisterResponse):
                    _logger.warning(f'Update: {message}')

                future = self.expected_responses.get(message.shape_hash(), None)
                if future and not future.done():
                    future.set_result(message)
                try:
                    self.plant.update(message)
                except RegisterCacheUpdateFailed as e:
                    await self.debug_frames['error'].put(frame)
                    _logger.debug(f'Ignoring {message}: {e}')

    def do_requests(
        self, requests: List[TransparentRequest], timeout: float, retries: int, return_exceptions: bool = False
    ) -> 'Future[List[TransparentResponse]]':
        """Helper to perform multiple requests in bulk."""
        return asyncio.gather(
            *[self.do_request(m, timeout=timeout, retries=retries) for m in requests],
            return_exceptions=return_exceptions,
        )

    async def do_request(self, request: TransparentRequest, timeout: float, retries: int) -> TransparentResponse:
        """Send a command to the remote, await and return the response."""
        # record the expected response
        expected_response = request.expected_response()
        expected_shape_hash = expected_response.shape_hash()
        existing_response_future = self.expected_responses.get(expected_shape_hash, None)
        if existing_response_future and not existing_response_future.done():
            _logger.debug(f'Cancelling existing in-flight request and replacing: {request}')
            if sys.version_info < (3, 8):
                existing_response_future.cancel()
            else:
                existing_response_future.cancel('replaced')
        response_future: Future[TransparentResponse] = asyncio.get_event_loop().create_future()
        self.expected_responses[expected_shape_hash] = response_future

        raw_frame = request.encode()

        tries = 0
        while tries <= retries:
            if tries > 0:
                _logger.debug(f'Timeout awaiting {expected_response}, attempting retry {tries} of {retries}')
            await self.network_client.transmit_frame(raw_frame)
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

        raise asyncio.TimeoutError(f'Timeout awaiting {expected_response} after {tries} tries at {timeout}s, giving up')

    async def run(self):
        """Run the coordinator in a loop forever."""
        while True:
            async with self.network_client.session():
                tasks = []
                for coro in (
                    self.refresh_plant_loop,
                    # self.chaos,
                    self.process_incoming_data_loop,
                    # self.update_setting,
                    self.dump_queues_to_files_loop,
                ):
                    if sys.version_info < (3, 8):
                        tasks.append(asyncio.create_task(coro()))
                    else:
                        tasks.append(asyncio.create_task(coro(), name=coro.__name__))
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

                for t in done:
                    if sys.version_info < (3, 8):
                        t_name = str(t)
                    else:
                        t_name = t.get_name()
                    if t.cancelled():
                        _logger.info(f'{t_name}: cancelled')
                    elif t.exception():
                        e = t.exception()
                        if isinstance(e, asyncio.CancelledError):
                            _logger.error(f'{t_name} cancelled {e}')
                        if isinstance(e, asyncio.TimeoutError):
                            _logger.error(f'{t_name} timeout {e}')
                        elif isinstance(e, OSError):
                            _logger.error(f'{t_name}: OSError {e}')
                        elif isinstance(e, ExceptionBase):
                            _logger.error(f'{t_name} internal error: {e}', exc_info=e)
                        else:
                            _logger.error(f'{t_name}: {e}', exc_info=e)
                    else:
                        _logger.info(f'{t_name} finished normally: {t}')
                for t in pending:
                    t.cancel()

                for future in self.expected_responses.values():
                    if sys.version_info < (3, 8):
                        future.cancel()
                    else:
                        future.cancel('client restarting')

                _logger.info(f'Restarting client in {self.seconds_between_main_loop_restarts}s')
                await asyncio.sleep(self.seconds_between_main_loop_restarts)
