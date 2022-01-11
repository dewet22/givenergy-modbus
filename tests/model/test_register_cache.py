import datetime

import pytest

from givenergy_modbus.model.register import HoldingRegister, InputRegister
from givenergy_modbus.model.register_cache import RegisterCache

from .test_register import HOLDING_REGISTERS, INPUT_REGISTERS


@pytest.fixture
def register_cache() -> RegisterCache:
    """Fixture to provide a loaded Register Cache."""
    i = RegisterCache()
    i.set_registers(HoldingRegister, HOLDING_REGISTERS)
    i.set_registers(InputRegister, INPUT_REGISTERS)
    return i


def test_register_cache():
    """Ensure we can instantiate a RegisterCache and derive correct attributes from it."""
    i = RegisterCache()
    i.set_registers(HoldingRegister, HOLDING_REGISTERS)
    i.set_registers(InputRegister, INPUT_REGISTERS)

    # assert i._registers == HOLDING_REGISTERS
    # assert i._registers == INPUT_REGISTERS

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
        with pytest.raises(KeyError) as e:
            assert getattr(i, k)
        assert e.value.args[0] == k

    assert i.device_type_code == '2001'
    assert i.inverter_module == 198706
    assert i.bms_firmware_version == 3005
    assert i.dsp_firmware_version == 449
    assert i.arm_firmware_version == 449
    assert i.enable_charge_target
    # assert i.system_time == datetime.datetime(2022, 1, 1, 23, 57, 19)

    # time slots are BCD-encoded: 30 == 00:30, 430 == 04:30
    assert i.charge_slot_1_start == datetime.time(0, 30)
    assert i.charge_slot_1_end == datetime.time(4, 30)
    # assert i.charge_slot_1 == (datetime.time(0, 30), datetime.time(4, 30))
    assert i.charge_slot_2_start == datetime.time(0, 0)
    assert i.charge_slot_2_end == datetime.time(0, 4)
    # assert i.charge_slot_2 == (datetime.time(0, 0), datetime.time(0, 4))
    assert i.discharge_slot_1_start == datetime.time(0, 0)
    assert i.discharge_slot_1_end == datetime.time(0, 0)
    # assert i.discharge_slot_1 == (datetime.time(0, 0), datetime.time(0, 0))
    assert i.discharge_slot_2_start == datetime.time(0, 0)
    assert i.discharge_slot_2_end == datetime.time(0, 0)
    # assert i.discharge_slot_2 == (datetime.time(0, 0), datetime.time(0, 0))

    assert i.v_pv1 == 1.4000000000000001
    assert i.v_pv2 == 1.0
    assert i.v_p_bus == 7.0
    assert i.v_n_bus == 0.0
    assert i.v_ac1 == 236.70000000000002

    assert i.e_battery_throughput_h == 0
    assert i.e_battery_throughput_l == 183.20000000000002
    assert i.e_battery_throughput == 183.20000000000002

    assert i.e_pv1_day == 0.4
    assert i.e_pv2_day == 0.5
    assert i.e_grid_export_day_l == 0.6000000000000001

    assert i.battery_percent == 4
    assert i.e_battery_discharge_total == 90.60000000000001
    assert i.e_battery_charge_total == 92.60000000000001

    assert i.v_battery_cell_01 == 3.117
    assert i.v_battery_cell_16 == 3.119
