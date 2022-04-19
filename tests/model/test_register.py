# type: ignore  # shut up mypy, this whole file is just a minefield
import datetime
from typing import Dict

import pytest

from givenergy_modbus.model.register import HoldingRegister, InputRegister, Register, ScalingFactor, Type, Unit

# fmt: off
INPUT_REGISTERS: Dict[int, int] = dict(enumerate([
    0, 14, 10, 70, 0, 2367, 0, 1832, 0, 0,  # 00x
    0, 0, 159, 4990, 0, 12, 4790, 4, 0, 5,  # 01x
    0, 0, 6, 0, 0, 0, 209, 0, 946, 0,  # 02x
    65194, 0, 0, 3653, 0, 93, 90, 89, 30, 0,  # 03x
    0, 222, 342, 680, 81, 0, 930, 0, 213, 1,  # 04x
    4991, 0, 0, 2356, 4986, 223, 170, 0, 292, 4,  # 05x

    3117, 3124, 3129, 3129, 3125, 3130, 3122, 3116, 3111, 3105,  # 06x
    3119, 3134, 3146, 3116, 3135, 3119, 175, 167, 171, 161,  # 07x
    49970, 172, 0, 50029, 0, 19097, 0, 16000, 0, 1804,  # 08x
    0, 1552, 256, 0, 0, 0, 12, 16, 3005, 0,  # 09x
    9, 0, 16000, 174, 167, 1696, 1744, 0, 0, 0,  # 10x
    16967, 12594, 13108, 18229, 13879, 8, 0, 0, 0, 0,  # 11x

    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 12x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 13x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 14x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 15x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 16x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 17x
    1696, 1744, 89, 90, 0, 0, 0, 0, 0, 0,  # 18x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 19x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 20x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 21x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 22x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 23x
]))
HOLDING_REGISTERS: Dict[int, int] = dict(enumerate([
    8193, 3, 2098, 513, 0, 50000, 3600, 1, 16967, 12594,  # 00x
    13108, 18229, 13879, 21313, 12594, 13108, 18229, 13879, 3005, 449,  # 01x
    1, 449, 2, 0, 32768, 30235, 6000, 1, 0, 0,  # 02x
    17, 0, 4, 7, 140, 22, 1, 1, 23, 57,  # 03x
    19, 1, 2, 0, 0, 0, 101, 1, 0, 0,  # 04x
    100, 0, 0, 1, 1, 160, 0, 0, 1, 0,  # 05x
    1500, 30, 30, 1840, 2740, 4700, 5198, 126, 27, 24,  # 06x
    28, 1840, 2620, 4745, 5200, 126, 52, 1, 28, 1755,  # 07x
    2837, 4700, 5200, 2740, 0, 0, 0, 0, 0, 0,  # 08x
    0, 0, 0, 0, 30, 430, 1, 4320, 5850, 0,  # 09x
    0, 0, 0, 0, 0, 0, 0, 0, 6, 1,  # 10x
    4, 50, 50, 0, 4, 0, 100, 0, 0, 0,  # 11x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 12x
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 13x
]))
# fmt: on


def test_lookup():
    """Ensure we can look up registers by index, instead of the complex type they're defined as."""
    assert InputRegister(0) == InputRegister.INVERTER_STATUS
    with pytest.raises(TypeError, match='Cannot extend enumerations'):
        InputRegister(0, Type.UINT16)
    assert HoldingRegister(0) == HoldingRegister.DEVICE_TYPE_CODE
    with pytest.raises(TypeError, match='Cannot extend enumerations'):
        HoldingRegister(0, Type.UINT16)


def test_str_and_repr():
    """Ensure some behaviour around str and repr handling."""
    assert isinstance(InputRegister(0), Register)
    assert isinstance(InputRegister(0), str)
    assert not isinstance(InputRegister(0), int)
    assert str(InputRegister(0)) == 'IR:000'
    assert repr(InputRegister(50)) == 'IR:050'
    assert str(HoldingRegister(109)) == 'HR:109'
    assert repr(HoldingRegister(99)) == 'HR:099'


def test_comparison():
    """Ensure registers from different banks aren't comparable."""
    assert HoldingRegister(0) == HoldingRegister(0)
    assert InputRegister(0) == InputRegister(0)
    assert HoldingRegister(0) != InputRegister(0)


def test_registers_unique_names():
    """Ensure registers have unique names despite their location."""
    holding_register_names = set(HoldingRegister.__members__.keys())
    input_register_names = set(InputRegister.__members__.keys())

    assert holding_register_names.intersection(input_register_names) == set()


def _gen_binary(x) -> str:
    v4 = bin(x % 16)[2:].zfill(4)
    x >>= 4
    v3 = bin(x % 16)[2:].zfill(4)
    x >>= 4
    v2 = bin(x % 16)[2:].zfill(4)
    x >>= 4
    v1 = bin(x % 16)[2:].zfill(4)
    return ' '.join([v1, v2, v3, v4])


@pytest.mark.parametrize("val", [0, 0x32, 0x7FFF, 0x8000, 0xFFFF])
@pytest.mark.parametrize("scaling", [v.value for v in ScalingFactor.__members__.values()])
def test_type_repr(val: int, scaling: int):
    """Ensure we render types correctly."""
    if scaling != 1:
        assert Type.UINT16.repr(val, scaling) == f'{val / scaling:0.02f}'
    else:
        assert Type.UINT16.repr(val, scaling) == str(val)

    if scaling != 1:
        if val > 0x7FFF:  # this should be negative
            assert Type.INT16.repr(val, scaling) == f'{(val - 2 ** 16) / scaling:0.02f}'
        else:
            assert Type.INT16.repr(val, scaling) == f'{val / scaling:0.02f}'
    else:
        if val > 0x7FFF:  # this should be negative
            assert Type.INT16.repr(val, scaling) == str(val - 2**16)
        else:
            assert Type.INT16.repr(val, scaling) == str(val)

    if scaling != 1:
        assert Type.UINT32_LOW.repr(val, scaling) == f'{val / scaling:0.02f}'
        assert Type.UINT32_HIGH.repr(val, scaling) == f'{(val * 2 ** 16) / scaling:0.02f}'
    else:
        assert Type.UINT32_LOW.repr(val, scaling) == str(val)
        assert Type.UINT32_HIGH.repr(val, scaling) == str(val * 2**16)

    assert Type.UINT8.repr(val, scaling) == str(val % 256)
    assert Type.DUINT8.repr(val, scaling) == f'{val // 256}, {val % 256}'

    assert Type.BITFIELD.repr(val, scaling) == _gen_binary(val)

    assert Type.HEX.repr(val, scaling) == f'0x{val:04x}'

    # scaling doesn't make sense for ascii types
    # non-ascii values will not decode properly
    if val == 0x0:
        with pytest.raises(ValueError, match='null'):
            Type.ASCII.convert(val, scaling)
    elif val // 256 < 128 and val % 256 < 128:
        assert Type.ASCII.repr(val, scaling) == val.to_bytes(2, byteorder='big').decode(encoding='ascii')
    else:
        with pytest.raises(ValueError, match='non-ASCII'):
            Type.ASCII.repr(val, scaling)

    if val == 0x0:
        assert Type.BOOL.repr(val, scaling) == 'False'
    elif val == 0x1:
        assert Type.BOOL.repr(val, scaling) == 'True'
    else:
        with pytest.raises(ValueError, match=str(val)):
            Type.BOOL.repr(val, scaling)


@pytest.mark.parametrize("val", [0, 0x32, 0x7FFF, 0x8000, 0xFFFF])
@pytest.mark.parametrize("scaling", [v.value for v in ScalingFactor.__members__.values()])
def test_type_convert(val: int, scaling: int):
    """Ensure we render types correctly."""
    assert Type.UINT16.convert(val, scaling) == val / scaling

    if val > 0x7FFF:  # this should be negative
        assert Type.INT16.convert(val, scaling) == (val - 2**16) / scaling
    else:
        assert Type.INT16.convert(val, scaling) == val / scaling

    assert Type.UINT32_LOW.convert(val, scaling) == val / scaling
    assert Type.UINT32_HIGH.convert(val, scaling) == (val * 2**16) / scaling

    assert Type.UINT8.convert(val, scaling) == val % 256
    assert Type.DUINT8.convert(val, scaling) == ((val // 256), (val % 256))

    assert Type.BITFIELD.convert(val, scaling) == val

    assert Type.HEX.convert(val, scaling) == f'{hex(val)[2:]:>04}'

    # scaling doesn't make sense for ascii types
    # non-ascii values will not decode properly
    if val == 0x0:
        with pytest.raises(ValueError, match='null'):
            Type.ASCII.convert(val, scaling)
    elif val // 256 < 128 and val % 256 < 128:
        assert Type.ASCII.convert(val, scaling) == val.to_bytes(2, byteorder='big').decode(encoding='ascii')
    else:
        with pytest.raises(ValueError, match='non-ASCII'):
            Type.ASCII.convert(val, scaling)

    if val == 0x0:
        assert Type.BOOL.convert(val, scaling) is False
    elif val == 0x1:
        assert Type.BOOL.convert(val, scaling) is True
    else:
        with pytest.raises(ValueError, match=str(val)):
            Type.BOOL.convert(val, scaling)


@pytest.mark.parametrize("scaling", [v.value for v in ScalingFactor.__members__.values()])
def test_type_render_time(scaling):
    """Ensure we can convert BCD-encoded time slots."""
    assert Type.TIME.convert(0, scaling) == datetime.time(hour=0, minute=0)
    assert Type.TIME.convert(30, scaling) == datetime.time(hour=0, minute=30)
    assert Type.TIME.convert(60, scaling) == datetime.time(hour=0, minute=0)  # what _does_ 60 mean?
    assert Type.TIME.convert(430, scaling) == datetime.time(hour=4, minute=30)
    assert Type.TIME.convert(123, scaling) == datetime.time(hour=1, minute=23)
    assert Type.TIME.convert(234, scaling) == datetime.time(hour=2, minute=34)
    assert Type.TIME.convert(2400, scaling) == datetime.time(hour=0, minute=0)
    assert Type.TIME.convert(2401, scaling) == datetime.time(hour=0, minute=1)
    with pytest.raises(ValueError, match='0678'):
        Type.TIME.convert(678, scaling)
    with pytest.raises(ValueError, match='9999'):
        Type.TIME.convert(9999, scaling)


@pytest.mark.parametrize("scaling", [v.value for v in ScalingFactor.__members__.values()])
def test_type_render_power_factor(scaling: int):
    """Ensure we can convert BCD-encoded time slots."""
    assert Type.POWER_FACTOR.convert(0, scaling) == -1.0
    assert Type.POWER_FACTOR.convert(5000, scaling) == -0.5
    assert Type.POWER_FACTOR.convert(10000, scaling) == 0.0
    assert Type.POWER_FACTOR.convert(15000, scaling) == 0.5
    assert Type.POWER_FACTOR.convert(20000, scaling) == 1.0


def test_random_sanity_checks():
    """Just a few random sanity checks."""
    assert Type.INT16.convert(98, 1) == 98
    assert Type.INT16.convert(64786, 1) == -750


def test_register_convert():
    """Ensure we can convert a register's value and sanity-check it."""

    def assert_can_convert(raw_val, expected, negative_too=True):
        assert func(raw_val) == expected, f'{raw_val} should convert to {expected}'
        if raw_val != 0:
            if negative_too:
                assert func(-raw_val) == -expected, f'{-raw_val} should convert to {-expected}'
            else:
                pytest.raises(ValueError, func, -raw_val)

    def assert_raises(raw_val, negative_too=True):
        pytest.raises(ValueError, func, raw_val)
        if raw_val != 0 and negative_too:
            pytest.raises(ValueError, func, -raw_val)

    func = InputRegister['V_AC1'].convert
    assert_can_convert(0, 0.0)
    assert_can_convert(100, 10.0)
    assert_can_convert(1000, 100.0)
    assert_can_convert(10_000, 1000.0)
    assert_raises(20_000)

    func = InputRegister['P_PV1'].convert
    assert_can_convert(0, 0.0)
    assert_can_convert(100, 100)
    assert_can_convert(1000, 1000)
    assert_raises(10_000)
    assert_raises(20_000)

    func = InputRegister['I_GRID_PORT'].convert
    assert_can_convert(0, 0.0)
    assert_can_convert(50, 0.5)
    assert_can_convert(100, 1.0)
    assert_can_convert(150, 1.50)
    assert_can_convert(200, 2.0)
    assert_can_convert(1000, 10.0)
    assert_can_convert(5000, 50.0)
    assert_can_convert(10_000, 100.0)
    assert_can_convert(15_000, 150.0)
    assert_raises(20_000)

    func = InputRegister['E_INVERTER_OUT_DAY'].convert
    assert_can_convert(0, 0)
    assert_can_convert(100, 10.0, False)
    assert_can_convert(1005, 100.5, False)
    assert_can_convert(10_500, 1050.0, False)
    assert_can_convert(20_000, 2000.0, False)
    assert_raises(-200, False)

    func = InputRegister['F_EPS_BACKUP'].convert
    assert_can_convert(0, 0)
    assert_can_convert(5000, 50, False)
    assert_can_convert(6000, 60.0, False)
    assert_can_convert(9999, 99.99, False)
    assert_raises(10000)
    assert_raises(20000)

    func = InputRegister['TEMP_INVERTER_HEATSINK'].convert
    assert_can_convert(0, 0)
    assert_can_convert(50, 5.0)
    assert_can_convert(60, 6.0)
    assert_can_convert(99, 9.9)
    assert_can_convert(100, 10.0)
    assert_can_convert(999, 99.9)
    assert_can_convert(1555, 155.5)
    assert_raises(2000)


def test_register_repr():
    """Ensure we can create human-readable forms of register values."""
    assert InputRegister['V_AC1'].repr(15) == '1.50V'
    assert InputRegister['P_PV1'].repr(15) == '15W'
    assert InputRegister['I_GRID_PORT'].repr(15) == '0.15A'
    assert InputRegister['E_INVERTER_OUT_DAY'].repr(15) == '1.50kWh'
    assert InputRegister['F_EPS_BACKUP'].repr(15) == '0.15Hz'
    assert InputRegister['TEMP_INVERTER_HEATSINK'].repr(15) == '1.50°C'


def test_unit_is_sane_value():
    """Ensure we can predict physical values that are improbable."""

    def assert_sane(val, negative_too=True):
        assert func(val) is True, f'{val} should be True'
        if val != 0:
            if negative_too:
                assert func(-val) is True, f'{-val} should be True'
            else:
                assert func(-val) is False, f'{-val} should be False'

    def assert_not_sane(val, negative_too=True):
        assert func(val) is False, f'{val} should be False'
        if val != 0 and negative_too:
            assert func(-val) is False, f'{-val} should be False'

    func = Unit.VOLTAGE_V.is_value_sane
    assert_sane(0)
    assert_sane(100)
    assert_sane(1000)
    assert_not_sane(10_000)
    assert_not_sane(20_000)

    func = Unit.POWER_W.is_value_sane
    assert_sane(0)
    assert_sane(100)
    assert_sane(1000)
    assert_not_sane(10_000)
    assert_not_sane(20_000)

    func = Unit.POWER_VA.is_value_sane
    assert_sane(0)
    assert_sane(100)
    assert_sane(1000)
    assert_not_sane(10_000)
    assert_not_sane(20_000)

    func = Unit.POWER_KW.is_value_sane
    assert_sane(0)
    assert_sane(5)
    assert_not_sane(10)
    assert_not_sane(100)

    func = Unit.CURRENT_A.is_value_sane
    assert_sane(0)
    assert_sane(50)
    assert_sane(100)
    assert_sane(150)
    assert_not_sane(200)
    assert_not_sane(1000)
    assert_not_sane(5000)
    assert_not_sane(10_000)

    func = Unit.CURRENT_MA.is_value_sane
    assert_sane(0)
    assert_sane(50)
    assert_sane(100)
    assert_sane(150)
    assert_sane(200)
    assert_sane(1000)
    assert_not_sane(5000)
    assert_not_sane(10_000)

    func = Unit.ENERGY_KWH.is_value_sane
    assert_sane(0)
    assert_sane(00, False)
    assert_sane(1000, False)
    assert_sane(10_000, False)
    assert_sane(20_000, False)
    assert_not_sane(-200, False)

    func = Unit.FREQUENCY_HZ.is_value_sane
    assert_sane(0)
    assert_sane(50, False)
    assert_sane(60, False)
    assert_sane(99, False)
    assert_not_sane(100)
    assert_not_sane(200)

    func = Unit.TEMPERATURE_C.is_value_sane
    assert_sane(0)
    assert_sane(50)
    assert_sane(60)
    assert_sane(99)
    assert_sane(100)
    assert_not_sane(200)

    func = Unit.PERCENT.is_value_sane
    assert_sane(0)
    assert_sane(50, False)
    assert_sane(60, False)
    assert_sane(99, False)
    assert_sane(100, False)
    assert_sane(200, False)
    assert_sane(250, False)
    assert_not_sane(256, False)
