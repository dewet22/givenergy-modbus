"""Wire-level regression test for the three-phase decode, replayed from a real capture.

The first real three-phase dataset — a GIV-3HY-11 HV hybrid from givenergy-hass#174 —
fed through the framer into a bare ``Plant``, asserting the decoded battery values. Every
other three-phase test primes synthetic registers; this is the only one that proves the
real wire→model path, and it locks in the fixes these frames drove:

- ``i_battery`` is centi, not deci (#264);
- ``p_battery`` / ``e_battery_throughput`` are derived from the native three-phase
  registers (#262);
- the HV BCU cluster block decodes (the path consumers read per-stack SOC from).

See ``tests/fixtures/captures/three_phase_hv_a/README.md`` for provenance.
"""

from pathlib import Path

import pytest

from givenergy_modbus.model.hv_bcu import Bcu
from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.testing.mock_plant import plant_from_capture

_CAPTURE = Path(__file__).parents[1] / "fixtures" / "captures" / "three_phase_hv_a" / "giv3hy11_hass174_180s.txt"


@pytest.fixture(scope="module")
def replayed_plant() -> Plant:
    """Decode the capture once for the module (the frames are immutable, so share the Plant).

    Routed through the shared ``plant_from_capture`` loader, which now parses this fixture's
    ``rx:/tx: <hex>`` line form directly (#322) — so this also regression-tests that the
    integration capture loads through the same path ``mock-server`` uses.
    """
    return plant_from_capture(_CAPTURE)


@pytest.mark.timeout(15)
def test_three_phase_inverter_battery_decode_from_capture(replayed_plant: Plant):
    """Inverter-level battery fields decode correctly on a real three-phase HV unit (0x11)."""
    inv = ThreePhaseInverter.from_register_cache(replayed_plant.register_caches[0x11])
    assert inv.battery_soc == 71  # type: ignore[attr-defined]
    # #264: i_battery is centi, not deci — the final frame's raw -1 decodes to -0.01 A (was -0.1).
    assert inv.i_battery == pytest.approx(-0.01)  # type: ignore[attr-defined]
    assert inv.p_battery_charge == pytest.approx(8.1)  # type: ignore[attr-defined]
    assert inv.p_battery_discharge == pytest.approx(0.0)  # type: ignore[attr-defined]
    # #262: derived p_battery = discharge − charge (negative = charging), single-phase sign convention.
    assert inv.p_battery == pytest.approx(-8.1)  # type: ignore[attr-defined]
    # #262: derived e_battery_throughput = charge_total + discharge_total.
    assert inv.e_battery_throughput == pytest.approx(11840.2 + 10753.6)  # type: ignore[attr-defined]
    assert inv.v_battery_bms == pytest.approx(470.3)  # type: ignore[attr-defined]


@pytest.mark.timeout(15)
def test_three_phase_hv_bcu_decode_from_capture(replayed_plant: Plant):
    """BCU cluster-level data decodes (the path consumers read per-stack SOC/temp from)."""
    bcu = Bcu.from_register_cache(replayed_plant.register_caches[0x70])
    assert bcu.number_of_modules == 6  # type: ignore[attr-defined]
    assert bcu.battery_soc_max == 71  # type: ignore[attr-defined]
    assert bcu.battery_soc_min == 68  # type: ignore[attr-defined]
    assert bcu.battery_voltage == pytest.approx(470.3)  # type: ignore[attr-defined]
    assert bcu.battery_soh == 95  # type: ignore[attr-defined]


@pytest.mark.timeout(15)
def test_three_phase_grid_block_decode_from_capture(replayed_plant: Plant):
    """Three-phase grid-block IR(1061-1099) decodes against the lamztib capture.

    The inverter is idle at capture time (``p_inverter_out == 0``, ``p_battery ~ 0``,
    ``system_mode == NORMAL``), so the topology question in #141 (does IR30 aggregate
    per-phase, or stay a distinct external-CT reading on 3-phase?) is not settled here —
    a capture with meaningful grid flow is still needed. What this test locks in is the
    decode path itself for the registers that *are* populated and well-formed on a real
    three-phase wire.
    """
    inv = ThreePhaseInverter.from_register_cache(replayed_plant.register_caches[0x11])

    # Per-phase grid voltages / currents / frequency — all populated and within bounds.
    assert inv.v_ac1 == pytest.approx(405.4)  # type: ignore[attr-defined]
    assert inv.v_ac2 == pytest.approx(406.6)  # type: ignore[attr-defined]
    assert inv.v_ac3 == pytest.approx(406.3)  # type: ignore[attr-defined]
    assert inv.i_ac1 == pytest.approx(0.9)  # type: ignore[attr-defined]
    assert inv.i_ac2 == pytest.approx(0.8)  # type: ignore[attr-defined]
    assert inv.i_ac3 == pytest.approx(0.9)  # type: ignore[attr-defined]
    assert inv.f_ac1 == pytest.approx(50.02)  # type: ignore[attr-defined]

    # Aggregates: at-capture-time idle on the inverter side, a little export at the meter.
    assert inv.p_inverter_out == pytest.approx(0.0)  # type: ignore[attr-defined]
    assert inv.p_meter_import == pytest.approx(0.0)  # type: ignore[attr-defined]
    assert inv.p_meter_export == pytest.approx(4.0)  # type: ignore[attr-defined]
    assert inv.p_grid_apparent == pytest.approx(652.0)  # type: ignore[attr-defined]
    assert inv.p_load_all == pytest.approx(339.0)  # type: ignore[attr-defined]

    # Per-phase inverter active power IR(1091-1093) — all zero on this idle capture.
    assert inv.p_inverter_active_ac1 == 0  # type: ignore[attr-defined]
    assert inv.p_inverter_active_ac2 == 0  # type: ignore[attr-defined]
    assert inv.p_inverter_active_ac3 == 0  # type: ignore[attr-defined]

    # Inherited single-phase grid nodes — IR(30) p_grid_out reads as 0 on 3-phase. With the
    # inverter idle here we can't tell whether 3ph firmware ever populates it; #141 stays
    # open pending a capture with meaningful grid flow.
    assert inv.p_grid_out == 0  # type: ignore[attr-defined]
    assert inv.p_grid_out_ph1 == 0  # type: ignore[attr-defined]

    # Per-phase grid-METER active power IR(1083-1085) — signed watts (#185). The old unsigned
    # C.deci decode dropped IR1083/1084 as out-of-bounds (raw 65456/65351) and mis-scaled IR1085;
    # as signed int16 they read -80 / -185 / +269 W, summing to +4 W — matching p_meter_export
    # (4.0 W) on this exporting house. That sum identity is what confirms the signed-watt scale.
    assert inv.p_meter_active_ac1 == -80  # type: ignore[attr-defined]
    assert inv.p_meter_active_ac2 == -185  # type: ignore[attr-defined]
    assert inv.p_meter_active_ac3 == 269  # type: ignore[attr-defined]
    assert (  # the per-phase sum reconciles with the aggregate meter export
        inv.p_meter_active_ac1 + inv.p_meter_active_ac2 + inv.p_meter_active_ac3  # type: ignore[attr-defined]
    ) == pytest.approx(inv.p_meter_export)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# giv3hy11_da011_10min.log — the same plant's multi-module cli capture (2026-07-08)
# ---------------------------------------------------------------------------

_CAPTURE_MULTI = Path(__file__).parents[1] / "fixtures" / "captures" / "three_phase_hv_a" / "giv3hy11_da011_10min.log"


@pytest.fixture(scope="module")
def multi_module_plant() -> Plant:
    """Decode the 2026-07-08 cli capture once for the module (frames are immutable)."""
    return plant_from_capture(_CAPTURE_MULTI)


@pytest.mark.timeout(15)
def test_multi_module_capture_device_topology(multi_module_plant: Plant):
    """Every device the plant fronts answered: inverter, 2 meters, 6 BMUs, BCU, 2 BAMS."""
    caches = multi_module_plant.register_caches
    for addr in (0x01, 0x02, 0x11, 0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x70, 0x90, 0xA0):
        assert addr in caches, f"device 0x{addr:02x} missing from capture"


@pytest.mark.timeout(15)
def test_multi_module_bmu_per_cell_decode(multi_module_plant: Plant):
    """All 6 HV BMU modules decode per-cell data at their own addresses (0x50-0x55).

    The wire validation #265 asked for: the earlier HA capture's module-0 stride
    overlapped the BCU block, so this is the first fixture where per-module,
    per-cell voltages/temps decode against real silicon.
    """
    from givenergy_modbus.model.hv_bcu import Bmu

    for addr in range(0x50, 0x56):
        bmu = Bmu.from_register_cache(multi_module_plant.register_caches[addr])
        assert bmu.is_valid(), f"BMU 0x{addr:02x} not valid"
        v_cells = [getattr(bmu, f"v_cell_{i:02d}") for i in range(1, 25)]
        # near-full LiFePO4 pack: all 24 cells in a tight band around 3.35 V
        assert all(3.3 < v < 3.4 for v in v_cells), f"BMU 0x{addr:02x} cell voltages {v_cells}"
    # Temperatures: modules 0x50-0x54 populate all 24 sensors; 0x55 populates only the
    # first 12, and its split serial's "HY" prefix at IR(110) decodes as
    # t_cell_21 = 1852.1 — the imperative decode applies no bounds (the LUT's declared
    # min/max are inert), so the artefact passes through. Pinned as-is (characterisation);
    # the decode-bounds gap is tracked as a follow-up.
    for addr in range(0x50, 0x55):
        bmu = Bmu.from_register_cache(multi_module_plant.register_caches[addr])
        t_cells = [getattr(bmu, f"t_cell_{i:02d}") for i in range(1, 25)]
        assert all(25.0 < t < 40.0 for t in t_cells), f"BMU 0x{addr:02x} cell temps {t_cells}"
    bmu_55 = Bmu.from_register_cache(multi_module_plant.register_caches[0x55])
    t_55 = [getattr(bmu_55, f"t_cell_{i:02d}") for i in range(1, 25)]
    assert all(25.0 < t < 40.0 for t in t_55[:12]), f"BMU 0x55 populated temps {t_55[:12]}"
    assert t_55[20] == pytest.approx(1852.1)  # "HY" (0x4859) read as a temperature
    # Serials are date-redacted placeholders. Module 0x55's firmware stores its serial
    # SPLIT on the wire ("HY" at IR(110), the tail at IR(115-118)) — preserved as
    # captured, so its decoded IR(114-118) serial carries no prefix (see README).
    for addr in range(0x50, 0x55):
        bmu = Bmu.from_register_cache(multi_module_plant.register_caches[addr])
        assert bmu.serial_number == "HY2336G000"  # type: ignore[attr-defined]
    bmu_55 = Bmu.from_register_cache(multi_module_plant.register_caches[0x55])
    assert bmu_55.serial_number == "2336G000"  # type: ignore[attr-defined]


@pytest.mark.timeout(15)
def test_multi_module_bcu_cluster_and_serial_decode(multi_module_plant: Plant):
    """BCU cluster block plus its own unit serial at IR(138-142) (#375)."""
    bcu = Bcu.from_register_cache(multi_module_plant.register_caches[0x70])
    assert bcu.is_valid()  # type: ignore[attr-defined]
    assert bcu.number_of_modules == 6  # type: ignore[attr-defined]
    assert bcu.battery_voltage == pytest.approx(477.9)  # type: ignore[attr-defined]
    assert bcu.battery_soc_max == 99  # type: ignore[attr-defined]
    assert bcu.battery_soc_min == 98  # type: ignore[attr-defined]
    assert bcu.battery_soh == 95  # type: ignore[attr-defined]
    # matches the reporter's stated hardware: 52 Ah modules
    assert bcu.battery_nominal_capacity_ah == pytest.approx(52.0)  # type: ignore[attr-defined]
    # the BCU's own serial (redacted placeholder) — first wire evidence, #375
    assert bcu.serial_number == "HB2336G000"  # type: ignore[attr-defined]


@pytest.mark.timeout(15)
def test_multi_module_inverter_and_meters_decode(multi_module_plant: Plant):
    """Three-phase inverter block and both meters decode from the same capture."""
    from givenergy_modbus.model.meter import Meter

    inv = ThreePhaseInverter.from_register_cache(multi_module_plant.register_caches[0x11])
    assert inv.battery_soc == 99  # type: ignore[attr-defined]
    assert inv.v_battery_bms == pytest.approx(477.7)  # type: ignore[attr-defined]
    assert inv.v_ac1 == pytest.approx(402.9)  # type: ignore[attr-defined]
    assert inv.f_ac1 == pytest.approx(50.0)  # type: ignore[attr-defined]
    assert inv.e_battery_throughput == pytest.approx(23309.7)  # type: ignore[attr-defined]
    assert inv.p_load_all == pytest.approx(715.0)  # type: ignore[attr-defined]

    m1 = Meter.from_register_cache(multi_module_plant.register_caches[0x01])
    m2 = Meter.from_register_cache(multi_module_plant.register_caches[0x02])
    assert m1.is_valid() and m2.is_valid()  # type: ignore[attr-defined]
    assert m1.v_phase_1 == pytest.approx(232.2)  # type: ignore[attr-defined]
    assert m2.v_phase_1 == pytest.approx(232.1)  # type: ignore[attr-defined]
