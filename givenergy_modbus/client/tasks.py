import asyncio
import logging
import sys
from asyncio import Task
from typing import Awaitable, Callable, Collection, Dict, Tuple

# from metrology import Metrology
from givenergy_modbus.client import Message

_logger = logging.getLogger(__name__)


class TasksMixin:
    """Helpers for task management."""

    tasks: Dict[str, Task] = {}
    connected: bool

    refresh_count: int
    seconds_between_data_refreshes: float = 5
    full_refresh_interval_count: int = 60  # 5s * 60 = 5m

    number_batteries: int  # provided by ModelMixin
    refresh_data: Callable  # provided by CommandsMixin
    enqueue_message_for_sending: Callable  # provided by DispatchingMixin

    async def reset_tasks(self):
        """Cancel all tracked tasks and reset the index."""
        if self.tasks:
            # stop all background tasks
            _logger.debug(f'Cancelling tasks {", ".join(self.tasks.keys())}')
            tasks = self.tasks.values()
            if sys.version_info < (3, 9):
                [t.cancel() for t in tasks]
            else:
                [t.cancel('reset_tasks') for t in tasks]
            result = await asyncio.gather(*tasks, return_exceptions=True)
            _logger.debug(f'Result: {result}')
        self.tasks = {}

        self.refresh_count = 0

    def run_tasks_forever(self, *funcs: Tuple[Callable[[], Awaitable], float]) -> Collection[Task]:
        """Helper method to wrap coros in tasks, run them in a permanent loop and handle cancellation."""

        async def coro(f: Callable[[], Awaitable], s: float, n: str):
            while self.connected:
                try:
                    await f()
                    await asyncio.sleep(s)
                except asyncio.CancelledError:
                    self.connected = False
                    _logger.debug(f"{n}() cancelled")
                    raise
                except asyncio.TimeoutError:
                    self.connected = False
                    _logger.error(f"{n}() timeout")
                    raise
            _logger.debug(f"{n}() stopped")

        for func, sleep in funcs:
            func_name = func.__name__
            _logger.debug(f"Forever running {func_name}()")
            if sys.version_info < (3, 8):
                self.tasks[func_name] = asyncio.create_task(coro(func, sleep, func_name))
            else:
                self.tasks[func_name] = asyncio.create_task(coro(func, sleep, func_name), name=func_name)
        return self.tasks.values()

    #########################################################################################################
    async def request_data_refresh(self) -> Collection[Message]:
        """Refresh data from the remote system."""
        full_refresh = self.refresh_count % self.full_refresh_interval_count == 0
        _logger.debug(f'Doing refresh: full={full_refresh}, batteries={self.number_batteries}')
        messages = await self.refresh_data(full_refresh, self.number_batteries)
        await asyncio.gather(*[self.enqueue_message_for_sending(m) for m in messages])
        self.refresh_count += 1
        return messages
        #
        # try:
        #     res = await asyncio.gather(*[m.future for m in messages], return_exceptions=True)
        #     failed_messages = [messages[k] for k, v in enumerate(res) if not isinstance(v, Message)]
        #     if failed_messages:
        #         _logger.warning(
        #             f'{len(failed_messages)} failed refresh futures: {" ".join([m.pdu for m in failed_messages])}'
        #         )
        # except asyncio.CancelledError as e:
        #     _logger.warning(f'A future was cancelled', exc_info=e)
