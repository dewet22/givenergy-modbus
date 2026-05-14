"""Coverage for the slave_address → device_address terminology aliases.

Modbus.org adopted client/server terminology in 2020, replacing master/slave. This
library follows suit; the legacy `slave`-based names are retained as deprecated
aliases so downstream consumers (givenergy-hass, givenergy-cli) have a soft
landing.

These tests pin down: kwargs accepted in both forms, attribute reads emit a warning,
and the two paths return the same underlying value. When the aliases are eventually
removed, these tests can be deleted alongside the alias code.
"""

import warnings

import pytest

from givenergy_modbus.model.hv_bcu import Bcu, HvStack
from givenergy_modbus.model.inverter import Model
from givenergy_modbus.model.plant import PlantCapabilities
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import ReadInputRegistersRequest


def test_pdu_slave_address_kwarg_warns_and_maps():
    with pytest.warns(DeprecationWarning, match="slave_address is deprecated"):
        req = ReadInputRegistersRequest(base_register=0, register_count=60, slave_address=0x33)
    assert req.device_address == 0x33


def test_pdu_device_address_kwarg_is_silent():
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning would fail the test
        req = ReadInputRegistersRequest(base_register=0, register_count=60, device_address=0x33)
    assert req.device_address == 0x33


def test_pdu_slave_address_property_read_warns():
    req = ReadInputRegistersRequest(base_register=0, register_count=60, device_address=0x33)
    with pytest.warns(DeprecationWarning, match="slave_address is deprecated"):
        value = req.slave_address
    assert value == 0x33


def test_pdu_slave_address_property_set_warns():
    req = ReadInputRegistersRequest(base_register=0, register_count=60, device_address=0x33)
    with pytest.warns(DeprecationWarning, match="slave_address is deprecated"):
        req.slave_address = 0x55
    assert req.device_address == 0x55


def test_pdu_both_kwargs_raises():
    with pytest.raises(TypeError, match="not both"):
        ReadInputRegistersRequest(base_register=0, register_count=60, device_address=0x33, slave_address=0x55)


def test_capabilities_legacy_kwargs_warn():
    with pytest.warns(DeprecationWarning, match="inverter_slave is deprecated"):
        caps = PlantCapabilities(device_type=Model.HYBRID, inverter_slave=0x33)
    assert caps.inverter_address == 0x33

    with pytest.warns(DeprecationWarning, match="meter_slaves is deprecated"):
        caps = PlantCapabilities(device_type=Model.HYBRID, meter_slaves=[0x01])
    assert caps.meter_addresses == [0x01]

    with pytest.warns(DeprecationWarning, match="lv_battery_slaves is deprecated"):
        caps = PlantCapabilities(device_type=Model.HYBRID, lv_battery_slaves=[0x33])
    assert caps.lv_battery_addresses == [0x33]

    with pytest.warns(DeprecationWarning, match="bcu_slaves is deprecated"):
        caps = PlantCapabilities(device_type=Model.ALL_IN_ONE, bcu_slaves=[(0, 3)])
    assert caps.bcu_stacks == [(0, 3)]


def test_capabilities_legacy_properties_warn_on_read():
    caps = PlantCapabilities(
        device_type=Model.HYBRID,
        inverter_address=0x32,
        meter_addresses=[0x01],
        lv_battery_addresses=[0x33],
        bcu_stacks=[(0, 2)],
    )
    with pytest.warns(DeprecationWarning, match="inverter_slave is deprecated"):
        assert caps.inverter_slave == 0x32
    with pytest.warns(DeprecationWarning, match="meter_slaves is deprecated"):
        assert caps.meter_slaves == [0x01]
    with pytest.warns(DeprecationWarning, match="lv_battery_slaves is deprecated"):
        assert caps.lv_battery_slaves == [0x33]
    with pytest.warns(DeprecationWarning, match="bcu_slaves is deprecated"):
        assert caps.bcu_slaves == [(0, 2)]


def test_capabilities_both_kwarg_forms_raises():
    with pytest.raises(TypeError, match="not both"):
        PlantCapabilities(device_type=Model.HYBRID, inverter_address=0x32, inverter_slave=0x32)


def test_capabilities_from_dict_accepts_legacy_keys():
    """Persisted state from older versions uses *_slave(s) keys; from_dict must still load it."""
    legacy = {
        "device_type": Model.HYBRID.value,
        "inverter_slave": 0x32,
        "meter_slaves": [0x01],
        "lv_battery_slaves": [0x33],
        "bcu_slaves": [[0, 2]],
    }
    caps = PlantCapabilities.from_dict(legacy)
    assert caps.inverter_address == 0x32
    assert caps.meter_addresses == [0x01]
    assert caps.lv_battery_addresses == [0x33]
    assert caps.bcu_stacks == [(0, 2)]


def test_capabilities_to_dict_uses_new_keys():
    caps = PlantCapabilities(
        device_type=Model.HYBRID,
        inverter_address=0x32,
        meter_addresses=[0x01],
        lv_battery_addresses=[0x33],
        bcu_stacks=[(0, 2)],
    )
    assert set(caps.to_dict().keys()) == {
        "device_type",
        "inverter_address",
        "meter_addresses",
        "lv_battery_addresses",
        "bcu_stacks",
    }


def test_hv_stack_slave_address_kwarg_warns():
    bcu = Bcu.from_register_cache(RegisterCache())
    with pytest.warns(DeprecationWarning, match="HvStack.slave_address is deprecated"):
        stack = HvStack(bcu=bcu, slave_address=0x70)
    assert stack.device_address == 0x70


def test_hv_stack_slave_address_property_read_warns():
    bcu = Bcu.from_register_cache(RegisterCache())
    stack = HvStack(bcu=bcu, device_address=0x70)
    with pytest.warns(DeprecationWarning, match="HvStack.slave_address is deprecated"):
        assert stack.slave_address == 0x70
