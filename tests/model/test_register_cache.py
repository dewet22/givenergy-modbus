import datetime

from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.register import HR, IR
from givenergy_modbus.model.register_cache import RegisterCache
from tests.model.test_register import HOLDING_REGISTERS, INPUT_REGISTERS


def test_register_cache(register_cache):
    """Ensure we can instantiate a RegisterCache and set registers in it."""
    expected = {HR(k): v for k, v in HOLDING_REGISTERS.items()}
    expected.update({IR(k): v for k, v in INPUT_REGISTERS.items()})
    assert register_cache == expected


def test_to_from_json():
    """Ensure we can unserialize a RegisterCache from JSON."""
    assert RegisterCache.from_json('{"HR(1)": 2, "IR(3)": 4}') == {HR(1): 2, IR(3): 4}


def test_to_from_json_actual_data(json_inverter_daytime_discharging_with_solar_generation):
    """Ensure we can unserialize a RegisterCache to and from JSON."""
    rc = RegisterCache.from_json(json_inverter_daytime_discharging_with_solar_generation)
    assert len(rc) == 360


def test_to_string():
    rc = RegisterCache(
        registers={
            HR(14): 12594,
            HR(16): 18229,
            IR(13): 21313,
            IR(15): 13108,
            IR(17): 13879,
            IR(99): 0,
            IR(100): 1,
        }
    )
    assert '' == rc.to_string()
    assert 'SA1234G567' == rc.to_string(IR(13), HR(14), IR(15), HR(16), IR(17))
    assert 'SA' == rc.to_string(IR(13))
    assert '' == rc.to_string(IR(22))
    assert '' == rc.to_string(IR(99))
    assert '' == rc.to_string(IR(99), IR(100))
    assert '' == rc.to_string(IR(100))


def test_to_hex_string():
    rc = RegisterCache(
        registers={
            HR(14): 0x3456,
            HR(16): 0x7890,
            IR(13): 0xABCD,
            IR(15): 0x9876,
            IR(17): 0x210F,
        }
    )
    assert '' == rc.to_hex_string()
    assert 'ABCD345698767890210F' == rc.to_hex_string(IR(13), HR(14), IR(15), HR(16), IR(17))
    assert '3456' == rc.to_hex_string(HR(14))
    assert '0000' == rc.to_hex_string(IR(22))


def test_to_duint8():
    rc = RegisterCache(
        registers={
            HR(14): 0x3456,
            IR(17): 0x210F,
        }
    )
    assert (0x34, 0x56) == rc.to_duint8(HR(14))
    assert (0x21, 0x0F) == rc.to_duint8(IR(17))
    assert (0x34, 0x56, 0x21, 0x0F) == rc.to_duint8(HR(14), IR(17))
    assert (0, 0) == rc.to_duint8(IR(22))


def test_to_uint32():
    rc = RegisterCache(
        registers={
            HR(14): 0x3456,
            IR(17): 0x210F,
        }
    )
    assert 0x3456210F == rc.to_uint32(HR(14), IR(17))
    assert 0 == rc.to_uint32(IR(22), IR(23))


def test_to_datetime():
    registers = {
        HR(14): 1,
        HR(16): 2,
        IR(13): 3,
        IR(15): 4,
        IR(17): 5,
        HR(19): 6,
    }
    rc = RegisterCache(registers)
    assert datetime.datetime(2001, 2, 3, 4, 5, 6) == rc.to_datetime(*registers.keys())
    assert datetime.datetime(2000, 1, 1, 0, 0, 0) == rc.to_datetime(IR(22), IR(23), IR(24), IR(25), IR(26), IR(27))


def test_to_timeslot():
    rc = RegisterCache(
        registers={
            HR(14): 1030,
            IR(17): 2359,
        }
    )
    assert TimeSlot.from_components(10, 30, 23, 59) == rc.to_timeslot(HR(14), IR(17))
    assert TimeSlot.from_components(0, 0, 0, 0) == rc.to_timeslot(IR(22), IR(23))
