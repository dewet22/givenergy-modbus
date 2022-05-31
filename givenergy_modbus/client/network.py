import asyncio
import logging
import socket
import sys
from asyncio import Future, Queue, StreamReader, StreamWriter
from contextlib import asynccontextmanager
from typing import AsyncIterator, Tuple

_logger = logging.getLogger(__name__)


class NetworkClient:
    """Coordinator for all network functions."""

    host: str
    port: int

    reader: StreamReader
    writer: StreamWriter

    tx_queue: 'Queue[Tuple[bytes, Future]]'

    def __init__(self, host: str = 'localhost', port: int = 8899) -> None:
        self.host = host
        self.port = port

    @asynccontextmanager
    async def session(
        self,
        timeout: float = 2.0,
        retry_delay: float = 1.0,
        retry_delay_ceil: float = 60.0,
        retry_delay_backoff_factor: float = 1.5,
    ):
        """Connect to the remote host, retrying with backoff if connection fails."""
        retries = 0
        while True:
            try:
                connection = asyncio.open_connection(host=self.host, port=self.port, flags=socket.TCP_NODELAY)
                self.reader, self.writer = await asyncio.wait_for(connection, timeout=timeout)
                break
            except asyncio.TimeoutError:
                reason = f'Timeout establishing connection to {self.host}:{self.port} within {timeout:.1f}s'
            except OSError as e:
                reason = f'Error establishing connection to {self.host}:{self.port}: {e}'

            retries += 1
            _logger.error(f'{reason}. Retry attempt #{retries} follows in {retry_delay:.1f} seconds')
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay_ceil, retry_delay * retry_delay_backoff_factor)

        self.tx_queue = Queue()

        _logger.info(f'Connection established to {self.host}:{self.port} (retries={retries})')
        if sys.version_info < (3, 8):
            producer_task = asyncio.create_task(self.producer())
        else:
            producer_task = asyncio.create_task(self.producer(), name='NetworkClient.producer')

        yield self

        producer_task.cancel()
        if hasattr(self, 'reader') and self.reader:
            self.reader.set_exception(RuntimeError('cancelling'))
            del self.reader
        if hasattr(self, 'writer') and self.writer:
            self.writer.close()
            del self.writer

        if self.tx_queue:
            while not self.tx_queue.empty():
                message, future = self.tx_queue.get_nowait()
                future.cancel()

    async def await_frames(self) -> AsyncIterator[bytes]:
        """Awaits data from the network."""
        while True:
            yield await self.reader.read(300)

    async def producer(self, tx_message_wait: float = 0.25):
        """Producer loop to transmit queued frames with an appropriate delay."""
        while True:
            if self.tx_queue.qsize() > 20:
                _logger.warning(f'tx_queue size = {self.tx_queue.qsize()}')
            message, future = await self.tx_queue.get()
            self.writer.write(message)
            future.set_result(message)
            await asyncio.gather(
                self.writer.drain(),
                asyncio.sleep(tx_message_wait),
            )

    async def transmit_frame(self, frame: bytes):
        """Queue an outgoing frame to be transmitted."""
        future = asyncio.get_event_loop().create_future()
        await self.tx_queue.put((frame, future))
        await future
        _logger.debug(f'Sent {frame.hex()}')
