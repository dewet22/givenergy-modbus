from enum import IntEnum
from typing import ClassVar

from pydantic import ConfigDict, create_model

from givenergy_modbus.model.register import (
    IR,
    RegisterGetter,
    RegisterMetadataMixin,
    is_valid_serial,
)
from givenergy_modbus.model.register import Converter as DT
from givenergy_modbus.model.register import RegisterDefinition as Def


class BatteryRegisterGetter(RegisterGetter):
    """Structured format for all battery attributes."""

    REGISTER_LUT = {
        # Input Registers, block 60-119
        "v_cell_01": Def(DT.milli, None, IR(60), min=1.0, max=5.0),
        "v_cell_02": Def(DT.milli, None, IR(61), min=1.0, max=5.0),
        "v_cell_03": Def(DT.milli, None, IR(62), min=1.0, max=5.0),
        "v_cell_04": Def(DT.milli, None, IR(63), min=1.0, max=5.0),
        "v_cell_05": Def(DT.milli, None, IR(64), min=1.0, max=5.0),
        "v_cell_06": Def(DT.milli, None, IR(65), min=1.0, max=5.0),
        "v_cell_07": Def(DT.milli, None, IR(66), min=1.0, max=5.0),
        "v_cell_08": Def(DT.milli, None, IR(67), min=1.0, max=5.0),
        "v_cell_09": Def(DT.milli, None, IR(68), min=1.0, max=5.0),
        "v_cell_10": Def(DT.milli, None, IR(69), min=1.0, max=5.0),
        "v_cell_11": Def(DT.milli, None, IR(70), min=1.0, max=5.0),
        "v_cell_12": Def(DT.milli, None, IR(71), min=1.0, max=5.0),
        "v_cell_13": Def(DT.milli, None, IR(72), min=1.0, max=5.0),
        "v_cell_14": Def(DT.milli, None, IR(73), min=1.0, max=5.0),
        "v_cell_15": Def(DT.milli, None, IR(74), min=1.0, max=5.0),
        "v_cell_16": Def(DT.milli, None, IR(75), min=1.0, max=5.0),
        # Temperature `min=-60.0` also (incidentally) rejects the absent-battery-slot sentinel.
        # The BMS firmware stores temperatures internally with a `+2730` bias and subtracts
        # 2730 on TX, so an empty slot (internal `0`) emits `0xF556 = -2730 = -273.0 °C`.
        # See open-giv/bms-analysis docs/03 ("Absent device pattern") for the firmware path.
        # If you tighten these bounds, keep the lower bound below `-273.0` or add explicit
        # sentinel rejection — otherwise empty-slot frames will start reaching consumers.
        "t_cells_01_04": Def(DT.deci, None, IR(76), min=-60.0, max=150.0),
        "t_cells_05_08": Def(DT.deci, None, IR(77), min=-60.0, max=150.0),
        "t_cells_09_12": Def(DT.deci, None, IR(78), min=-60.0, max=150.0),
        "t_cells_13_16": Def(DT.deci, None, IR(79), min=-60.0, max=150.0),
        "v_cells_sum": Def(DT.milli, None, IR(80), min=16.0, max=80.0),
        "t_bms_mosfet": Def(DT.deci, None, IR(81), min=-60.0, max=150.0),
        "v_out": Def(DT.uint32, DT.milli, IR(82), IR(83), min=16.0, max=80.0),
        "cap_calibrated": Def(DT.uint32, DT.centi, IR(84), IR(85)),
        "cap_design": Def(DT.uint32, DT.centi, IR(86), IR(87)),
        "cap_remaining": Def(DT.uint32, DT.centi, IR(88), IR(89)),
        "status_1": Def((DT.duint8, 0), None, IR(90)),
        "status_2": Def((DT.duint8, 1), None, IR(90)),
        "status_3": Def((DT.duint8, 0), None, IR(91)),
        "status_4": Def((DT.duint8, 1), None, IR(91)),
        "status_5": Def((DT.duint8, 0), None, IR(92)),
        "status_6": Def((DT.duint8, 1), None, IR(92)),
        "status_7": Def((DT.duint8, 0), None, IR(93)),
        "warning_1": Def((DT.duint8, 0), None, IR(94)),
        "warning_2": Def((DT.duint8, 1), None, IR(94)),
        # IR(95) unused
        "num_cycles": Def(DT.uint16, None, IR(96)),
        "num_cells": Def(DT.uint16, None, IR(97)),
        "bms_firmware_version": Def(DT.uint16, None, IR(98)),
        # IR(99) unused
        "soc": Def(DT.uint16, None, IR(100), min=0, max=100),
        "cap_design2": Def(DT.uint32, DT.centi, IR(101), IR(102)),
        "t_max": Def(DT.deci, None, IR(103), min=-60.0, max=150.0),
        "t_min": Def(DT.deci, None, IR(104), min=-60.0, max=150.0),
        # IR(105-109) unused
        "serial_number": Def(DT.serial, None, IR(110), IR(111), IR(112), IR(113), IR(114)),
        # IR(115) meaning unverified — manufacturer specs only document 0 and 8 (originally
        # decoded as a UsbDevice enum), but observed values outside that set (e.g. 11 on
        # D0.449-A0.449) caused decode failures. Exposed as a raw uint16 until documented.
        "usb_device_inserted": Def(DT.uint16, None, IR(115)),
        # IR(116-119) unused
    }


_BatteryBase = create_model(  # type: ignore[call-overload]
    "Battery",
    __config__=ConfigDict(frozen=True, use_enum_values=True),
    **BatteryRegisterGetter.to_fields(),
)


class Battery(_BatteryBase, RegisterMetadataMixin):  # type: ignore[misc,valid-type]
    """GivEnergy battery data model."""

    REGISTER_GETTER: ClassVar[type[RegisterGetter]] = BatteryRegisterGetter

    @classmethod
    def from_register_cache(cls, register_cache) -> "Battery":
        """Construct a Battery from a RegisterCache."""
        return cls.model_validate(BatteryRegisterGetter(register_cache).build())

    def is_valid(self) -> bool:
        """Try to detect if a battery exists based on its attributes."""
        return is_valid_serial(self.serial_number)  # type: ignore[attr-defined]


class State(IntEnum):
    """Battery charge/discharge state."""

    STATIC = 0
    CHARGE = 1
    DISCHARGE = 2

    @classmethod
    def _missing_(cls, value):
        return cls.STATIC


class ExportPriority(IntEnum):
    """Dispatch priority for surplus power on AC-coupled inverters.

    Confirmed writable on Model.AC via direct portal observations (hass#52):
    HR(311) was written with values 0/1/2 while the portal's "Export Priority"
    control was cycled through its three options.
    """

    BATTERY_FIRST = 0
    GRID_FIRST = 1
    LOAD_FIRST = 2


class BatteryPauseMode(IntEnum):
    """Battery pause mode."""

    DISABLED = 0
    PAUSE_CHARGE = 1
    PAUSE_DISCHARGE = 2
    PAUSE_BOTH = 3

    @classmethod
    def _missing_(cls, value):
        return cls.DISABLED


class BatteryMaintenance(IntEnum):
    """Battery maintenance mode."""

    OFF = 0
    DISCHARGE = 1
    CHARGE = 2
    STANDBY = 3

    @classmethod
    def _missing_(cls, value):
        return cls.OFF
