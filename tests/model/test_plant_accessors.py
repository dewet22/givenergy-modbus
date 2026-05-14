"""Tests for Plant typed accessors that depend on PlantCapabilities."""

from givenergy_modbus.model.hv_bcu import HvStack
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
from givenergy_modbus.model.meter import Meter
from givenergy_modbus.model.plant import Plant, PlantCapabilities
from givenergy_modbus.model.register import IR
from givenergy_modbus.model.register_cache import RegisterCache


def _plant_with_caps(**kwargs) -> Plant:
    plant = Plant()
    plant.capabilities = PlantCapabilities(**kwargs)
    return plant


def _prime(plant: Plant, slave: int, registers: dict) -> None:
    if slave not in plant.register_caches:
        plant.register_caches[slave] = RegisterCache()
    plant.register_caches[slave].update(registers)


# ---------------------------------------------------------------------------
# plant.inverter — dispatches via select_inverter when capabilities set
# ---------------------------------------------------------------------------


def test_inverter_falls_back_without_capabilities():
    plant = Plant()
    # No capabilities: returns SinglePhaseInverter from 0x32 cache as before.
    from givenergy_modbus.model.inverter import SinglePhaseInverter

    assert isinstance(plant.inverter, SinglePhaseInverter)


def test_inverter_returns_threephase_for_threephase_model():
    plant = _plant_with_caps(device_type=Model.HYBRID_3PH, inverter_slave=0x32)
    assert isinstance(plant.inverter, ThreePhaseInverter)


# ---------------------------------------------------------------------------
# plant.batteries — uses lv_battery_slaves when capabilities set
# ---------------------------------------------------------------------------


def test_batteries_uses_capabilities_slave_list():
    plant = _plant_with_caps(device_type=Model.HYBRID, lv_battery_slaves=[0x32, 0x33])
    _prime(plant, 0x32, {IR(60): 1})
    _prime(plant, 0x33, {IR(60): 1})
    assert len(plant.batteries) == 2


def test_batteries_skips_missing_caches():
    plant = _plant_with_caps(device_type=Model.HYBRID, lv_battery_slaves=[0x32, 0x33])
    _prime(plant, 0x32, {IR(60): 1})
    # 0x33 cache absent — should not raise, just omit it.
    assert len(plant.batteries) == 1


def test_number_batteries_uses_capabilities():
    plant = _plant_with_caps(device_type=Model.HYBRID, lv_battery_slaves=[0x32, 0x33])
    assert plant.number_batteries == 2


def test_batteries_empty_without_capabilities_and_no_valid_data():
    plant = Plant()
    assert plant.batteries == []


# ---------------------------------------------------------------------------
# plant.hv_stacks
# ---------------------------------------------------------------------------


def test_hv_stacks_empty_for_lv_system():
    plant = _plant_with_caps(device_type=Model.HYBRID)
    assert plant.hv_stacks == []


def test_hv_stacks_empty_without_capabilities():
    plant = Plant()
    assert plant.hv_stacks == []


def test_hv_stacks_returns_stack_per_bcu():
    plant = _plant_with_caps(device_type=Model.ALL_IN_ONE, bcu_slaves=[(0, 2), (1, 3)])
    _prime(plant, 0x70, {IR(64): 2})
    _prime(plant, 0x71, {IR(64): 3})
    stacks = plant.hv_stacks
    assert len(stacks) == 2
    assert all(isinstance(s, HvStack) for s in stacks)
    assert stacks[0].slave_address == 0x70
    assert stacks[1].slave_address == 0x71
    assert len(stacks[0].bmus) == 2
    assert len(stacks[1].bmus) == 3


# ---------------------------------------------------------------------------
# plant.meters
# ---------------------------------------------------------------------------


def test_meters_empty_without_capabilities():
    plant = Plant()
    assert plant.meters == {}


def test_meters_empty_when_no_meter_slaves():
    plant = _plant_with_caps(device_type=Model.HYBRID, meter_slaves=[])
    assert plant.meters == {}


def test_meters_returns_dict_keyed_by_slave():
    plant = _plant_with_caps(device_type=Model.HYBRID, meter_slaves=[0x01, 0x02])
    _prime(plant, 0x01, {IR(60): 100})
    _prime(plant, 0x02, {IR(60): 200})
    meters = plant.meters
    assert set(meters.keys()) == {0x01, 0x02}
    assert all(isinstance(m, Meter) for m in meters.values())


def test_meters_skips_missing_caches():
    plant = _plant_with_caps(device_type=Model.HYBRID, meter_slaves=[0x01, 0x02])
    _prime(plant, 0x01, {IR(60): 100})
    # 0x02 absent — only one meter returned.
    assert set(plant.meters.keys()) == {0x01}


# ---------------------------------------------------------------------------
# plant.ems
# ---------------------------------------------------------------------------


def test_ems_none_for_non_ems_device():
    plant = _plant_with_caps(device_type=Model.HYBRID)
    assert plant.ems is None


def test_ems_none_without_capabilities():
    plant = Plant()
    assert plant.ems is None


def test_ems_returned_for_ems_device():
    from givenergy_modbus.model.ems import Ems

    plant = _plant_with_caps(device_type=Model.EMS)
    ems = plant.ems
    assert isinstance(ems, Ems)


def test_ems_returned_for_ems_commercial():
    from givenergy_modbus.model.ems import Ems

    plant = _plant_with_caps(device_type=Model.EMS_COMMERCIAL)
    assert isinstance(plant.ems, Ems)


# ---------------------------------------------------------------------------
# plant.gateway
# ---------------------------------------------------------------------------


def test_gateway_none_for_non_gateway_device():
    plant = _plant_with_caps(device_type=Model.HYBRID)
    assert plant.gateway is None


def test_gateway_none_without_capabilities():
    plant = Plant()
    assert plant.gateway is None


def test_gateway_returned_for_gateway_device():
    from givenergy_modbus.model.gateway import GatewayV1, GatewayV2

    plant = _plant_with_caps(device_type=Model.GATEWAY)
    gw = plant.gateway
    assert isinstance(gw, (GatewayV1, GatewayV2))
