"""Wire-level regression test for HYBRID_HV_GEN3 (DTC family 81), replayed from a real capture.

The first field capture of a GIV-HY-8.0-G3-HV — a residential single-phase HV hybrid
from givenergy-hass#295. `Model.HYBRID_HV_GEN3` was classified three-phase, so the plant
polled and decoded the IR(1000-1413) bank; that bank *answers* on this unit rather than
error-responding, and returns zeros throughout, which surfaced to the reporter as a
live-but-idle system (battery SOC 0 %, house consumption 0, both PV strings 0 W).

The manifest's own comment on ``is_three_phase`` already draws this distinction for the
sibling model — the residential ALL_IN_ONE (DTC family 8) is HV but SINGLE-phase — and
HYBRID_HV_GEN3 looks to have been swept into the set with it. No 81xx capture existed
until now, so the membership had never been exercised against hardware.

See ``tests/fixtures/captures/hybrid_hv_gen3_a/README.md`` for provenance.
"""

from pathlib import Path

import pytest

from givenergy_modbus.model.inverter import Model, SinglePhaseInverter, resolve_model
from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter, select_inverter
from givenergy_modbus.model.manifest import has_capability
from givenergy_modbus.model.plant import Plant
from givenergy_modbus.model.register import IR
from givenergy_modbus.testing.mock_plant import plant_from_capture

_CAPTURE = Path(__file__).parents[1] / "fixtures" / "captures" / "hybrid_hv_gen3_a" / "givhy80g3hv_hass295_120s.log"

# The reporter's device-type code. This capture is 120 s of steady-state refresh traffic
# and carries no HR(0) — the identity bank is a load_config read taken once at startup —
# so the DTC comes from the reporter's own plant export, not from these bytes.
_DTC = 0x8102


@pytest.fixture(scope="module")
def replayed_plant() -> Plant:
    """Decode the capture once for the module (the frames are immutable, so share the Plant)."""
    return plant_from_capture(_CAPTURE)


def test_dtc_8102_resolves_to_hybrid_hv_gen3():
    """Anchor the fixture to its model: DTC 0x8102 is HYBRID_HV_GEN3 at any firmware."""
    assert resolve_model(_DTC, 0) is Model.HYBRID_HV_GEN3
    assert resolve_model(_DTC, 500) is Model.HYBRID_HV_GEN3


def test_hybrid_hv_gen3_is_hv_but_not_three_phase():
    """DTC family 81 is a residential HV hybrid — HV battery architecture, single-phase AC.

    Same shape as the residential ALL_IN_ONE (family 8), which the manifest already
    excludes from ``is_three_phase`` for exactly this reason.
    """
    assert has_capability("is_hv", Model.HYBRID_HV_GEN3) is True
    assert has_capability("is_three_phase", Model.HYBRID_HV_GEN3) is False


def test_select_inverter_picks_single_phase_for_hv_gen3(replayed_plant: Plant):
    """The model→class boundary: HYBRID_HV_GEN3 decodes through the single-phase layout.

    This is the defect the reporter saw. Under the three-phase layout every headline
    field reads zero off the same cache; under the single-phase layout they carry the
    real values asserted in ``test_single_phase_decode_from_capture``.
    """
    inv = select_inverter(Model.HYBRID_HV_GEN3, replayed_plant.register_caches[0x11])
    assert isinstance(inv, SinglePhaseInverter)
    assert not isinstance(inv, ThreePhaseInverter)
    assert inv.battery_soc == 100  # type: ignore[attr-defined]


@pytest.mark.timeout(15)
def test_single_phase_decode_from_capture(replayed_plant: Plant):
    """IR(0-59)/IR(180-239) decode to a self-consistent sunny-afternoon single-phase plant."""
    inv = SinglePhaseInverter.from_register_cache(replayed_plant.register_caches[0x11])

    assert inv.battery_soc == 100  # type: ignore[attr-defined]
    assert inv.v_battery == pytest.approx(240.07)  # type: ignore[attr-defined]
    assert inv.p_battery == 58  # type: ignore[attr-defined]

    # Both PV strings generating; the per-string day counters sum to the 21.1 kWh total.
    assert inv.p_pv1 == 674  # type: ignore[attr-defined]
    assert inv.p_pv2 == 4531  # type: ignore[attr-defined]
    assert inv.e_pv1_day == pytest.approx(6.2)  # type: ignore[attr-defined]
    assert inv.e_pv2_day == pytest.approx(14.9)  # type: ignore[attr-defined]

    # Derived house consumption — the field the reporter saw pinned at 0.
    assert inv.e_consumption_today == pytest.approx(5.2)  # type: ignore[attr-defined]
    assert inv.is_ac_coupled is False  # type: ignore[attr-defined]


@pytest.mark.timeout(15)
def test_three_phase_bank_answers_but_is_all_zero(replayed_plant: Plant):
    """The evidence for the reclassification, pinned so a later capture can contradict it.

    A genuinely absent block error-responds or times out; this one answers every read
    with zeros. That is why the misclassification presented as an idle plant rather than
    an obvious decode failure, and why a readability probe could not have caught it.
    """
    cache = replayed_plant.register_caches[0x11]

    three_phase = [cache.get(IR(i)) for i in range(1000, 1414)]
    assert all(v is not None for v in three_phase), "the 1000-range answered every read"
    assert not any(three_phase), "…and returned zeros throughout"

    single_phase = [cache.get(IR(i)) for i in range(0, 60)]
    assert sum(1 for v in single_phase if v) == 50, "IR(0-59) is densely populated"


@pytest.mark.timeout(15)
def test_every_response_frame_decodes(replayed_plant: Plant):
    """All 17 rx frames decode cleanly — `plant_from_capture` skips undecodable ones silently.

    Without this, a corrupted fixture (a botched CRC regen, a hand-edit) would degrade to a
    thinner plant rather than an error, and the assertions above would quietly test less.
    """
    devices = set(replayed_plant.register_caches)
    assert devices == {0x01, 0x11, 0x32, 0x50, 0x51, 0x52, 0x70}
    populated = sum(1 for a in devices if len(replayed_plant.register_caches[a]))
    assert populated == 6, "only the empty 0x32 cache should be unpopulated"


@pytest.mark.timeout(15)
def test_hv_topology_decodes_from_capture(replayed_plant: Plant):
    """Residential HV topology: one BCU at 0x70 fronting the reporter's three BMU modules."""
    from givenergy_modbus.model.hv_bcu import Bcu, Bmu

    bcu = Bcu.from_register_cache(replayed_plant.register_caches[0x70])
    assert bcu.is_valid()  # type: ignore[attr-defined]
    assert bcu.number_of_modules == 3  # type: ignore[attr-defined]

    for addr in (0x50, 0x51, 0x52):
        bmu = Bmu.from_register_cache(replayed_plant.register_caches[addr])
        assert bmu.is_valid(), f"BMU 0x{addr:02x} not valid"
