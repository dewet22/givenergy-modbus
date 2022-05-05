import datetime

import pytest

from givenergy_modbus.model.register import HoldingRegister, InputRegister
from givenergy_modbus.model.register_cache import RegisterCache
from tests.model.test_register import HOLDING_REGISTERS, INPUT_REGISTERS


def test_register_cache(register_cache):
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    expected = {HoldingRegister(k): v for k, v in HOLDING_REGISTERS.items()}
    expected.update({InputRegister(k): v for k, v in INPUT_REGISTERS.items()})
    assert register_cache == expected


def test_attributes(register_cache):
    """Ensure we can instantiate a RegisterCache and derive correct attributes from it."""
    for k in (
        'inverter_serial_number',
        'model',
        'battery_serial_number',
        'system_time',
        'charge_slot_1',
        'charge_slot_2',
        'discharge_slot_1',
        'discharge_slot_2',
    ):
        with pytest.raises(KeyError, match=k):
            getattr(register_cache, k)
        with pytest.raises(KeyError, match=k):
            register_cache[k]

    assert register_cache.device_type_code == '2001'
    assert register_cache.inverter_module == 198706
    assert register_cache.bms_firmware_version == 3005
    assert register_cache.dsp_firmware_version == 449
    assert register_cache.arm_firmware_version == 449
    assert register_cache.enable_charge_target
    # assert register_cache.system_time == datetime.datetime(2022, 1, 1, 23, 57, 19)

    # time slots are BCD-encoded: 30 == 00:30, 430 == 04:30
    assert register_cache.charge_slot_1_start == datetime.time(0, 30)
    assert register_cache.charge_slot_1_end == datetime.time(4, 30)
    # assert register_cache.charge_slot_1 == (datetime.time(0, 30), datetime.time(4, 30))
    assert register_cache.charge_slot_2_start == datetime.time(0, 0)
    assert register_cache.charge_slot_2_end == datetime.time(0, 4)
    # assert register_cache.charge_slot_2 == (datetime.time(0, 0), datetime.time(0, 4))
    assert register_cache.discharge_slot_1_start == datetime.time(0, 0)
    assert register_cache.discharge_slot_1_end == datetime.time(0, 0)
    # assert register_cache.discharge_slot_1 == (datetime.time(0, 0), datetime.time(0, 0))
    assert register_cache.discharge_slot_2_start == datetime.time(0, 0)
    assert register_cache.discharge_slot_2_end == datetime.time(0, 0)
    # assert register_cache.discharge_slot_2 == (datetime.time(0, 0), datetime.time(0, 0))

    assert register_cache.v_pv1 == 1.4
    assert register_cache.v_pv2 == 1.0
    assert register_cache.v_p_bus == 7.0
    assert register_cache.v_n_bus == 0.0
    assert register_cache.v_ac1 == 236.7
    assert register_cache.p_grid_out == -342

    assert register_cache.e_pv1_day == 0.4
    assert register_cache.e_pv2_day == 0.5
    assert register_cache.e_grid_out_total_l == 0.6

    assert register_cache.battery_percent == 4
    assert register_cache.e_battery_discharge_total == 169.6
    assert register_cache.e_battery_charge_total == 174.4

    assert register_cache.e_battery_throughput_total_h == 0
    assert register_cache.e_battery_throughput_total_l == 183.2
    assert register_cache.e_battery_throughput_total == 183.2

    assert register_cache.v_cell_01 == 3.117
    assert register_cache.v_cell_16 == 3.119


def test_to_from_json():
    """Ensure we can serialize and unserialize a RegisterCache to and from JSON."""
    registers = {HoldingRegister(1): 2, InputRegister(3): 4}
    json = RegisterCache(registers=registers).json()
    assert json == '{"HoldingRegister(1)": 2, "InputRegister(3)": 4}'
    rc = RegisterCache.from_json(json)
    assert rc == registers
    assert len(rc._register_lookup_table) > 100  # ensure we have all registers ready to look up


def test_to_from_json_actual_data(json_inverter_daytime_discharging_with_solar_generation):
    """Ensure we can serialize and unserialize a RegisterCache to and from JSON."""
    rc = RegisterCache.from_json(json_inverter_daytime_discharging_with_solar_generation)
    assert len(rc) == 362
    assert len(rc._register_lookup_table) > 100  # ensure we have all registers ready to look up
