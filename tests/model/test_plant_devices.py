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
    assert {p.identity for p in packs} == {"XX1234A567", "YY1234A567"}  # own serial, no prefix
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


def test_walk_root_identity_uses_inverter_serial_accessor():
    """I2: root identity anchors on ``Plant.inverter_serial`` (register-first).

    Not the envelope ``inverter_serial_number`` field. The documented
    ``Plant.from_caches()`` recipe (no live client) doesn't pass an
    envelope serial, so a bare ``Plant.from_caches()`` call must still resolve the real
    serial from the register cache (HR13-17) rather than surfacing an empty identity.
    """
    values = {
        HR(0): 0x2001,
        HR(21): 449,  # HYBRID_GEN1
        # HR(13-17) -> "XX1234A567"
        HR(13): 0x5858,
        HR(14): 0x3132,
        HR(15): 0x3334,
        HR(16): 0x4135,
        HR(17): 0x3637,
    }
    plant = Plant.from_caches({0x11: RegisterCache(values)})
    assert plant.devices[0].identity == "XX1234A567"


def test_walk_aio_module_synthetic_identity_when_serial_less():
    """I1: a capability-listed AIO module with no decodable serial gets a synthetic identity.

    The address stays listed in capabilities but its register cache is present-and-empty
    (no valid decode) rather than absent — analogous to the #213 battery/meter placeholder
    path. Without the fallback this would collide with siblings on an empty identity.
    """
    plant = Plant()
    plant.inverter_serial_number = "CH1234G567"
    plant.capabilities = PlantCapabilities(
        device_type=Model.ALL_IN_ONE,
        inverter_address=0x11,
        aio_battery_module_addresses=[0x50, 0x51],
    )
    plant.register_caches[0x11] = RegisterCache()
    plant.register_caches[0x50] = RegisterCache({IR(114 + i): v for i, v in _encode_serial("XX1234A567").items()})
    plant.register_caches[0x51] = RegisterCache()  # present, but serial-less — no valid decode

    rows = plant.devices
    module_rows = {r.identity: r for r in rows if r.device_type is DeviceType.BATTERY_MODULE}
    assert set(module_rows) == {"XX1234A567", "CH1234G567_module_81"}  # 0x51 == 81
    placeholder = module_rows["CH1234G567_module_81"]
    assert placeholder.is_valid is False
    assert placeholder.serial_number is None
    assert module_rows["XX1234A567"].is_valid is True


def test_walk_aio_module_identity_survives_sparse_earlier_address():
    """I1 regression: a missing earlier address must not shift later modules' identities.

    ``aio_battery_modules`` silently skips addresses absent from ``register_caches``
    (0x50 here), so it only yields entries for 0x51 and 0x52. Zipping that shorter list
    against the full address list ``[0x50, 0x51, 0x52]`` mislabels the 0x51 module as
    0x50. Each module carries its own ``module_address`` (set in
    ``AioBatteryModule.from_register_cache``), so the walk must key off that instead of
    positional correspondence with the address list.
    """
    plant = Plant()
    plant.inverter_serial_number = "CH1234G567"
    plant.capabilities = PlantCapabilities(
        device_type=Model.ALL_IN_ONE,
        inverter_address=0x11,
        aio_battery_module_addresses=[0x50, 0x51, 0x52],
    )
    plant.register_caches[0x11] = RegisterCache()
    # 0x50 is absent entirely -> aio_battery_modules() skips it.
    plant.register_caches[0x51] = RegisterCache()  # present, but serial-less
    plant.register_caches[0x52] = RegisterCache({IR(114 + i): v for i, v in _encode_serial("XX1234A567").items()})

    rows = plant.devices
    module_rows = {r.identity: r for r in rows if r.device_type is DeviceType.BATTERY_MODULE}
    # The serial-less module physically at 0x51 must be keyed on its own address (81),
    # not shifted onto the absent 0x50 (80).
    assert set(module_rows) == {"XX1234A567", "CH1234G567_module_81"}
    placeholder = module_rows["CH1234G567_module_81"]
    assert placeholder.is_valid is False
    assert placeholder.serial_number is None
    assert module_rows["XX1234A567"].is_valid is True


def test_walk_hv_bmu_synthetic_identity_when_serial_less():
    """I1: an HV BMU with an absent module cache gets a synthetic identity.

    Keyed off the stack identity and its 1-based index within the stack, instead of
    colliding with its siblings on an empty identity.
    """
    plant = Plant()
    plant.inverter_serial_number = "HV1234A567"
    plant.capabilities = PlantCapabilities(
        device_type=Model.ALL_IN_ONE,
        inverter_address=0x11,
        bcu_stacks=[(0, 2)],  # BCU at 0x70, two BMUs at 0x50/0x51
    )
    plant.register_caches[0x11] = RegisterCache()
    # IR(60-63): BCU pack_software_version -> "HY0001".
    plant.register_caches[0x70] = RegisterCache({IR(60): 0x4859, IR(61): 0, IR(62): 0, IR(63): 1})
    plant.register_caches[0x50] = RegisterCache({IR(114 + i): v for i, v in _encode_serial("XX1234A567").items()})
    # 0x51 (second BMU) has no cache at all; Plant.hv_stacks() decodes it from a default
    # empty RegisterCache() rather than dropping it.

    rows = plant.devices
    stack_identity = f"{plant.inverter_serial_number}_hvstack_0x70"
    bmu_rows = {r.identity: r for r in rows if r.device_type is DeviceType.BATTERY_MODULE}
    assert set(bmu_rows) == {"XX1234A567", f"{stack_identity}_bmu_2"}
    placeholder = bmu_rows[f"{stack_identity}_bmu_2"]
    assert placeholder.is_valid is False
    assert placeholder.serial_number is None


def test_walk_hv_stack_row_is_valid_false_when_bcu_unreachable():
    """M1: an HV_STACK row's is_valid reflects the BCU decode, not a bare default of True."""
    plant = Plant()
    plant.inverter_serial_number = "HV1234A567"
    plant.capabilities = PlantCapabilities(
        device_type=Model.ALL_IN_ONE,
        inverter_address=0x11,
        bcu_stacks=[(0, 0)],  # BCU at 0x70, no BMUs
    )
    plant.register_caches[0x11] = RegisterCache()
    # No cache for 0x70 at all — the BCU hasn't answered.

    rows = plant.devices
    stack_row = next(r for r in rows if r.device_type is DeviceType.HV_STACK)
    assert stack_row.is_valid is False


def test_walk_pins_inverter_and_battery_firmware_versions():
    """M4: root inverter firmware_version (HR19/HR21) and LV-battery firmware_version (IR98).

    Matches ``SinglePhaseInverter.firmware_version``'s ``D0.{dsp}-A0.{arm}`` format for the
    root row, and the battery row's raw ``bms_firmware_version`` stringified.
    """
    plant = _hybrid_plant_two_packs()
    plant.register_caches[0x11].update({HR(19): 5, HR(21): 449})
    plant.register_caches[0x32].update({IR(98): 3005})

    rows = plant.devices
    root = rows[0]
    assert root.firmware_version == "D0.5-A0.449"

    battery_row = next(r for r in rows if r.device_type is DeviceType.BATTERY and r.identity == "XX1234A567")
    assert battery_row.firmware_version == "3005"
