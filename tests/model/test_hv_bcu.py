import pytest

from givenergy_modbus.model.hv_bcu import Bcu, BcuStatus, Bmu, _bcu_status_from
from givenergy_modbus.model.register import IR
from givenergy_modbus.model.register_cache import RegisterCache


def _cache(values: dict) -> RegisterCache:
    return RegisterCache(values)


# ---------------------------------------------------------------------------
# BCU tests
# ---------------------------------------------------------------------------


def test_bcu_empty():
    bcu = Bcu.from_register_cache(RegisterCache())
    assert bcu.is_valid() is False
    assert bcu.battery_voltage is None  # type: ignore[attr-defined]


def test_bcu_from_synthetic_registers():
    cache = _cache(
        {
            IR(60): 0x4741,  # 'G','A'
            IR(61): 0x3030,  # '0','0'
            IR(62): 0x0000,
            IR(63): 0x0005,  # version suffix 5 → "GA000005"
            IR(64): 4,  # number_of_modules
            IR(65): 24,  # cells_per_module
            IR(70): 1,  # status
            IR(73): 4800,  # battery_voltage = 480.0 V
            IR(74): 4780,  # load_voltage = 478.0 V
            IR(76): 65536 - 500,  # battery_current = -50.0 A (int16 deci)
            IR(79): 5000,  # battery_power = 5.0 W (milli)
            IR(80): (90 << 8) | 85,  # soc_max=90, soc_min=85
            IR(81): 98,  # battery_soh
            IR(82): 0,
            IR(83): 1000,  # charge_energy_total = 100.0 kWh
            IR(98): 2000,  # nominal_capacity_ah = 200.0 Ah
            IR(99): 1800,  # remaining_capacity_ah = 180.0 Ah
            IR(100): 120,  # number_of_cycles = 12.0
            # Diagnostic tail (IR(107)–IR(119)) — raw read-back
            IR(107): 7,  # fan_fault_code
            IR(113): 1,  # self_check_status
            IR(114): 0x0001,  # pack_warning_status H
            IR(115): 0x0002,  # pack_warning_status L → 0x00010002
            IR(118): 0x0000,
            IR(119): 0x0010,  # pack_fault_status → 0x00000010
        }
    )
    bcu = Bcu.from_register_cache(cache)
    assert bcu.is_valid() is True
    assert bcu.pack_software_version == "GA000005"  # type: ignore[attr-defined]
    assert bcu.number_of_modules == 4  # type: ignore[attr-defined]
    assert bcu.cells_per_module == 24  # type: ignore[attr-defined]
    assert bcu.battery_voltage == 480.0  # type: ignore[attr-defined]
    assert bcu.battery_current == -50.0  # type: ignore[attr-defined]
    assert bcu.battery_soc_max == 90  # type: ignore[attr-defined]
    assert bcu.battery_soc_min == 85  # type: ignore[attr-defined]
    assert bcu.battery_soh == 98  # type: ignore[attr-defined]
    assert bcu.charge_energy_total == 100.0  # type: ignore[attr-defined]
    assert bcu.battery_nominal_capacity_ah == 200.0  # type: ignore[attr-defined]
    assert bcu.remaining_battery_capacity_ah == 180.0  # type: ignore[attr-defined]
    assert bcu.number_of_cycles == pytest.approx(12.0)  # type: ignore[attr-defined]
    # IR(70) = 1 → PRECHARGING; raw status stays available alongside the typed label
    assert bcu.status == 1  # type: ignore[attr-defined]
    assert bcu.status_label is BcuStatus.PRECHARGING  # type: ignore[attr-defined]
    # Diagnostic read-back (raw, un-decoded)
    assert bcu.fan_fault_code == 7  # type: ignore[attr-defined]
    assert bcu.self_check_status == 1  # type: ignore[attr-defined]
    assert bcu.pack_warning_status == 0x00010002  # type: ignore[attr-defined]
    assert bcu.pack_fault_status == 0x00000010  # type: ignore[attr-defined]


def test_bcu_is_valid_empty_version_string():
    cache = _cache({IR(60): 0, IR(61): 0, IR(62): 0, IR(63): 0})
    bcu = Bcu.from_register_cache(cache)
    assert bcu.is_valid() is False


def test_bcu_status_label_decode():
    # Every named BCU_STATUS code maps to its label; unknown codes degrade to None.
    assert _bcu_status_from(0) is BcuStatus.BMS_INITIALISING
    assert _bcu_status_from(5) is BcuStatus.ERROR
    assert _bcu_status_from(8) is BcuStatus.PRODUCTION
    assert _bcu_status_from(99) is None
    assert _bcu_status_from(None) is None


# ---------------------------------------------------------------------------
# BMU tests
# ---------------------------------------------------------------------------


def test_bmu_empty():
    bmu = Bmu.from_register_cache(RegisterCache(), bmu_index=0)
    assert bmu.is_valid() is False
    assert bmu.bmu_index == 0  # type: ignore[attr-defined]
    assert bmu.v_cell_01 is None  # type: ignore[attr-defined]


def test_bmu_index_0():
    cache = _cache(
        {
            IR(60): 3200,  # v_cell_01 = 3.200 V (milli)
            IR(61): 3210,  # v_cell_02 = 3.210 V
            IR(90): 250,  # t_cell_01 = 25.0 °C (deci)
            IR(91): 255,  # t_cell_02 = 25.5 °C
            IR(114): 0x4142,
            IR(115): 0x4344,
            IR(116): 0x4546,
            IR(117): 0x4748,
            IR(118): 0x4900,
        }
    )
    bmu = Bmu.from_register_cache(cache, bmu_index=0)
    assert bmu.is_valid() is True
    assert bmu.bmu_index == 0  # type: ignore[attr-defined]
    assert bmu.v_cell_01 == pytest.approx(3.2)  # type: ignore[attr-defined]
    assert bmu.v_cell_02 == pytest.approx(3.21)  # type: ignore[attr-defined]
    assert bmu.t_cell_01 == pytest.approx(25.0)  # type: ignore[attr-defined]
    assert bmu.t_cell_02 == pytest.approx(25.5)  # type: ignore[attr-defined]
    assert bmu.serial_number == "ABCDEFGHI"  # type: ignore[attr-defined]


def test_bmu_index_is_a_label_not_a_stride():
    # Post-#265: every BMU reads its OWN device-address cache at base=0 (IR 60-118). bmu_index
    # is just a label; it no longer shifts the register window (the old 120*index stride read
    # the BCU's own cluster registers as cell data).
    cache = _cache(
        {
            IR(60): 3300,  # v_cell_01 = 3.300 V (milli)
            IR(90): 280,  # t_cell_01 = 28.0 °C (deci)
            IR(114): 0x4142,
            IR(115): 0x4344,
            IR(116): 0x4546,
            IR(117): 0x4748,
            IR(118): 0x4900,
        }
    )
    bmu = Bmu.from_register_cache(cache, bmu_index=1)
    assert bmu.is_valid() is True
    assert bmu.bmu_index == 1  # type: ignore[attr-defined]
    assert bmu.v_cell_01 == pytest.approx(3.3)  # type: ignore[attr-defined]
    assert bmu.t_cell_01 == pytest.approx(28.0)  # type: ignore[attr-defined]
    assert bmu.serial_number == "ABCDEFGHI"  # type: ignore[attr-defined]


def test_bmu_reads_only_its_own_cache_window():
    # Each BMU decodes IR(60-118) from its own cache; data outside that window — e.g. the old
    # stride offset IR(180), or the BCU cluster block — is never read.
    cache = _cache({IR(180): 3300})
    bmu = Bmu.from_register_cache(cache, bmu_index=1)
    assert bmu.v_cell_01 is None  # type: ignore[attr-defined]
    assert bmu.is_valid() is False


def test_bmu_has_24_cell_voltage_fields():
    bmu = Bmu.from_register_cache(RegisterCache(), bmu_index=0)
    dump = bmu.model_dump()
    v_fields = [k for k in dump if k.startswith("v_cell_")]
    t_fields = [k for k in dump if k.startswith("t_cell_")]
    assert len(v_fields) == 24
    assert len(t_fields) == 24
