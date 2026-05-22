"""GivEnergy EMS (Energy Management System) data model."""

from pydantic import ConfigDict, create_model

from givenergy_modbus.model.inverter import Status
from givenergy_modbus.model.meter import MeterStatus
from givenergy_modbus.model.register import HR, IR, RegisterGetter
from givenergy_modbus.model.register import Converter as C
from givenergy_modbus.model.register import RegisterDefinition as Def


class EmsRegisterGetter(RegisterGetter):
    """Structured format for EMS plant-level attributes (device address 0x11)."""

    REGISTER_LUT = {
        #
        # Holding Registers 2040–2075 — Plant configuration
        #
        "plant_status": Def(C.uint16, Status, HR(2040)),
        "expected_inverter_count": Def(C.uint16, None, HR(2041)),
        "expected_meter_count": Def(C.uint16, None, HR(2042)),
        "expected_car_charger_count": Def(C.uint16, None, HR(2043)),
        "discharge_slot_1": Def(C.timeslot, None, HR(2044), HR(2045)),
        "discharge_target_1": Def(C.uint16, None, HR(2046)),
        "discharge_slot_2": Def(C.timeslot, None, HR(2047), HR(2048)),
        "discharge_target_2": Def(C.uint16, None, HR(2049)),
        "discharge_slot_3": Def(C.timeslot, None, HR(2050), HR(2051)),
        "discharge_target_3": Def(C.uint16, None, HR(2052)),
        "charge_slot_1": Def(C.timeslot, None, HR(2053), HR(2054)),
        "charge_target_1": Def(C.uint16, None, HR(2055)),
        "charge_slot_2": Def(C.timeslot, None, HR(2056), HR(2057)),
        "charge_target_2": Def(C.uint16, None, HR(2058)),
        "charge_slot_3": Def(C.timeslot, None, HR(2059), HR(2060)),
        "charge_target_3": Def(C.uint16, None, HR(2061)),
        "export_slot_1": Def(C.timeslot, None, HR(2062), HR(2063)),
        "export_target_1": Def(C.uint16, None, HR(2064)),
        "export_slot_2": Def(C.timeslot, None, HR(2065), HR(2066)),
        "export_target_2": Def(C.uint16, None, HR(2067)),
        "export_slot_3": Def(C.timeslot, None, HR(2068), HR(2069)),
        "export_target_3": Def(C.uint16, None, HR(2070)),
        "export_power_limit": Def(C.uint16, None, HR(2071)),
        "car_charge_mode": Def(C.uint16, None, HR(2072)),
        "car_charge_boost": Def(C.uint16, None, HR(2073)),
        "plant_charge_compensation": Def(C.uint16, None, HR(2074)),
        "plant_discharge_compensation": Def(C.uint16, None, HR(2075)),
        #
        # Input Registers 2040–2094 — Plant runtime data
        #
        "ems_status": Def(C.uint16, Status, IR(2040)),
        "meter_count": Def(C.uint16, None, IR(2041)),
        "meter_types": Def(C.uint16, None, IR(2042)),
        # IR(2043) packs 8 meter statuses as 2-bit fields
        "meter_1_status": Def((C.bitfield, 0, 1), MeterStatus, IR(2043)),
        "meter_2_status": Def((C.bitfield, 2, 3), MeterStatus, IR(2043)),
        "meter_3_status": Def((C.bitfield, 4, 5), MeterStatus, IR(2043)),
        "meter_4_status": Def((C.bitfield, 6, 7), MeterStatus, IR(2043)),
        "meter_5_status": Def((C.bitfield, 8, 9), MeterStatus, IR(2043)),
        "meter_6_status": Def((C.bitfield, 10, 11), MeterStatus, IR(2043)),
        "meter_7_status": Def((C.bitfield, 12, 13), MeterStatus, IR(2043)),
        "meter_8_status": Def((C.bitfield, 14, 15), MeterStatus, IR(2043)),
        "inverter_count": Def(C.uint16, None, IR(2044)),
        # IR(2045) packs up to 4 inverter statuses as 3-bit fields
        "inverter_1_status": Def((C.bitfield, 0, 2), Status, IR(2045)),
        "inverter_2_status": Def((C.bitfield, 3, 5), Status, IR(2045)),
        "inverter_3_status": Def((C.bitfield, 6, 8), Status, IR(2045)),
        "inverter_4_status": Def((C.bitfield, 9, 11), Status, IR(2045)),
        "meter_1_power": Def(C.int16, None, IR(2046)),
        "meter_2_power": Def(C.int16, None, IR(2047)),
        "meter_3_power": Def(C.int16, None, IR(2048)),
        "meter_4_power": Def(C.int16, None, IR(2049)),
        "meter_5_power": Def(C.int16, None, IR(2050)),
        "meter_6_power": Def(C.int16, None, IR(2051)),
        "meter_7_power": Def(C.int16, None, IR(2052)),
        "meter_8_power": Def(C.int16, None, IR(2053)),
        "inverter_1_power": Def(C.int16, None, IR(2054)),
        "inverter_2_power": Def(C.int16, None, IR(2055)),
        "inverter_3_power": Def(C.int16, None, IR(2056)),
        "inverter_4_power": Def(C.int16, None, IR(2057)),
        "inverter_1_soc": Def(C.uint16, None, IR(2058)),
        "inverter_2_soc": Def(C.uint16, None, IR(2059)),
        "inverter_3_soc": Def(C.uint16, None, IR(2060)),
        "inverter_4_soc": Def(C.uint16, None, IR(2061)),
        "inverter_1_temp": Def(C.int16, C.deci, IR(2062), min=-60.0, max=150.0),
        "inverter_2_temp": Def(C.int16, C.deci, IR(2063), min=-60.0, max=150.0),
        "inverter_3_temp": Def(C.int16, C.deci, IR(2064), min=-60.0, max=150.0),
        "inverter_4_temp": Def(C.int16, C.deci, IR(2065), min=-60.0, max=150.0),
        "inverter_1_serial_number": Def(C.string, None, IR(2066), IR(2067), IR(2068), IR(2069), IR(2070)),
        "inverter_2_serial_number": Def(C.string, None, IR(2071), IR(2072), IR(2073), IR(2074), IR(2075)),
        "inverter_3_serial_number": Def(C.string, None, IR(2076), IR(2077), IR(2078), IR(2079), IR(2080)),
        "inverter_4_serial_number": Def(C.string, None, IR(2081), IR(2082), IR(2083), IR(2084), IR(2085)),
        "e_active_generation_total": Def(C.uint16, None, IR(18)),
        "calc_load_power": Def(C.uint16, None, IR(2086)),
        "measured_load_power": Def(C.uint16, None, IR(2087)),
        "total_generation_load_power": Def(C.uint16, None, IR(2088)),
        "grid_meter_power": Def(C.int16, None, IR(2089)),
        "total_battery_power": Def(C.int16, None, IR(2090)),
        "remaining_battery_wh": Def(C.uint16, None, IR(2091)),
        "other_battery_power": Def(C.int16, None, IR(2094)),
    }


_EmsBase = create_model(  # type: ignore[call-overload]
    "Ems",
    __config__=ConfigDict(frozen=True, use_enum_values=True),
    **EmsRegisterGetter.to_fields(),
)


class Ems(_EmsBase):  # type: ignore[misc,valid-type]
    """GivEnergy EMS plant-level data (device address 0x11)."""

    @classmethod
    def from_register_cache(cls, register_cache) -> "Ems":
        """Construct an Ems from a RegisterCache."""
        return cls.model_validate(EmsRegisterGetter(register_cache).build())

    def is_valid(self) -> bool:
        """Try to detect if an EMS is present based on its attributes."""
        return self.ems_status is not None  # type: ignore[attr-defined]
