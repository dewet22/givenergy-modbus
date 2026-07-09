from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.register import IR
from givenergy_modbus.model.register_cache import RegisterCache


def _energy_cache(overrides: dict | None = None) -> RegisterCache:
    """A minimal cache with the fields the remaining-energy computed fields read.

    cap_remaining is uint32 centi at IR(88)/IR(89); v_out is uint32 milli at IR(82)/IR(83);
    num_cells is uint16 at IR(97). Defaults give a 16S pack at 47.81 Ah / 52.203 V. An
    override value of None drops that register from the cache (simulating an absent read).
    """
    values = {
        IR(97): 16,  # num_cells
        IR(88): 0,
        IR(89): 4781,  # cap_remaining = 47.81 Ah (centi)
        IR(82): 0,
        IR(83): 52203,  # v_out = 52.203 V (milli)
    }
    values.update(overrides or {})
    return RegisterCache({k: v for k, v in values.items() if v is not None})


def test_remaining_energy_nominal_wh():
    """cap_remaining (Ah) x nominal voltage (num_cells x 3.2 V), in Wh (#374)."""
    b = Battery.from_register_cache(_energy_cache())
    assert b.remaining_energy_nominal_wh == 2448  # 47.81 Ah x 51.2 V


def test_remaining_energy_measured_wh():
    """cap_remaining (Ah) x measured v_out (V), in Wh (#374)."""
    b = Battery.from_register_cache(_energy_cache())
    assert b.remaining_energy_measured_wh == 2496  # 47.81 Ah x 52.203 V


def test_remaining_energy_none_when_cap_remaining_absent():
    b = Battery.from_register_cache(_energy_cache({IR(88): None, IR(89): None}))
    assert b.remaining_energy_nominal_wh is None
    assert b.remaining_energy_measured_wh is None


def test_remaining_energy_nominal_falls_back_to_measured_when_num_cells_absent():
    """A pack that doesn't report num_cells still contributes (via v_out) rather than dropping."""
    b = Battery.from_register_cache(_energy_cache({IR(97): None}))
    assert b.remaining_energy_nominal_wh == 2496  # falls back to measured basis


def test_remaining_energy_nominal_none_when_num_cells_and_v_out_absent():
    b = Battery.from_register_cache(_energy_cache({IR(97): None, IR(82): None, IR(83): None}))
    assert b.remaining_energy_nominal_wh is None


def test_from_registers(register_cache):
    """Ensure we can return a dict view of battery data."""
    assert Battery.from_register_cache(register_cache).model_dump() == {
        "bms_firmware_version": 3005,
        "cap_design": 160.0,
        "cap_design2": 160.0,
        "cap_calibrated": 190.97,
        "e_battery_charge_total": 174.4,
        "e_battery_discharge_total": 169.6,
        "force_discharge_flag": 0,
        "i_battery": 0.0,
        "num_cells": 16,
        "num_cycles": 12,
        "cap_remaining": 18.04,
        "remaining_energy_nominal_wh": 924,
        "remaining_energy_measured_wh": 903,
        "serial_number": "BG1234G567",
        "soc": 9,
        "status_1": 0,
        "status_2": 0,
        "status_3": 6,
        "status_4": 16,
        "status_5": 1,
        "status_6": 0,
        "status_7": 0,
        "t_bms_mosfet": 17.2,
        "t_cells_13_16": 16.1,
        "t_cells_01_04": 17.5,
        "t_cells_05_08": 16.7,
        "t_cells_09_12": 17.1,
        "t_max": 17.4,
        "t_min": 16.7,
        "usb_device_inserted": 8,
        "v_cell_01": 3.117,
        "v_cell_02": 3.124,
        "v_cell_03": 3.129,
        "v_cell_04": 3.129,
        "v_cell_05": 3.125,
        "v_cell_06": 3.13,
        "v_cell_07": 3.122,
        "v_cell_08": 3.116,
        "v_cell_09": 3.111,
        "v_cell_10": 3.105,
        "v_cell_11": 3.119,
        "v_cell_12": 3.134,
        "v_cell_13": 3.146,
        "v_cell_14": 3.116,
        "v_cell_15": 3.135,
        "v_cell_16": 3.119,
        "v_cells_sum": 49.97,
        "v_out": 50.029,
        "warning_1": 0,
        "warning_2": 0,
    }


def test_from_registers_actual_data(register_cache_battery_daytime_discharging):
    """Ensure we can instantiate an instance of battery data from actual registers."""
    assert Battery.from_register_cache(register_cache_battery_daytime_discharging).model_dump() == {
        "bms_firmware_version": 3005,
        "cap_design": 160.0,
        "cap_design2": 160.0,
        "cap_calibrated": 195.13,
        "e_battery_charge_total": 174.4,
        "e_battery_discharge_total": 169.6,
        "force_discharge_flag": 0,
        "i_battery": 0.0,
        "num_cells": 16,
        "num_cycles": 23,
        "cap_remaining": 131.42,
        "remaining_energy_nominal_wh": 6729,
        "remaining_energy_measured_wh": 6810,
        "serial_number": "BG1234G567",
        "soc": 67,
        "status_1": 0,
        "status_2": 0,
        "status_3": 14,
        "status_4": 16,
        "status_5": 1,
        "status_6": 0,
        "status_7": 0,
        "t_bms_mosfet": 17.2,
        "t_cells_13_16": 14.6,
        "t_cells_01_04": 16.8,
        "t_cells_05_08": 15.7,
        "t_cells_09_12": 16.5,
        "t_max": 16.8,
        "t_min": 15.7,
        "usb_device_inserted": 8,
        "v_cell_01": 3.232,
        "v_cell_02": 3.237,
        "v_cell_03": 3.235,
        "v_cell_04": 3.232,
        "v_cell_05": 3.235,
        "v_cell_06": 3.229,
        "v_cell_07": 3.237,
        "v_cell_08": 3.233,
        "v_cell_09": 3.238,
        "v_cell_10": 3.237,
        "v_cell_11": 3.235,
        "v_cell_12": 3.235,
        "v_cell_13": 3.235,
        "v_cell_14": 3.235,
        "v_cell_15": 3.24,
        "v_cell_16": 3.238,
        "v_cells_sum": 51.832,
        "v_out": 51.816,
        "warning_1": 0,
        "warning_2": 0,
    }


def test_from_registers_unsure_data(register_cache_battery_unsure):
    """Test case of battery registers returned for non-existent device address."""
    b = Battery.from_register_cache(register_cache_battery_unsure)
    assert b.serial_number == ""
    assert b.is_valid() is False
    assert b.model_dump() == {
        "bms_firmware_version": 0,
        "cap_calibrated": 0.0,
        "cap_design": 0.0,
        "cap_design2": 0.0,
        "cap_remaining": 0.0,
        "e_battery_charge_total": 0.0,
        "e_battery_discharge_total": 0.0,
        "force_discharge_flag": 0,
        "i_battery": 0.0,
        "num_cells": 0,
        "num_cycles": 0,
        "remaining_energy_nominal_wh": 0,
        "remaining_energy_measured_wh": 0,
        "serial_number": "",
        "soc": 0,
        "status_1": 0,
        "status_2": 0,
        "status_3": 0,
        "status_4": 0,
        "status_5": 0,
        "status_6": 0,
        "status_7": 0,
        "t_bms_mosfet": 25.6,
        "t_cells_01_04": 5.2,
        "t_cells_05_08": 0.0,
        "t_cells_09_12": 0.0,
        "t_cells_13_16": 0.0,
        "t_max": 0.0,
        "t_min": 0.0,
        "usb_device_inserted": 0,
        "v_cell_01": 0.0,
        "v_cell_02": 0.0,
        "v_cell_03": 0.0,
        "v_cell_04": 0.0,
        "v_cell_05": 0.0,
        "v_cell_06": 0.0,
        "v_cell_07": 0.0,
        "v_cell_08": 0.0,
        "v_cell_09": 0.0,
        "v_cell_10": 0.0,
        "v_cell_11": 0.0,
        "v_cell_12": 0.0,
        "v_cell_13": 0.0,
        "v_cell_14": 0.0,
        "v_cell_15": 0.0,
        "v_cell_16": 0.0,
        "v_cells_sum": 0.0,
        "v_out": 0.0,
        "warning_1": 0,
        "warning_2": 0,
    }


def test_i_battery_signed_centi():
    """IR(95) 'Im_Avg' decodes as a signed 0.01 A current (#238).

    A negative charge current and a heavy discharge current, both from the
    field report on real LV hardware, round-trip through int16 + centi scaling.
    """
    charging = Battery.from_register_cache(RegisterCache({IR(95): 65536 - 203}))
    assert charging.i_battery == -2.03

    discharging = Battery.from_register_cache(RegisterCache({IR(95): 4183}))
    assert discharging.i_battery == 41.83


def test_cell_temps_signed_deci():
    """Cell / MOS / min-max temps decode as signed int16 deci (v4.1.6 4.4.1.2).

    A genuine sub-zero reading decodes to its negative value; the empty-slot sentinel
    (0xF556 = -273.0 °C) and a positive reading both round-trip, with the sentinel
    suppressed to None by the -60.0 floor.
    """
    b = Battery.from_register_cache(
        RegisterCache(
            {
                IR(76): 65536 - 55,  # t_cells_01_04 = -5.5 °C (signed)
                IR(77): 231,  # t_cells_05_08 = 23.1 °C
                IR(81): 65536 - 100,  # t_bms_mosfet = -10.0 °C
                IR(103): 0xF556,  # t_max = -273.0 °C empty-slot sentinel → None
                IR(104): 205,  # t_min = 20.5 °C
            }
        )
    )
    assert b.t_cells_01_04 == -5.5
    assert b.t_cells_05_08 == 23.1
    assert b.t_bms_mosfet == -10.0
    assert b.t_max is None
    assert b.t_min == 20.5


def test_energy_totals_deci_kwh():
    """IR(105/106) decode as unsigned 0.1 kWh lifetime energy totals (#238/#241).

    Raw values from the field report on two real LV plants; both packs within a
    plant reported identical values (the counters appear stack-level, mirrored
    into each pack's register block).
    """
    plant_a = Battery.from_register_cache(RegisterCache({IR(105): 62165, IR(106): 61276, IR(107): 0}))
    assert plant_a.e_battery_discharge_total == 6216.5
    assert plant_a.e_battery_charge_total == 6127.6
    assert plant_a.force_discharge_flag == 0

    plant_b = Battery.from_register_cache(RegisterCache({IR(105): 28936, IR(106): 29751}))
    assert plant_b.e_battery_discharge_total == 2893.6
    assert plant_b.e_battery_charge_total == 2975.1


def test_empty():
    """Ensure we can instantiate from empty data."""
    b1 = Battery()
    b2 = Battery.from_register_cache(RegisterCache({}))
    assert b1.serial_number is None
    assert b1.is_valid() is False
    assert b2.serial_number is None
    assert b2.is_valid() is False

    assert (
        b1.model_dump()
        == b2.model_dump()
        == {
            "bms_firmware_version": None,
            "cap_calibrated": None,
            "cap_design": None,
            "cap_design2": None,
            "cap_remaining": None,
            "e_battery_charge_total": None,
            "e_battery_discharge_total": None,
            "force_discharge_flag": None,
            "i_battery": None,
            "num_cells": None,
            "num_cycles": None,
            "remaining_energy_nominal_wh": None,
            "remaining_energy_measured_wh": None,
            "serial_number": None,
            "soc": None,
            "status_1": None,
            "status_2": None,
            "status_3": None,
            "status_4": None,
            "status_5": None,
            "status_6": None,
            "status_7": None,
            "t_bms_mosfet": None,
            "t_cells_01_04": None,
            "t_cells_05_08": None,
            "t_cells_09_12": None,
            "t_cells_13_16": None,
            "t_max": None,
            "t_min": None,
            "usb_device_inserted": None,
            "v_cell_01": None,
            "v_cell_02": None,
            "v_cell_03": None,
            "v_cell_04": None,
            "v_cell_05": None,
            "v_cell_06": None,
            "v_cell_07": None,
            "v_cell_08": None,
            "v_cell_09": None,
            "v_cell_10": None,
            "v_cell_11": None,
            "v_cell_12": None,
            "v_cell_13": None,
            "v_cell_14": None,
            "v_cell_15": None,
            "v_cell_16": None,
            "v_cells_sum": None,
            "v_out": None,
            "warning_1": None,
            "warning_2": None,
        }
    )
