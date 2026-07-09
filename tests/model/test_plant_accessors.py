"""Tests for Plant typed accessors that depend on PlantCapabilities."""

import pytest

from givenergy_modbus.model.hv_bcu import HvStack
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter
from givenergy_modbus.model.meter import Meter
from givenergy_modbus.model.plant import Plant, PlantCapabilities
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register_cache import RegisterCache


def _plant_with_caps(**kwargs) -> Plant:
    plant = Plant()
    plant.capabilities = PlantCapabilities(**kwargs)
    return plant


def _prime(plant: Plant, device_addr: int, registers: dict) -> None:
    if device_addr not in plant.register_caches:
        plant.register_caches[device_addr] = RegisterCache()
    plant.register_caches[device_addr].update(registers)


# ---------------------------------------------------------------------------
# plant.inverter — dispatches via select_inverter when capabilities set
# ---------------------------------------------------------------------------


def test_inverter_falls_back_to_0x11_without_capabilities():
    """Without capabilities, .inverter reads the inverter identity at 0x11, not battery pack 1 at 0x32 (#352)."""
    from givenergy_modbus.model.inverter import SinglePhaseInverter

    plant = Plant()
    # Empty bare Plant: still an empty SinglePhaseInverter, no KeyError (0x11 is not pre-allocated).
    assert isinstance(plant.inverter, SinglePhaseInverter)
    # Inverter serial (HR13-17 → "SA1234G567") lives at 0x11; battery cell data sits at 0x32.
    _prime(plant, 0x11, {HR(13): 0x5341, HR(14): 0x3132, HR(15): 0x3334, HR(16): 0x4735, HR(17): 0x3637})
    _prime(plant, 0x32, {IR(60): 3300})  # battery cell — must not surface through .inverter
    assert plant.inverter.serial_number == "SA1234G567"  # decoded from 0x11, not the 0x32 battery cache


def test_inverter_returns_threephase_for_threephase_model():
    plant = _plant_with_caps(device_type=Model.HYBRID_3PH, inverter_address=0x32)
    assert isinstance(plant.inverter, ThreePhaseInverter)


def test_inverter_tolerates_unpopulated_inverter_address_cache():
    """.inverter must not KeyError when its address cache isn't populated yet.

    A pre-#189 persisted capability may still point at the 0x31 facade, which detect()
    doesn't populate (it reads identity at 0x11), so .inverter would otherwise KeyError
    between detect() and the first poll (#119, #189).
    """
    from givenergy_modbus.model.inverter import SinglePhaseInverter

    plant = _plant_with_caps(device_type=Model.HYBRID_GEN1, inverter_address=0x31)  # pre-#189 persisted state
    assert plant.capabilities.inverter_address == 0x31
    assert 0x31 not in plant.register_caches  # nothing cached there yet
    assert isinstance(plant.inverter, SinglePhaseInverter)  # no KeyError


# ---------------------------------------------------------------------------
# plant.batteries — uses lv_battery_addresses when capabilities set
# ---------------------------------------------------------------------------


def test_batteries_uses_capabilities_address_list():
    plant = _plant_with_caps(device_type=Model.HYBRID, lv_battery_addresses=[0x32, 0x33])
    _prime(plant, 0x32, {IR(60): 1})
    _prime(plant, 0x33, {IR(60): 1})
    assert len(plant.batteries) == 2


def test_batteries_skips_missing_caches():
    plant = _plant_with_caps(device_type=Model.HYBRID, lv_battery_addresses=[0x32, 0x33])
    _prime(plant, 0x32, {IR(60): 1})
    # 0x33 cache absent — should not raise, just omit it.
    assert len(plant.batteries) == 1


def test_number_batteries_uses_capabilities():
    plant = _plant_with_caps(device_type=Model.HYBRID, lv_battery_addresses=[0x32, 0x33])
    assert plant.number_batteries == 2


def test_batteries_empty_without_capabilities_and_no_valid_data():
    plant = Plant()
    assert plant.batteries == []


# ---------------------------------------------------------------------------
# plant.remaining_battery_energy_wh — per-dongle nominal sum (#374)
# ---------------------------------------------------------------------------

_PACK_A = {IR(97): 16, IR(88): 0, IR(89): 4781, IR(82): 0, IR(83): 52203}  # 47.81 Ah, 16S → 2448 Wh
_PACK_B = {IR(97): 16, IR(88): 0, IR(89): 5155, IR(82): 0, IR(83): 52700}  # 51.55 Ah, 16S → 2639 Wh


def test_remaining_battery_energy_wh_sums_packs_on_the_dongle():
    """Sums remaining_energy_nominal_wh across all packs — the primary/secondary chain IR2091 drops."""
    plant = _plant_with_caps(device_type=Model.HYBRID, lv_battery_addresses=[0x32, 0x33])
    _prime(plant, 0x32, _PACK_A)
    _prime(plant, 0x33, _PACK_B)
    assert plant.remaining_battery_energy_wh == 2448 + 2639  # 5087


def test_remaining_battery_energy_wh_none_when_no_batteries():
    """An EMS-dongle Plant (no LV battery sub-bus) returns None, not 0 — signals 'sum the inverters'."""
    assert Plant().remaining_battery_energy_wh is None


def test_remaining_battery_energy_wh_skips_undecodable_packs():
    """A pack whose energy can't be computed is skipped, not counted as 0."""
    plant = _plant_with_caps(device_type=Model.HYBRID, lv_battery_addresses=[0x32, 0x33])
    _prime(plant, 0x32, _PACK_A)
    _prime(plant, 0x33, {IR(60): 1})  # present but no cap_remaining → remaining_energy is None
    assert plant.remaining_battery_energy_wh == 2448


def test_remaining_battery_energy_wh_is_attribute_only_not_in_model_dump():
    """Derived accessor: attribute-accessible but excluded from the raw-state model_dump,
    consistent with the sibling device accessors (inverter/batteries/ems/hv_stacks). A
    SOC-varying derivation does not belong in the plant's dumpable/persistable state."""
    plant = _plant_with_caps(device_type=Model.HYBRID, lv_battery_addresses=[0x32])
    _prime(plant, 0x32, _PACK_A)
    assert plant.remaining_battery_energy_wh == 2448  # attribute access works
    assert "remaining_battery_energy_wh" not in plant.model_dump()


@pytest.mark.timeout(15)
def test_remaining_battery_energy_wh_fixture_backed():
    """Real 2x Giv-Bat 5.2 capture: the two packs sum to ~5087 Wh nominal (#374)."""
    from pathlib import Path

    from givenergy_modbus.testing.mock_plant import plant_from_capture

    cap = Path(__file__).parents[1] / "fixtures" / "captures" / "ems_2_inv_3_bat_a" / "ac_arm282_2x_givbat52_30min.log"
    plant = plant_from_capture(cap)
    plant.capabilities = PlantCapabilities(device_type=Model.AC, lv_battery_addresses=[0x32, 0x33])
    assert plant.remaining_battery_energy_wh == 5087


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
    plant = _plant_with_caps(device_type=Model.ALL_IN_ONE, bcu_stacks=[(0, 2), (1, 3)])
    _prime(plant, 0x70, {IR(64): 2})
    _prime(plant, 0x71, {IR(64): 3})
    stacks = plant.hv_stacks
    assert len(stacks) == 2
    assert all(isinstance(s, HvStack) for s in stacks)
    assert stacks[0].device_address == 0x70
    assert stacks[1].device_address == 0x71
    assert len(stacks[0].bmus) == 2
    assert len(stacks[1].bmus) == 3


def test_hv_stacks_decodes_bmus_from_own_address_caches():
    # #265: each BMU decodes from its own device-address cache (0x50 + running index), NOT a
    # stride within the BCU cache. A two-module stack → BMUs at 0x50, 0x51.
    plant = _plant_with_caps(device_type=Model.HYBRID_HV_GEN3, bcu_stacks=[(0, 2)])
    _prime(plant, 0x70, {IR(64): 2})  # BCU cluster: 2 modules
    _prime(plant, 0x50, {IR(60): 3200, IR(90): 250})  # BMU 0: v_cell_01=3.2 V, t_cell_01=25.0 °C
    _prime(plant, 0x51, {IR(60): 3300, IR(90): 260})  # BMU 1: v_cell_01=3.3 V, t_cell_01=26.0 °C
    bmus = plant.hv_stacks[0].bmus
    assert len(bmus) == 2
    assert bmus[0].bmu_index == 0
    assert bmus[0].v_cell_01 == pytest.approx(3.2)
    assert bmus[0].t_cell_01 == pytest.approx(25.0)
    assert bmus[1].bmu_index == 1
    assert bmus[1].v_cell_01 == pytest.approx(3.3)
    assert bmus[1].t_cell_01 == pytest.approx(26.0)


def test_hv_stacks_bmu_does_not_read_bcu_cluster_registers():
    # Regression for the #265 bug: the BCU cluster cache (0x70) carries pack_software_version,
    # counts and cluster V/I/SoC at IR(60-105). With no per-module 0x50+ cache primed, BMUs must
    # decode to None — they must not mistake the BCU's own registers for cell data.
    plant = _plant_with_caps(device_type=Model.HYBRID_HV_GEN3, bcu_stacks=[(0, 1)])
    _prime(plant, 0x70, {IR(60): 1234, IR(67): 3300, IR(90): 250})  # BCU cluster regs, not cells
    bmus = plant.hv_stacks[0].bmus
    assert len(bmus) == 1
    assert bmus[0].v_cell_01 is None
    assert bmus[0].is_valid() is False


# ---------------------------------------------------------------------------
# plant.meters
# ---------------------------------------------------------------------------


def test_meters_empty_without_capabilities():
    plant = Plant()
    assert plant.meters == {}


def test_meters_empty_when_no_meter_addresses():
    plant = _plant_with_caps(device_type=Model.HYBRID, meter_addresses=[])
    assert plant.meters == {}


def test_meters_returns_dict_keyed_by_address():
    plant = _plant_with_caps(device_type=Model.HYBRID, meter_addresses=[0x01, 0x02])
    _prime(plant, 0x01, {IR(60): 100})
    _prime(plant, 0x02, {IR(60): 200})
    meters = plant.meters
    assert set(meters.keys()) == {0x01, 0x02}
    assert all(isinstance(m, Meter) for m in meters.values())


def test_meters_skips_missing_caches():
    plant = _plant_with_caps(device_type=Model.HYBRID, meter_addresses=[0x01, 0x02])
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


# ---------------------------------------------------------------------------
# plant.lv_bcu — present only when capabilities carry lv_bcu_address (#241)
# ---------------------------------------------------------------------------


def test_lv_bcu_none_without_capabilities():
    assert Plant().lv_bcu is None


def test_lv_bcu_none_when_not_detected():
    plant = _plant_with_caps(device_type=Model.HYBRID, lv_battery_addresses=[0x32])
    assert plant.lv_bcu is None


def test_lv_bcu_none_when_cache_unpopulated():
    """No KeyError between detect() and the first poll of the BCU page."""
    plant = _plant_with_caps(device_type=Model.HYBRID, lv_bcu_address=0x31)
    assert 0x31 not in plant.register_caches
    assert plant.lv_bcu is None


def test_lv_bcu_decodes_from_cache():
    from givenergy_modbus.model.lv_bcu import LvBcu

    plant = _plant_with_caps(device_type=Model.HYBRID, lv_bcu_address=0x31)
    _prime(plant, 0x31, {IR(60): 0, IR(61): 0, IR(62): 167, IR(63): 167})
    bcu = plant.lv_bcu
    assert isinstance(bcu, LvBcu)
    assert bcu.request_charge_current == 167
    assert bcu.request_discharge_current == 167


def test_lv_bcu_decode_error_returns_none(caplog):
    """A malformed cache raises during decode — must return None, not propagate (#241)."""
    import logging
    from unittest.mock import patch

    plant = _plant_with_caps(device_type=Model.HYBRID, lv_bcu_address=0x31)
    _prime(plant, 0x31, {IR(60): 1})
    with patch("givenergy_modbus.model.plant.LvBcu.from_register_cache", side_effect=RuntimeError("oops")):
        with caplog.at_level(logging.ERROR):
            result = plant.lv_bcu
    assert result is None
    assert "Failed to decode LV BCU" in caplog.text
