"""Tests for ``Plant.devices`` — the #106 flat topology walk.

``PlantDevice`` carries the walk contract: ``identity`` / ``device_type`` /
``parent`` / ``device``, plus ``serial_number`` / ``firmware_version`` /
``is_valid`` / ``is_control_authority`` / ``data_source``. ``Plant.devices``
returns exactly one root row (``parent=None``) — an inverter, EMS, or gateway,
depending on plant shape — followed by every other device as a flat child row
parented to that root, sorted by ``(device_type.value, identity)``. Exactly
one row is ``is_control_authority=True``: the root.

Plants are constructed in-memory, matching the idiom in ``test_devices.py``.
"""

import dataclasses

import pytest

from givenergy_modbus.model.devices import DeviceType, PlantDevice
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.plant import Plant, PlantCapabilities
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register_cache import RegisterCache
from tests.model.test_devices import _add_rollup_slot, _encode_serial


def test_plant_device_row_contract():
    """PlantDevice carries the #106 walk contract fields; `model` is gone."""
    from givenergy_modbus.model.devices import DeviceType

    row = PlantDevice(
        identity="XX1234A567",
        device_type=DeviceType.BATTERY,
        parent="YY1234A567",
        device=object(),
        serial_number="XX1234A567",
        firmware_version="3005",
        is_valid=True,
        is_control_authority=False,
        data_source=None,
    )
    assert row.identity == "XX1234A567"
    assert row.parent == "YY1234A567"
    assert row.is_control_authority is False
    assert not hasattr(row, "model")
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.identity = "nope"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Plant-priming helpers — same inline-construction idiom used throughout this
# file and test_devices.py (Plant() + capabilities + register_caches).
# ---------------------------------------------------------------------------


def _battery_cache(serial: str) -> RegisterCache:
    """A battery register cache carrying a valid serial in IR(110..114)."""
    return RegisterCache({IR(110 + i): v for i, v in _encode_serial(serial).items()})


def _hybrid_plant_two_packs(*, drop_cache_for: int | None = None) -> Plant:
    """Hybrid inverter plant (root at 0x11) with two LV battery packs at 0x32/0x33.

    ``drop_cache_for`` optionally omits one pack's register cache (0x32 or
    0x33) to exercise the #213 placeholder path — the address stays listed in
    capabilities but has no cache, so it decodes to an invalid, serial-less
    battery instead of being dropped.
    """
    plant = Plant()
    plant.inverter_serial_number = "SA1234G567"
    plant.capabilities = PlantCapabilities(
        device_type=Model.HYBRID_GEN3,
        inverter_address=0x11,
        lv_battery_addresses=[0x32, 0x33],
    )
    plant.register_caches[0x11] = RegisterCache()
    if drop_cache_for != 0x32:
        plant.register_caches[0x32] = _battery_cache("XX1234A567")
    if drop_cache_for != 0x33:
        plant.register_caches[0x33] = _battery_cache("YY1234A567")
    return plant


def test_walk_single_inverter_plant_root_and_batteries():
    """Hybrid plant: inverter root (authority), packs as child rows keyed by own serial."""
    plant = _hybrid_plant_two_packs()  # existing-style helper: caps + primed 0x11/0x32/0x33
    rows = plant.devices
    root = rows[0]
    assert root.parent is None and root.device_type is DeviceType.INVERTER
    assert root.identity == plant.inverter_serial_number
    assert root.is_control_authority is True
    packs = [r for r in rows if r.device_type is DeviceType.BATTERY]
    assert [p.identity for p in packs] == [p.serial_number for p in packs]  # own serial, no prefix
    assert all(p.parent == root.identity for p in packs)
    assert sum(r.is_control_authority for r in rows) == 1


def test_walk_placeholder_battery_slot_identity():
    """#213 placeholder (listed address, empty cache): inert slot identity, is_valid False."""
    plant = _hybrid_plant_two_packs(drop_cache_for=0x33)
    rows = plant.devices
    ph = [r for r in rows if r.device_type is DeviceType.BATTERY and not r.is_valid]
    assert len(ph) == 1
    assert ph[0].identity == f"{plant.inverter_serial_number}_battery_2"
    assert ph[0].serial_number is None


def test_walk_ems_plant_controller_authority_managed_children():
    """EMS plant: EMS root has authority; managed inverters are INVERTER rows.

    Identity {serial}_managed, parent=EMS root, data_source='ems_rollup', is_valid True.
    """
    values: dict = {IR(2040): 1, IR(2044): 2}  # ems_status=1, inverter_count=2
    _add_rollup_slot(values, 1, serial="XX1234A567", power=1800, soc=65)
    _add_rollup_slot(values, 2, serial="YY1234A567", power=2200, soc=78)
    # HR(19)/HR(21): dsp/arm firmware words, read via plant.inverter decoding the EMS's
    # own cache (C.firmware_version -> "D0.{dsp}-A0.{arm}").
    values[HR(19)] = 5
    values[HR(21)] = 7
    plant = Plant()
    plant.inverter_serial_number = "EM1234A567"
    plant.capabilities = PlantCapabilities(device_type=Model.EMS, inverter_address=0x11)
    plant.register_caches[0x11] = RegisterCache(values)

    rows = plant.devices
    root = rows[0]
    assert root.parent is None
    assert root.device_type is DeviceType.EMS
    assert root.identity == plant.inverter_serial_number
    assert root.is_control_authority is True
    assert root.firmware_version == "D0.5-A0.7"  # HR(19)=5, HR(21)=7

    managed = [r for r in rows if r.device_type is DeviceType.INVERTER]
    assert len(managed) == 2
    assert {r.identity for r in managed} == {"XX1234A567_managed", "YY1234A567_managed"}
    assert all(r.parent == root.identity for r in managed)
    assert all(r.data_source == "ems_rollup" for r in managed)
    assert all(r.is_valid is True for r in managed)
    # Blinded rollup entries carry no direct decode, so no per-inverter firmware.
    assert all(r.firmware_version is None for r in managed)
    assert sum(r.is_control_authority for r in rows) == 1


def test_walk_gateway_plant():
    """Gateway root (authority), no INVERTER row, meters parent to the gateway root."""
    plant = Plant()
    plant.inverter_serial_number = "GW1234A567"
    plant.capabilities = PlantCapabilities(
        device_type=Model.GATEWAY,
        inverter_address=0x11,
        meter_addresses=[0x01],
    )
    # IR(1600-1603): gateway_version block ('G'=0x47,'A'=0x41, then digit registers 0, 9) -> "GA0009".
    plant.register_caches[0x11] = RegisterCache({IR(1600): 0x4741, IR(1601): 0, IR(1602): 0, IR(1603): 9})
    plant.register_caches[0x01] = RegisterCache({IR(60): 2300})  # v_phase_1 deci -> 230.0V, meter.is_valid()

    rows = plant.devices
    root = rows[0]
    assert root.parent is None
    assert root.device_type is DeviceType.GATEWAY
    assert root.identity == plant.inverter_serial_number
    assert root.is_control_authority is True
    assert DeviceType.INVERTER not in [r.device_type for r in rows]
    assert root.firmware_version == "GA0009"

    meters = [r for r in rows if r.device_type is DeviceType.METER]
    assert len(meters) == 1
    assert meters[0].parent == root.identity
    assert meters[0].is_valid is True
    # Meter carries no own serial_number field (Phase-1 limitation) -> synthetic identity.
    assert meters[0].identity == f"{plant.inverter_serial_number}_meter_1"
    assert sum(r.is_control_authority for r in rows) == 1


def test_walk_hv_stack_and_bmus():
    """Stack identity {plant_serial}_hvstack_{addr:#04x}; BMUs parent to the stack.

    BMU identity = own serial; stack firmware = bcu.pack_software_version.
    """
    plant = Plant()
    plant.inverter_serial_number = "HV1234A567"
    plant.capabilities = PlantCapabilities(
        device_type=Model.ALL_IN_ONE,
        inverter_address=0x11,
        bcu_stacks=[(0, 1)],  # BCU at 0x70 + 0, one BMU at 0x50
    )
    plant.register_caches[0x11] = RegisterCache()
    # IR(60-63): BCU pack_software_version ('H'=0x48,'Y'=0x59, then digit registers 0, 1) -> "HY0001".
    plant.register_caches[0x70] = RegisterCache({IR(60): 0x4859, IR(61): 0, IR(62): 0, IR(63): 1})
    # IR(114-118): BMU's own 5-register serial block.
    plant.register_caches[0x50] = RegisterCache({IR(114 + i): v for i, v in _encode_serial("XX1234A567").items()})

    rows = plant.devices
    root = rows[0]
    stack_identity = f"{plant.inverter_serial_number}_hvstack_0x70"  # device_address=0x70, {addr:#04x}
    stack_row = next(r for r in rows if r.device_type is DeviceType.HV_STACK)
    assert stack_row.parent == root.identity
    assert stack_row.identity == stack_identity
    assert stack_row.firmware_version == "HY0001"

    bmu_rows = [r for r in rows if r.device_type is DeviceType.BATTERY_MODULE]
    assert len(bmu_rows) == 1
    assert bmu_rows[0].parent == stack_identity
    assert bmu_rows[0].identity == "XX1234A567"  # own serial, no prefix
    assert bmu_rows[0].serial_number == "XX1234A567"
