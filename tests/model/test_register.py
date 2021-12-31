import pytest

from givenergy_modbus.model.register import InputRegisterBank, Scaling, Type


def test_lookup():
    """Ensure we can look up registers by index, instead of the complex type they're defined as."""
    assert InputRegisterBank(0) == InputRegisterBank.INV_STATUS
    with pytest.raises(TypeError) as e:
        InputRegisterBank(0, Type.WORD, Scaling.UNIT) == InputRegisterBank.INVERTER_STATUS
    assert e.value.args[0] == '__call__() takes from 2 to 3 positional arguments but 4 were given'
