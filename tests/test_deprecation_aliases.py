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
from givenergy_modbus.pdu import ReadInputRegistersRequest, WriteHoldingRegisterRequest


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


def test_write_holding_register_request_slave_address_kwarg_warns_and_maps():
    """WriteHoldingRegisterRequest has its own __init__ wrapping the base; legacy kwarg must still flow through."""
    with pytest.warns(DeprecationWarning, match="slave_address is deprecated"):
        req = WriteHoldingRegisterRequest(register=20, value=1, slave_address=0x33)
    assert req.device_address == 0x33


def test_write_holding_register_request_defaults_to_0x11():
    """When neither device_address nor slave_address is passed, the address defaults to 0x11."""
    req = WriteHoldingRegisterRequest(register=20, value=1)
    assert req.device_address == 0x11


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


def test_capabilities_unexpected_kwarg_raises():
    # Pydantic raises ValidationError (a ValueError subclass) rather than TypeError
    # for extra inputs — the rejection contract is preserved, the error type changed
    # as part of the v2.1 Pydantic migration (#72).
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PlantCapabilities(device_type=Model.HYBRID, nonexistent=42)


def test_capabilities_positional_args_work():
    """Positional-arg construction is preserved across the Pydantic migration.

    The historic dataclass form supported positional args; the Pydantic
    migration's custom __init__ preserves that for external callers who may
    have written PlantCapabilities(Model.HYBRID, 0x32, [0x01], ...) directly.
    """
    caps = PlantCapabilities(Model.HYBRID, 0x33, [0x01], [0x35], [(0, 2)])
    assert caps.device_type == Model.HYBRID
    assert caps.inverter_address == 0x33
    assert caps.meter_addresses == [0x01]
    assert caps.lv_battery_addresses == [0x35]
    assert caps.bcu_stacks == [(0, 2)]


def test_capabilities_model_validate_still_handles_legacy_keys():
    """model_validate() must still apply legacy alias mapping.

    model_validate() bypasses __init__, so the model_validator must catch
    legacy *_slave(s) keys arriving via that path too.
    """
    with pytest.warns(DeprecationWarning, match="inverter_slave is deprecated"):
        caps = PlantCapabilities.model_validate({"device_type": Model.HYBRID, "inverter_slave": 0x33})
    assert caps.inverter_address == 0x33


def test_capabilities_legacy_setters_warn_and_assign():
    """Setting a legacy property must update the canonical field and emit a DeprecationWarning."""
    caps = PlantCapabilities(device_type=Model.HYBRID)
    with pytest.warns(DeprecationWarning, match="inverter_slave is deprecated"):
        caps.inverter_slave = 0x55
    assert caps.inverter_address == 0x55

    with pytest.warns(DeprecationWarning, match="meter_slaves is deprecated"):
        caps.meter_slaves = [0x02]
    assert caps.meter_addresses == [0x02]

    with pytest.warns(DeprecationWarning, match="lv_battery_slaves is deprecated"):
        caps.lv_battery_slaves = [0x34]
    assert caps.lv_battery_addresses == [0x34]

    with pytest.warns(DeprecationWarning, match="bcu_slaves is deprecated"):
        caps.bcu_slaves = [(0, 4)]
    assert caps.bcu_stacks == [(0, 4)]


def test_capabilities_to_dict_format():
    """Serialised form uses hex address strings, Model.name, and includes schema_version."""
    caps = PlantCapabilities(
        device_type=Model.HYBRID,
        inverter_address=0x32,
        meter_addresses=[0x01],
        lv_battery_addresses=[0x33],
        bcu_stacks=[(0, 2)],
    )
    assert caps.to_dict() == {
        "schema_version": 1,
        "device_type": "HYBRID",
        "inverter_address": "0x32",
        "meter_addresses": ["0x01"],
        "lv_battery_addresses": ["0x33"],
        "bcu_stacks": [[0, 2]],
    }


def test_capabilities_from_dict_rejects_unknown_schema_version():
    with pytest.raises(ValueError, match="unsupported PlantCapabilities schema_version"):
        PlantCapabilities.from_dict({"schema_version": 999, "device_type": "HYBRID"})


def test_capabilities_from_dict_ignores_unknown_keys():
    """Forward-compat: unknown keys are silently ignored."""
    caps = PlantCapabilities.from_dict(
        {
            "schema_version": 1,
            "device_type": "HYBRID",
            "inverter_address": "0x32",
            "meter_addresses": [],
            "lv_battery_addresses": [],
            "bcu_stacks": [],
            "future_field": "ignored",
        }
    )
    assert caps.device_type == Model.HYBRID


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


def test_hv_stack_slave_address_setter_warns_and_assigns():
    bcu = Bcu.from_register_cache(RegisterCache())
    stack = HvStack(bcu=bcu, device_address=0x70)
    with pytest.warns(DeprecationWarning, match="HvStack.slave_address is deprecated"):
        stack.slave_address = 0x71
    assert stack.device_address == 0x71


def test_hv_stack_both_kwargs_raises():
    bcu = Bcu.from_register_cache(RegisterCache())
    with pytest.raises(TypeError, match="not both"):
        HvStack(bcu=bcu, device_address=0x70, slave_address=0x71)


def test_hv_stack_missing_address_raises():
    bcu = Bcu.from_register_cache(RegisterCache())
    with pytest.raises(TypeError, match="missing required argument: device_address"):
        HvStack(bcu=bcu)


def test_hv_stack_missing_bcu_raises():
    with pytest.raises(TypeError, match="missing required argument: bcu"):
        HvStack(device_address=0x70)


def test_hv_stack_positional_args_compatible_with_pre_rename_order():
    """Legacy callers using positional args (slave_address, bcu) must still work after the rename."""
    bcu = Bcu.from_register_cache(RegisterCache())
    stack = HvStack(0x70, bcu)
    assert stack.device_address == 0x70
    assert stack.bcu is bcu
    assert stack.bmus == []
