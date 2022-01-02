import datetime
from enum import Enum

from ..util import charge_slot_to_time_range
from .register import HoldingRegister, InputRegister


class Model(Enum):
    """Inverter models, as determined from their serial number prefix."""

    CE = 'AC'
    ED = "Gen2"
    SA = "Hybrid"


class Inverter:
    """Models an inverter device."""

    holding_registers: list[int]  # raw register values cache
    input_registers: list[int]  # raw register values cache

    def __init__(self, holding_registers, input_registers):
        """Constructor."""
        self.holding_registers = holding_registers
        self.input_registers = input_registers

        self.inverter_serial_number = (
            self.inverter_serial_number_5
            + self.inverter_serial_number_4
            + self.inverter_serial_number_3
            + self.inverter_serial_number_2
            + self.inverter_serial_number_1
        )
        self.serial_number = self.inverter_serial_number
        self.model = Model[self.serial_number[0:2]].value
        self.battery_serial_number = (
            self.battery_serial_number_5
            + self.battery_serial_number_4
            + self.battery_serial_number_3
            + self.battery_serial_number_2
            + self.battery_serial_number_1
        )
        self.system_time = datetime.datetime(
            year=self.system_time_year + 2000,
            month=self.system_time_month,
            day=self.system_time_day,
            hour=self.system_time_hour,
            minute=self.system_time_minute,
            second=self.system_time_second,
        )
        self.charge_slot_1 = charge_slot_to_time_range(self.charge_slot_1_start, self.charge_slot_1_end)
        self.charge_slot_2 = charge_slot_to_time_range(self.charge_slot_2_start, self.charge_slot_2_end)
        self.discharge_slot_1 = charge_slot_to_time_range(self.discharge_slot_1_start, self.discharge_slot_1_end)
        self.discharge_slot_2 = charge_slot_to_time_range(self.discharge_slot_2_start, self.discharge_slot_2_end)

    def __getattr__(self, item: str):
        """Magic attributes that look up and render register values."""
        item = item.upper()

        for bank, values in {HoldingRegister: self.holding_registers, InputRegister: self.input_registers}.items():
            if item in bank.__members__:
                return bank[item].render(values[bank[item].value])
            if item + '_H' in bank.__members__:
                # double-word composite registers
                # fmt: off
                return (
                    bank[(item + '_H')].render(values[bank[(item + '_H')].value])
                    + bank[(item + '_L')].render(values[bank[(item + '_L')].value])
                )
                # fmt: on
        raise KeyError(item)
