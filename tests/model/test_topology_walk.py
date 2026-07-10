"""Golden-fixture pins for the #106 flat topology walk (``Plant.devices``).

Each test replays a committed wire capture offline (the same fixtures the golden
master uses — see ``test_fixture_golden_master.py``), derives capabilities the way
``Plant.from_caches()`` does (no live client), and pins the *exact* ordered
``Plant.devices`` row list: one root row (``parent=None``,
``is_control_authority=True``) followed by child rows sorted by
``(device_type.value, identity)``. A drift in the walk's shape — a row dropped,
reparented, or resorted — trips one of these pins.
"""

import pytest

from givenergy_modbus.model.plant import Plant

from .test_fixture_golden_master import _replay


async def _walk(*relpaths: str) -> list[tuple[str, str, str | None, bool, bool]]:
    """Replay a capture, derive capabilities offline, and flatten ``Plant.devices``.

    Mirrors ``Plant.from_caches(plant_from_capture(path).register_caches)`` — the
    documented recipe for building a fully-typed Plant from a register-cache dump
    (see ``Plant.from_caches`` docstring) — applied to ``_replay``'s in-memory
    caches instead of a fresh capture load, so every typed accessor (batteries,
    meters, hv_stacks, ems, gateway) the walk reads from is populated exactly as
    it would be for an offline capture export.
    """
    plant = await _replay(*relpaths)
    walked = Plant.from_caches(
        plant.register_caches,
        inverter_serial_number=plant.inverter_serial_number,
        data_adapter_serial_number=plant.data_adapter_serial_number,
    )
    return [(r.identity, r.device_type.value, r.parent, r.is_control_authority, r.is_valid) for r in walked.devices]


_FIXTURES = [
    "ems_2_inv_3_bat_a/ems_arm1036_30min.log",
    "aio_a/aio_arm620_redetect_7min.log",
    "hybrid_2_bat_a/hybrid_gen1_arm449_0x11_poll_10min.log",
    "gateway_2aio_a/gateway_gaaa0014_10min_daylight.log",
    "three_phase_hv_a/giv3hy11_da011_detect_10min.log",
]


async def _walked_plant(*relpaths: str) -> Plant:
    """Like ``_walk`` but returns the walked ``Plant`` itself, not flattened tuples."""
    plant = await _replay(*relpaths)
    return Plant.from_caches(
        plant.register_caches,
        inverter_serial_number=plant.inverter_serial_number,
        data_adapter_serial_number=plant.data_adapter_serial_number,
    )


@pytest.mark.parametrize("relpath", _FIXTURES)
async def test_walk_invariants(relpath):
    """Structural invariants that hold regardless of redaction-collapsed identities.

    Global identity uniqueness is deliberately NOT asserted here: these fixtures are
    raw REDACTED wire captures where same-batch devices (EMS-managed inverters, AIO
    modules, 3ph BMUs) legitimately decode byte-identical zeroed serials offline — see
    the per-fixture pins above. Uniqueness is a property of the live MockPlant serve
    path, which disambiguates those collisions, and is asserted there instead (see
    ``tests/client/test_mock_plant_integration.py::_assert_three_phase_hv``).
    """
    walked = await _walked_plant(relpath)
    rows = walked.devices
    roots = [r for r in rows if r.parent is None]
    assert len(roots) == 1 and rows[0] is roots[0]
    assert sum(r.is_control_authority for r in rows) == 1
    assert all(r.identity for r in rows)  # non-empty
    known = {r.identity for r in rows}
    assert all(r.parent in known for r in rows if r.parent is not None)
    assert [(r.identity, r.parent, r.device_type.value) for r in walked.devices] == [
        (r.identity, r.parent, r.device_type.value) for r in rows
    ]  # deterministic across accesses


async def test_ems_walk_pins_controller_plus_two_managed_inverters_and_meters():
    """EMS controller + 2 managed inverters (blinded, rollup-sourced) + 2 CT meters.

    No LV/HV batteries on this row list — the three physical packs live behind
    the managed inverters' own dongles (separate captures), invisible to the EMS
    controller's own register file. The two managed-inverter rows share an
    identical identity (``CE2231G000_managed``): the fixture's real inverter
    serials differ (`CE2231G000` vs `CE2242G000` per the fixture README), but the
    committed capture's EMS-rollup slots decode byte-identical — a pre-existing
    redaction artifact on this capture, not a walk defect (see test-3 report).
    """
    rows = await _walk("ems_2_inv_3_bat_a/ems_arm1036_30min.log")
    assert rows == [
        ("EMS2522000", "ems", None, True, True),
        ("CE2231G000_managed", "inverter", "EMS2522000", False, True),
        ("CE2231G000_managed", "inverter", "EMS2522000", False, True),
        ("EMS2522000_meter_1", "meter", "EMS2522000", False, True),
        ("EMS2522000_meter_3", "meter", "EMS2522000", False, True),
    ]


async def test_aio_walk_pins_inverter_plus_four_battery_modules_and_hv_stack():
    """All-in-One: inverter root, 4 integrated HV battery modules, 1 HV stack (BCU).

    The four module identities are all ``2414G000`` (no ``CH`` prefix): this BMU
    firmware (BAAA0013) stores its serial split on the wire (prefix at IR110, tail
    at IR115-118, #378) and this replay path applies no MockPlant-style
    disambiguation, so the raw decode is prefixless and duplicated across modules
    — documented as expected on this fixture in
    ``test_mock_plant_integration.py::_assert_aio_redetect``.
    """
    rows = await _walk("aio_a/aio_arm620_redetect_7min.log")
    assert rows == [
        ("CH2414G000", "inverter", None, True, True),
        ("2414G000", "battery_module", "CH2414G000", False, True),
        ("2414G000", "battery_module", "CH2414G000", False, True),
        ("2414G000", "battery_module", "CH2414G000", False, True),
        ("2414G000", "battery_module", "CH2414G000", False, True),
        ("CH2414G000_hvstack_0x70", "hv_stack", "CH2414G000", False, True),
    ]


async def test_hybrid_walk_pins_inverter_plus_two_lv_batteries():
    """Single-phase HYBRID_GEN1, direct (no EMS): inverter root + 2 LV battery packs."""
    rows = await _walk("hybrid_2_bat_a/hybrid_gen1_arm449_0x11_poll_10min.log")
    assert rows == [
        ("SA2114G000", "inverter", None, True, True),
        ("BG2134G000", "battery", "SA2114G000", False, True),
        ("DZ2228G000", "battery", "SA2114G000", False, True),
    ]


async def test_gateway_walk_pins_gateway_plus_two_meters():
    """Gen1 Gateway fronting 2 parallel AIOs: gateway root + 2 CT meters.

    The AIOs' batteries are register-embedded in the gateway rollup (IR1600-1859),
    not separately-addressed devices, so they don't surface as their own rows here.
    """
    rows = await _walk("gateway_2aio_a/gateway_gaaa0014_10min_daylight.log")
    assert rows == [
        ("GW2412G000", "gateway", None, True, True),
        ("GW2412G000_meter_1", "meter", "GW2412G000", False, True),
        ("GW2412G000_meter_2", "meter", "GW2412G000", False, True),
    ]


async def test_three_phase_hv_walk_pins_inverter_plus_six_bmus_hv_stack_and_two_meters():
    """Three-phase HV hybrid: inverter root, 1 HV stack with 6 BMU modules, 2 meters.

    All six BMU identities pin to the same ``HY2336G000``: the fixture's redaction
    scheme preserves family prefix + manufacture week but zeros only the trailing
    per-unit digits (see ``captures/README.md``), so same-batch modules collapse
    to an identical placeholder after redaction — a documented property of this
    capture's redaction, not a decode defect.
    """
    rows = await _walk("three_phase_hv_a/giv3hy11_da011_detect_10min.log")
    assert rows == [
        ("TC2337G000", "inverter", None, True, True),
        ("HY2336G000", "battery_module", "TC2337G000_hvstack_0x70", False, True),
        ("HY2336G000", "battery_module", "TC2337G000_hvstack_0x70", False, True),
        ("HY2336G000", "battery_module", "TC2337G000_hvstack_0x70", False, True),
        ("HY2336G000", "battery_module", "TC2337G000_hvstack_0x70", False, True),
        ("HY2336G000", "battery_module", "TC2337G000_hvstack_0x70", False, True),
        ("HY2336G000", "battery_module", "TC2337G000_hvstack_0x70", False, True),
        ("TC2337G000_hvstack_0x70", "hv_stack", "TC2337G000", False, True),
        ("TC2337G000_meter_1", "meter", "TC2337G000", False, True),
        ("TC2337G000_meter_2", "meter", "TC2337G000", False, True),
    ]
