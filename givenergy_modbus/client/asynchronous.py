import asyncio
import logging
from typing import Collection

from givenergy_modbus.client import Message
from givenergy_modbus.client.commands import ClientCommandsMixin
from givenergy_modbus.client.dispatch import DispatchingMixin
from givenergy_modbus.client.model import ModelMixin
from givenergy_modbus.client.tasks import TasksMixin

_logger = logging.getLogger(__name__)


class Client(DispatchingMixin, TasksMixin, ClientCommandsMixin, ModelMixin):
    """Asynchronous client utilising long-lived connections to a network device."""

    seconds_between_main_loop_restarts: float = 5

    async def request_data_refresh(self) -> Collection[Message]:
        """Refresh data from the remote system."""
        full_refresh = self.refresh_count % self.full_refresh_interval_count == 0
        # _logger.info(f'Doing refresh: full={full_refresh}, batteries={self.number_batteries}')
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

    async def update_setting(self) -> None:
        """Prototype for sending commands."""
        messages = await self.set_charge_target(85)
        await asyncio.gather(*[self.enqueue_message_for_sending(m) for m in messages])

        try:
            _logger.info(f'Awaiting {len(messages)} futures')
            res = await asyncio.gather(*[m.future for m in messages], return_exceptions=True)
            _logger.info('Done')
            failed_messages = [messages[k] for k, v in enumerate(res) if not isinstance(v, Message)]
            if failed_messages:
                _logger.warning(f'{len(failed_messages)}/{len(messages)} failed futures:')
                for m in failed_messages:
                    _logger.warning(f'{m.pdu} {m}')
        except asyncio.CancelledError as e:
            _logger.warning('Task cancelled?', exc_info=e)

    async def health_check(self):
        """Proto healthcheck function."""
        all_tasks = asyncio.all_tasks()
        if len(all_tasks) < 5 or len(all_tasks) > 30:
            tasks = "\n".join([f"    {t.get_name():30} {t._state:10} {t.get_coro()}" for t in all_tasks])
            _logger.warning(f'{len(all_tasks)} tasks scheduled:\n{tasks}')
        if self.tx_messages.qsize() > 10:
            _logger.warning(f'TX message queue len={self.tx_messages.qsize()}')
        if self.rx_messages.qsize() > 10:
            _logger.warning(f'RX message queue len={self.rx_messages.qsize()}')

    async def loop_forever(self):
        """Main async client loop."""
        while True:
            await self.connect_with_retry()
            await self.reset_tasks()
            tasks = self.run_tasks_forever(
                (self.read_incoming_network_data, 0, 60),
                (self.transmit_next_queued_message, self.seconds_between_pdu_writes, 60),
                (self.dispatch_next_incoming_message, 0, 30),
                (self.generate_retries_for_expired_expected_responses, 0.2, 1),
                (self.request_data_refresh, self.seconds_between_data_refreshes, 10),
                (self.dump_queues_to_files, 60, 1),
                (self.health_check, 10, 1),
                (self.log_stats, 900, 1),
                # (self.update_setting, 30, 10),
            )

            try:
                await asyncio.gather(*tasks)
                _logger.info('All tasks completed, restarting')
            except (OSError, asyncio.exceptions.TimeoutError) as e:
                _logger.exception(
                    f'{type(e).__name__}{f": {e}" if str(e) else ""}, '
                    f'restarting in {self.seconds_between_main_loop_restarts:.1f}s',
                    exc_info=e,
                )

            await self.disconnect_and_reset()
            await asyncio.sleep(self.seconds_between_main_loop_restarts)
