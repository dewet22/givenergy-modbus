"""Tests for ``Plant.devices`` — the typed-device enumeration API (#106 Phase 1).

These verify three things in concert: correct typed enumeration, no
mis-classification (an EMS / gateway controller must never surface as an
inverter), and that the existing ``Plant`` accessors are untouched (the API
is strictly additive). Plants are constructed in-memory, matching the idiom
in ``test_devices.py`` for the ``Plant.inverters`` tests.
"""

from givenergy_modbus.model.devices import DeviceType, Inverter
from givenergy_modbus.model.ems import Ems
from givenergy_modbus.model.gateway import GatewayV1, GatewayV2
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.plant import Plant, PlantCapabilities
from givenergy_modbus.model.register import IR
from givenergy_modbus.model.register_cache import RegisterCache
from tests.model.test_devices import _add_rollup_slot, _encode_serial


def _battery_cache(serial: str) -> RegisterCache:
    """A battery register cache carrying a valid serial in IR(110..114)."""
    return RegisterCache({IR(110 + i): v for i, v in _encode_serial(serial).items()})


def test_devices_ems_plant_enumerates_managed_inverters_and_ems_without_misclassification():
    """EMS plant: managed inverters become INVERTER rows; the EMS is its own EMS row.

    The headline #106 fix — an EMS controller must NEVER appear as an INVERTER
    row (hass#52). Two managed slots → two INVERTER rows + exactly one EMS row,
    and no inverter row ever wraps the Ems.
    """
    values: dict = {IR(2040): 1, IR(2044): 2}
    _add_rollup_slot(values, 1, serial="XX1234A567", power=1800, soc=65)
    _add_rollup_slot(values, 2, serial="ZZ9876B543", power=2200, soc=78)
    plant = Plant()
    plant.capabilities = PlantCapabilities(device_type=Model.EMS, inverter_address=0x32)
    plant.register_caches[0x32] = RegisterCache(values)

    devices = plant.devices
    by_type = [d.device_type for d in devices]

    assert by_type.count(DeviceType.INVERTER) == 2
    assert by_type.count(DeviceType.EMS) == 1
    assert DeviceType.GATEWAY not in by_type

    inverter_rows = [d for d in devices if d.device_type is DeviceType.INVERTER]
    assert {d.serial_number for d in inverter_rows} == {"XX1234A567", "ZZ9876B543"}
    assert all(isinstance(d.device, Inverter) for d in inverter_rows)
    # No mis-classification: the EMS is never wrapped as an inverter.
    assert not any(isinstance(d.device, Ems) for d in inverter_rows)
    # Blinded managed inverters have an unknown own-model (the plant model is EMS).
    assert all(d.model is None for d in inverter_rows)

    ems_row = next(d for d in devices if d.device_type is DeviceType.EMS)
    assert isinstance(ems_row.device, Ems)
    assert ems_row.model is Model.EMS


def test_devices_batteries_are_typed_rows_with_serials_and_back_compat_preserved():
    """Non-EMS plant: one INVERTER row plus a BATTERY row per pack, with serials.

    The legacy ``Plant.batteries`` accessor stays untouched (same list, same
    types) — proving the enumeration is purely additive.
    """
    plant = Plant()
    plant.capabilities = PlantCapabilities(
        device_type=Model.HYBRID_GEN3,
        inverter_address=0x31,
        lv_battery_addresses=[0x32, 0x33],
    )
    plant.register_caches[0x32] = _battery_cache("XX1234A567")
    plant.register_caches[0x33] = _battery_cache("ZZ9876B543")

    devices = plant.devices

    assert [d.device_type for d in devices].count(DeviceType.INVERTER) == 1
    battery_rows = [d for d in devices if d.device_type is DeviceType.BATTERY]
    assert {d.serial_number for d in battery_rows} == {"XX1234A567", "ZZ9876B543"}

    # Back-compat: legacy accessor unchanged.
    assert len(plant.batteries) == 2
    assert {b.serial_number for b in plant.batteries} == {"XX1234A567", "ZZ9876B543"}


def test_devices_gateway_plant_emits_single_gateway_row_and_no_spurious_inverter():
    """Gateway plant: exactly one GATEWAY row and ZERO inverter rows.

    On a gateway plant the singular ``Plant.inverter`` decodes the gateway's
    own cache as an inverter — a spurious row. ``Plant.devices`` suppresses it.
    """
    plant = Plant()
    plant.capabilities = PlantCapabilities(device_type=Model.GATEWAY, inverter_address=0x11)
    plant.register_caches[0x11] = RegisterCache()

    devices = plant.devices
    by_type = [d.device_type for d in devices]

    assert by_type.count(DeviceType.GATEWAY) == 1
    assert DeviceType.INVERTER not in by_type
    gw_row = next(d for d in devices if d.device_type is DeviceType.GATEWAY)
    assert isinstance(gw_row.device, (GatewayV1, GatewayV2))
    assert gw_row.model is Model.GATEWAY


def test_devices_enumerates_meters_and_hv_stacks_with_correct_types():
    """Meters and HV stacks surface as typed rows (serials optional this phase)."""
    plant = Plant()
    plant.capabilities = PlantCapabilities(
        device_type=Model.HYBRID_GEN3,
        inverter_address=0x11,
        meter_addresses=[0x01],
        bcu_stacks=[(0, 2)],
    )
    plant.register_caches[0x11] = RegisterCache()
    plant.register_caches[0x01] = RegisterCache()
    plant.register_caches[0x70] = RegisterCache()

    by_type = [d.device_type for d in plant.devices]
    assert by_type.count(DeviceType.METER) == 1
    assert by_type.count(DeviceType.HV_STACK) == 1
