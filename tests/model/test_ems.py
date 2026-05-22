from givenergy_modbus.model.ems import Ems
from givenergy_modbus.model.inverter import Status
from givenergy_modbus.model.meter import MeterStatus
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register_cache import RegisterCache


def _cache(values: dict) -> RegisterCache:
    return RegisterCache(values)


def test_ems_empty():
    ems = Ems.from_register_cache(RegisterCache())
    assert ems.is_valid() is False
    assert all(v is None for v in ems.model_dump().values())


def test_ems_is_valid_when_status_present():
    ems = Ems.from_register_cache(_cache({IR(2040): 1}))
    assert ems.is_valid() is True


def test_plant_configuration():
    cache = _cache(
        {
            HR(2040): 1,  # plant_status = NORMAL
            HR(2041): 2,  # expected_inverter_count
            HR(2042): 1,  # expected_meter_count
            HR(2043): 0,  # expected_car_charger_count
            HR(2071): 5000,  # export_power_limit
        }
    )
    ems = Ems.from_register_cache(cache)
    assert ems.plant_status == Status.NORMAL  # type: ignore[attr-defined]
    assert ems.expected_inverter_count == 2  # type: ignore[attr-defined]
    assert ems.expected_meter_count == 1  # type: ignore[attr-defined]
    assert ems.export_power_limit == 5000  # type: ignore[attr-defined]


def test_charge_and_discharge_slots():
    cache = _cache(
        {
            HR(2053): 700,
            HR(2054): 800,
            HR(2055): 90,
            HR(2044): 1700,
            HR(2045): 2300,
            HR(2046): 20,
        }
    )
    ems = Ems.from_register_cache(cache)
    charge_1 = ems.charge_slot_1  # type: ignore[attr-defined]
    assert charge_1.start.hour == 7
    assert charge_1.start.minute == 0
    assert charge_1.end.hour == 8
    assert charge_1.end.minute == 0
    assert ems.charge_target_1 == 90  # type: ignore[attr-defined]
    discharge_1 = ems.discharge_slot_1  # type: ignore[attr-defined]
    assert discharge_1.start.hour == 17
    assert discharge_1.start.minute == 0
    assert ems.discharge_target_1 == 20  # type: ignore[attr-defined]


def test_meter_status_bitfield():
    # bitfield(val, low, high) uses f"{val:016b}"[low:high+1], index 0 = MSB (bit 15).
    # meter_1 at [0:2]: ONLINE=1=0b01 → bit 14 set → 0x4000
    # meter_2 at [2:4]: OFFLINE=2=0b10 → bit 13 set → 0x2000
    # meter_3 at [4:6]: DISABLED=0 → 0x0000
    packed = 0x4000 | 0x2000  # = 0x6000
    cache = _cache({IR(2043): packed})
    ems = Ems.from_register_cache(cache)
    assert ems.meter_1_status == MeterStatus.ONLINE  # type: ignore[attr-defined]
    assert ems.meter_2_status == MeterStatus.OFFLINE  # type: ignore[attr-defined]
    assert ems.meter_3_status == MeterStatus.DISABLED  # type: ignore[attr-defined]


def test_inverter_status_bitfield():
    # inverter_1 at [0:3]: NORMAL=1=0b001 → bit 13 set → 0x2000
    # inverter_2 at [3:6]: FAULT=3=0b011 → bits 11,10 set → 0x0C00
    packed = 0x2000 | 0x0C00  # = 0x2C00
    cache = _cache({IR(2045): packed})
    ems = Ems.from_register_cache(cache)
    assert ems.inverter_1_status == Status.NORMAL  # type: ignore[attr-defined]
    assert ems.inverter_2_status == Status.FAULT  # type: ignore[attr-defined]


def test_per_inverter_data():
    cache = _cache(
        {
            IR(2044): 2,
            IR(2054): 3500,
            IR(2055): 65536 - 500,  # -500 W (int16)
            IR(2058): 80,
            IR(2059): 65,
            IR(2062): 350,
            IR(2066): 0x4142,
            IR(2067): 0x4344,
            IR(2068): 0x4546,
            IR(2069): 0x4748,
            IR(2070): 0x4900,
        }
    )
    ems = Ems.from_register_cache(cache)
    assert ems.inverter_count == 2  # type: ignore[attr-defined]
    assert ems.inverter_1_power == 3500  # type: ignore[attr-defined]
    assert ems.inverter_2_power == -500  # type: ignore[attr-defined]
    assert ems.inverter_1_soc == 80  # type: ignore[attr-defined]
    assert ems.inverter_2_soc == 65  # type: ignore[attr-defined]
    assert ems.inverter_1_temp == 35.0  # type: ignore[attr-defined]
    assert ems.inverter_1_serial_number == "ABCDEFGHI"  # type: ignore[attr-defined]


def test_plant_power_summary():
    cache = _cache(
        {
            IR(2086): 5000,
            IR(2087): 4800,
            IR(2089): 65536 - 1000,  # -1000 W import (negative = import)
            IR(2090): 65536 - 2000,  # discharging
            IR(2091): 15000,
        }
    )
    ems = Ems.from_register_cache(cache)
    assert ems.calc_load_power == 5000  # type: ignore[attr-defined]
    assert ems.measured_load_power == 4800  # type: ignore[attr-defined]
    assert ems.grid_meter_power == -1000  # type: ignore[attr-defined]
    assert ems.total_battery_power == -2000  # type: ignore[attr-defined]
    assert ems.remaining_battery_wh == 15000  # type: ignore[attr-defined]
