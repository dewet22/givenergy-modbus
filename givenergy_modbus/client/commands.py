from __future__ import annotations

import asyncio
import datetime
from typing import Sequence

from givenergy_modbus.client import Message, Timeslot
from givenergy_modbus.model.register import HoldingRegister
from givenergy_modbus.pdu.read_registers import ReadHoldingRegistersRequest, ReadInputRegistersRequest
from givenergy_modbus.pdu.transparent import TransparentRequest
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest


class ClientCommandsMixin:
    """Generator methods to create Messages to command the Plant with."""

    @staticmethod
    async def create_request_message(request: TransparentRequest, retries_remaining: int = 0):
        """Helper to create a TransparentRequest Message."""
        request.ensure_valid_state()
        return Message(request, retries_remaining=retries_remaining)

    @staticmethod
    async def create_read_holding_registers_request_message(
        base_register: int, register_count: int = 60, slave_address: int = 0x32
    ) -> Message:
        """Helper to create a ReadHoldingRegistersRequest Message."""
        return await ClientCommandsMixin.create_request_message(
            ReadHoldingRegistersRequest(
                base_register=base_register, register_count=register_count, slave_address=slave_address
            )
        )

    @staticmethod
    async def create_read_input_registers_request_message(
        base_register: int, register_count: int = 60, slave_address: int = 0x32, device_index: int = 0
    ) -> Message:
        """Helper to create a ReadInputRegistersRequest Message."""
        return await ClientCommandsMixin.create_request_message(
            ReadInputRegistersRequest(
                base_register=base_register, register_count=register_count, slave_address=slave_address + device_index
            )
        )

    @staticmethod
    async def create_write_holding_register_request_message(
        register: HoldingRegister, value: int, slave_address: int = 0x11, retries_remaining: int = 2
    ) -> Message:
        """Helper to create a WriteHoldingRegisterRequest Message."""
        return await ClientCommandsMixin.create_request_message(
            WriteHoldingRegisterRequest(register=register, value=value, slave_address=slave_address),
            retries_remaining=retries_remaining,
        )

    #########################################################################################################
    async def refresh_data(self, full_refresh: bool, number_batteries: int = 0) -> Sequence[Message]:
        """Refresh data about the Plant."""
        messages = [
            await self.create_read_input_registers_request_message(base_register=0),
            await self.create_read_input_registers_request_message(base_register=180),
        ]
        if full_refresh:
            messages.extend(
                await asyncio.gather(
                    self.create_read_holding_registers_request_message(base_register=0),
                    self.create_read_holding_registers_request_message(base_register=60),
                    self.create_read_holding_registers_request_message(base_register=120),
                    self.create_read_input_registers_request_message(base_register=120),
                )
            )
            number_batteries = 6

        for i in range(number_batteries):
            messages.append(await self.create_read_input_registers_request_message(base_register=60, device_index=i))

        return messages

    #########################################################################################################
    async def disable_charge_target(self) -> Sequence[Message]:
        """Removes SOC limit and target 100% charging."""
        return await asyncio.gather(
            self.create_write_holding_register_request_message(HoldingRegister.ENABLE_CHARGE_TARGET, False),
            self.create_write_holding_register_request_message(HoldingRegister.CHARGE_TARGET_SOC, 100),
        )

    async def set_charge_target(self, target_soc: int) -> Sequence[Message]:
        """Sets inverter to stop charging when SOC reaches the desired level. Also referred to as "winter mode"."""
        if not 4 <= target_soc <= 100:
            raise ValueError(f'Charge Target SOC ({target_soc}) must be in [4-100]%')
        ret = [await self.enable_charge()]
        if target_soc == 100:
            ret.extend(await self.disable_charge_target())
        else:
            ret.extend(
                await asyncio.gather(
                    self.create_write_holding_register_request_message(HoldingRegister.ENABLE_CHARGE_TARGET, True),
                    self.create_write_holding_register_request_message(HoldingRegister.CHARGE_TARGET_SOC, target_soc),
                )
            )
        return ret

    async def enable_charge(self) -> Message:
        """Enable the battery to charge, depending on the mode and slots set."""
        return await self.create_write_holding_register_request_message(HoldingRegister.ENABLE_CHARGE, True)

    async def disable_charge(self) -> Message:
        """Prevent the battery from charging at all."""
        return await self.create_write_holding_register_request_message(HoldingRegister.ENABLE_CHARGE, False)

    async def enable_discharge(self) -> Message:
        """Enable the battery to discharge, depending on the mode and slots set."""
        return await self.create_write_holding_register_request_message(HoldingRegister.ENABLE_DISCHARGE, True)

    async def disable_discharge(self) -> Message:
        """Prevent the battery from discharging at all."""
        return await self.create_write_holding_register_request_message(HoldingRegister.ENABLE_DISCHARGE, False)

    async def set_discharge_mode_max_power(self) -> Message:
        """Set the battery to discharge at maximum power (export) when discharging."""
        return await self.create_write_holding_register_request_message(HoldingRegister.BATTERY_POWER_MODE, 0)

    async def set_discharge_mode_demand(self) -> Message:
        """Set the battery to discharge to match demand (no export) when discharging."""
        return await self.create_write_holding_register_request_message(HoldingRegister.BATTERY_POWER_MODE, 1)

    async def set_shallow_charge(self, val: int) -> Message:
        """Set the minimum level of charge to keep."""
        # TODO what are valid values? 4-100?
        if not 4 <= val <= 100:
            raise ValueError(f'Minimum SOC / shallow charge ({val}) must be in [4-100]%')
        return await self.create_write_holding_register_request_message(HoldingRegister.BATTERY_SOC_RESERVE, val)

    async def set_battery_charge_limit(self, val: int) -> Message:
        """Set the battery charge power limit as percentage. 50% (2.6 kW) is the maximum for most inverters."""
        if not 0 <= val <= 50:
            raise ValueError(f'Specified Charge Limit ({val}%) is not in [0-50]%')
        return await self.create_write_holding_register_request_message(HoldingRegister.BATTERY_CHARGE_LIMIT, val)

    async def set_battery_discharge_limit(self, val: int) -> Message:
        """Set the battery discharge power limit as percentage. 50% (2.6 kW) is the maximum for most inverters."""
        if not 0 <= val <= 50:
            raise ValueError(f'Specified Discharge Limit ({val}%) is not in [0-50]%')
        return await self.create_write_holding_register_request_message(HoldingRegister.BATTERY_DISCHARGE_LIMIT, val)

    async def set_battery_power_reserve(self, val: int) -> Message:
        """Set the battery power reserve to maintain."""
        # TODO what are valid values?
        if not 4 <= val <= 100:
            raise ValueError(f'Battery power reserve ({val}) must be in [4-100]%')
        return await self.create_write_holding_register_request_message(
            HoldingRegister.BATTERY_DISCHARGE_MIN_POWER_RESERVE, val
        )

    async def _set_charge_slot(self, discharge: bool, idx: int, slot: Timeslot | None) -> Sequence[Message]:
        hr_start, hr_end = (
            HoldingRegister[f'{"DIS" if discharge else ""}CHARGE_SLOT_{idx}_START'],
            HoldingRegister[f'{"DIS" if discharge else ""}CHARGE_SLOT_{idx}_END'],
        )
        if slot:
            return await asyncio.gather(
                self.create_write_holding_register_request_message(hr_start, int(slot.start.strftime('%H%M'))),
                self.create_write_holding_register_request_message(hr_end, int(slot.end.strftime('%H%M'))),
            )
        else:
            return await asyncio.gather(
                self.create_write_holding_register_request_message(hr_start, 0),
                self.create_write_holding_register_request_message(hr_end, 0),
            )

    async def set_charge_slot_1(self, timeslot: Timeslot) -> Sequence[Message]:
        """Set first charge slot start & end times."""
        return await self._set_charge_slot(False, 1, timeslot)

    async def reset_charge_slot_1(self) -> Sequence[Message]:
        """Reset first charge slot to zero/disabled."""
        return await self._set_charge_slot(False, 1, None)

    async def set_charge_slot_2(self, timeslot: Timeslot) -> Sequence[Message]:
        """Set second charge slot start & end times."""
        return await self._set_charge_slot(False, 2, timeslot)

    async def reset_charge_slot_2(self) -> Sequence[Message]:
        """Reset second charge slot to zero/disabled."""
        return await self._set_charge_slot(False, 2, None)

    async def set_discharge_slot_1(self, timeslot: Timeslot) -> Sequence[Message]:
        """Set first discharge slot start & end times."""
        return await self._set_charge_slot(True, 1, timeslot)

    async def reset_discharge_slot_1(self) -> Sequence[Message]:
        """Reset first discharge slot to zero/disabled."""
        return await self._set_charge_slot(True, 1, None)

    async def set_discharge_slot_2(self, timeslot: Timeslot) -> Sequence[Message]:
        """Set second discharge slot start & end times."""
        return await self._set_charge_slot(True, 2, timeslot)

    async def reset_discharge_slot_2(self) -> Sequence[Message]:
        """Reset second discharge slot to zero/disabled."""
        return await self._set_charge_slot(True, 2, None)

    async def set_system_date_time(self, dt: datetime.datetime) -> Sequence[Message]:
        """Set the date & time of the inverter."""
        return await asyncio.gather(
            self.create_write_holding_register_request_message(HoldingRegister.SYSTEM_TIME_YEAR, dt.year - 2000),
            self.create_write_holding_register_request_message(HoldingRegister.SYSTEM_TIME_MONTH, dt.month),
            self.create_write_holding_register_request_message(HoldingRegister.SYSTEM_TIME_DAY, dt.day),
            self.create_write_holding_register_request_message(HoldingRegister.SYSTEM_TIME_HOUR, dt.hour),
            self.create_write_holding_register_request_message(HoldingRegister.SYSTEM_TIME_MINUTE, dt.minute),
            self.create_write_holding_register_request_message(HoldingRegister.SYSTEM_TIME_SECOND, dt.second),
        )

    async def set_mode_dynamic(self) -> Sequence[Message]:
        """Set system to Dynamic / Eco mode.

        This mode is designed to maximise use of solar generation. The battery will charge when
        there is excess power being generated from your solar panels. The battery will store and hold this energy
        until your demand increases. The system will try and balance the use of solar and battery so that you are
        importing and exporting as little energy as possible. This mode is useful if you want to maximise
        self-consumption of renewable generation and minimise the amount of energy drawn from the grid.
        """
        return await asyncio.gather(
            self.set_discharge_mode_demand(),  # r27=1
            self.set_shallow_charge(4),  # r110=4
            self.disable_discharge(),  # r59=0
        )

    async def set_mode_storage(
        self, slot_1: Timeslot = Timeslot.from_repr(1600, 700), slot_2: Timeslot = None, export: bool = False
    ) -> Sequence[Message]:
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
        ret: list[Message] = []
        if export:
            ret.append(await self.set_discharge_mode_max_power())  # r27=0
        else:
            ret.append(await self.set_discharge_mode_demand())  # r27=1
        ret.append(await self.set_shallow_charge(100))  # r110=100
        ret.append(await self.enable_discharge())  # r59=1
        ret.extend(await self.set_discharge_slot_1(slot_1))  # r56=1600, r57=700
        if slot_2:
            ret.extend(await self.set_discharge_slot_2(slot_2))  # r56=1600, r57=700
        else:
            ret.extend(await self.reset_discharge_slot_2())
        return ret
