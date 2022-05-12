import asyncio
import logging
from typing import List

from givenergy_modbus.client import Message
from givenergy_modbus.client.commands import CommandsMixin
from givenergy_modbus.client.dispatch import DispatchingMixin
from givenergy_modbus.client.model import ModelMixin
from givenergy_modbus.client.tasks import TasksMixin

_logger = logging.getLogger(__name__)


class Client(DispatchingMixin, TasksMixin, CommandsMixin, ModelMixin):
    """Asynchronous client utilising long-lived connections to a network device."""

    seconds_between_main_loop_restarts: float = 5

    async def update_setting(self) -> None:
        """Prototype for sending commands."""
        messages: List[Message] = []
        messages.extend(await self.set_charge_target(85))
        messages.extend(await self.set_mode_dynamic())

        await asyncio.gather(*[self.enqueue_message_for_sending(m) for m in messages])

        try:
            _logger.debug(f'Awaiting {len(messages)} futures')
            res = await asyncio.gather(*[m.future for m in messages], return_exceptions=True)
            _logger.debug('Done')
            failed_messages = [messages[k] for k, v in enumerate(res) if not isinstance(v, Message)]
            if failed_messages:
                _logger.warning(
                    f'{len(failed_messages)}/{len(messages)} failed futures: '
                    f'{" ".join([str(m.pdu) for m in failed_messages])}'
                )
        except asyncio.CancelledError as e:
            _logger.warning(f'Future cancelled? {e}')

    async def health_check(self):
        """Proto healthcheck function."""
        if self.refresh_count < 2:
            return
        all_tasks = asyncio.all_tasks()
        if len(all_tasks) < 5 or len(all_tasks) > 20:
            tasks = "\n".join([f"    {t.get_name():30} {t._state:10} {t.get_coro()}" for t in all_tasks])
            _logger.warning(f'{len(all_tasks)} tasks scheduled:\n{tasks}')
        if self.tx_messages.qsize() > 12:
            _logger.warning(f'TX message queue len={self.tx_messages.qsize()}')
        if self.rx_messages.qsize() > 12:
            _logger.warning(f'RX message queue len={self.rx_messages.qsize()}')

    def start_background_tasks(self):
        """Start and track common background tasks of the client."""
        self.run_tasks_forever(
            (self.read_incoming_network_data, 0),
            (self.transmit_next_queued_message, self.seconds_between_pdu_writes),
            (self.dispatch_next_incoming_message, 0),
            (self.dump_queues_to_files, 60),
            (self.generate_retries_for_expired_expected_responses, 0.2),
        )

    async def gather_tasks(self):
        """Return a gathering of the client's tracked tasks."""
        await asyncio.gather(*self.tasks.values())

    async def loop_forever(self):
        """Main async client loop."""
        while True:
            await self.connect_with_retry()
            await self.reset_tasks()
            self.start_background_tasks()
            self.run_tasks_forever(
                (self.request_data_refresh, self.seconds_between_data_refreshes),
                (self.health_check, 10),
                (self.update_setting, 300),
            )

            try:
                await self.gather_tasks()
                _logger.info('All tasks completed, restarting')
            except (OSError, asyncio.exceptions.TimeoutError) as e:
                _logger.exception(
                    f'{type(e).__name__}{f": {e}" if str(e) else ""}, '
                    f'restarting in {self.seconds_between_main_loop_restarts:.1f}s',
                )
            except Exception as e:
                _logger.exception(
                    f'{type(e).__name__}{f": {e}" if str(e) else ""}, '
                    f'restarting in {self.seconds_between_main_loop_restarts:.1f}s',
                    exc_info=e,
                )

            await self.disconnect_and_reset()
            await self.dump_queues_to_files()
            await asyncio.sleep(self.seconds_between_main_loop_restarts)
