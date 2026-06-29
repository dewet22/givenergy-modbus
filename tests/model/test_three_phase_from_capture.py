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

    # Per-phase inverter output — all zero on this idle capture.
    assert inv.p_out_ac1 == pytest.approx(0.0)  # type: ignore[attr-defined]
    assert inv.p_out_ac2 == pytest.approx(0.0)  # type: ignore[attr-defined]
    assert inv.p_out_ac3 == pytest.approx(0.0)  # type: ignore[attr-defined]

    # Inherited single-phase grid nodes — IR(30) p_grid_out reads as 0 on 3-phase. With the
    # inverter idle here we can't tell whether 3ph firmware ever populates it; #141 stays
    # open pending a capture with meaningful grid flow.
    assert inv.p_grid_out == 0  # type: ignore[attr-defined]
    assert inv.p_grid_out_ph1 == 0  # type: ignore[attr-defined]

    # Per-phase loads IR(1083-1085) — IR(1083) raw=65456 and IR(1084) raw=65351 silently
    # decode to ``None`` because the current ``Def(C.deci, ...)`` uses unsigned uint16 and
    # the values fall outside the (0, 6500) bounds. Read as int16 they're -8.0 W / -18.5 W
    # respectively, which would make sense as net per-phase load on an exporting house.
    # Calling that out here rather than asserting either interpretation; tracked as a
    # follow-up because confirming wants an active-grid 3-phase capture.
    assert inv.p_load_ac1 is None  # type: ignore[attr-defined]
    assert inv.p_load_ac2 is None  # type: ignore[attr-defined]
    assert inv.p_load_ac3 == pytest.approx(26.9)  # type: ignore[attr-defined]
