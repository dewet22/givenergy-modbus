import pytest

from givenergy_modbus.model.register import Type
from givenergy_modbus.model.register_banks import HoldingRegister, InputRegister


def test_lookup():
    """Ensure we can look up registers by index, instead of the complex type they're defined as."""
    assert InputRegister(0) == InputRegister.INVERTER_STATUS
    with pytest.raises(TypeError) as e:
        InputRegister(0, Type.WORD)
    assert e.value.args[0] == 'Cannot extend enumerations'

    assert HoldingRegister(0) == HoldingRegister.DEVICE_TYPE_CODE
    with pytest.raises(TypeError) as e:
        HoldingRegister(0, Type.WORD)
    assert e.value.args[0] == 'Cannot extend enumerations'


def test_comparison():
    """Ensure registers from different banks aren't comparable."""
    assert HoldingRegister(0) != InputRegister(0)


@pytest.mark.parametrize("val", [0, 0x32, 0x7FFF, 0x8000, 0xFFFF])
@pytest.mark.parametrize("scaling", [1000, 10, 1, 0.1, 0.01])
def test_render(val: int, scaling: float):
    """Ensure we render types correctly."""
    assert Type.WORD.render(val, scaling) == val * scaling

    if val > 0x7FFF:  # this should be negative
        assert Type.SWORD.render(val, scaling) == (val - 2 ** 16) * scaling
    else:
        assert Type.SWORD.render(val, scaling) == val * scaling

    assert Type.DWORD_LOW.render(val, scaling) == val * scaling
    assert Type.DWORD_HIGH.render(val, scaling) == (val * 2 ** 16) * scaling

    # scaling doesn't make sense for ascii types
    # non-ascii values will not decode properly
    if val // 256 < 128 and val % 256 < 128:
        assert Type.ASCII.render(val, scaling) == val.to_bytes(2, byteorder='big').decode(encoding='ascii')
    else:
        with pytest.raises(UnicodeDecodeError) as e:
            Type.ASCII.render(val, scaling)
        assert e.value.args[0] == 'ascii'
        assert e.value.args[4] == 'ordinal not in range(128)'

    # the assumption is that booleans are simply the LSB being set
    assert Type.BOOL.render(val, scaling) is bool(val & 0x1)
