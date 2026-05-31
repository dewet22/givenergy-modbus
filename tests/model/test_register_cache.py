import datetime

from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.register import HR, IR, MR
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


def test_to_from_json_mr():
    """Ensure MR keys round-trip through JSON serialisation."""
    assert RegisterCache.from_json('{"MR(0)": 1, "MR:5": 99}') == {MR(0): 1, MR(5): 99}


def test_from_json_skips_unknown_register_prefix():
    """An unknown register prefix (e.g. from a future namespace) must be skipped, not crash.

    The previous behaviour was to abort the entire deserialisation with KeyError
    on encountering anything outside the HR/IR/MR lookup table.
    """
    # Known + unknown mixed — unknown silently dropped, known retained.
    assert RegisterCache.from_json('{"HR(1)": 2, "XR(99)": 42, "IR(3)": 4}') == {HR(1): 2, IR(3): 4}
    # Entirely unknown — yields an empty cache, not an exception.
    assert RegisterCache.from_json('{"XR(0)": 1, "ZR(2)": 3}') == {}


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
    assert "" == rc.to_string()
    assert "SA1234G567" == rc.to_string(IR(13), HR(14), IR(15), HR(16), IR(17))
    assert "SA" == rc.to_string(IR(13))
    assert "" == rc.to_string(IR(22))
    assert "" == rc.to_string(IR(99))
    assert "" == rc.to_string(IR(99), IR(100))
    assert "" == rc.to_string(IR(100))


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
    assert "" == rc.to_hex_string()
    assert "ABCD345698767890210F" == rc.to_hex_string(IR(13), HR(14), IR(15), HR(16), IR(17))
    assert "3456" == rc.to_hex_string(HR(14))
    assert "0000" == rc.to_hex_string(IR(22))


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


def test_to_datetime_zero_month_and_day():
    """Month or day register reading 0 must clamp to 1, not crash.

    Real hardware: Nick's AC captures (hass#52) show HR(41)=0 on all 3 devices.
    Previously raised 'month must be in 1..12, not 0'.
    """
    rc = RegisterCache(
        registers={
            HR(0): 24,  # year → 2024
            HR(1): 0,  # month register present but reads 0
            HR(2): 0,  # day register present but reads 0
            HR(3): 12,
            HR(4): 0,
            HR(5): 0,
        }
    )
    result = rc.to_datetime(HR(0), HR(1), HR(2), HR(3), HR(4), HR(5))
    assert result == datetime.datetime(2024, 1, 1, 12, 0, 0)


def test_to_timeslot():
    rc = RegisterCache(
        registers={
            HR(14): 1030,
            IR(17): 2359,
        }
    )
    assert TimeSlot.from_components(10, 30, 23, 59) == rc.to_timeslot(HR(14), IR(17))
    # Missing endpoints read as unset (None), not as a midnight (0,0) slot — a missing
    # register isn't "00:00". (Previously the defaultdict returned 0 for these.)
    assert rc.to_timeslot(IR(22), IR(23)) is None
    # An endpoint genuinely read as 0 (HHMM 0000 = midnight) is still a valid slot.
    rc[HR(20)] = 0
    rc[HR(21)] = 0
    assert TimeSlot.from_components(0, 0, 0, 0) == rc.to_timeslot(HR(20), HR(21))


def test_to_timeslot_returns_none_for_unset_slot_sentinel():
    """Raw value 60 is the hardware sentinel for an unset slot — mirror Converter.timeslot."""
    rc = RegisterCache(
        registers={
            HR(0): 60,
            HR(1): 60,
            HR(2): 1030,
        }
    )
    assert rc.to_timeslot(HR(0), HR(1)) is None
    assert rc.to_timeslot(HR(0), HR(2)) is None
    assert rc.to_timeslot(HR(2), HR(0)) is None


def test_to_timeslot_returns_none_for_missing_or_none_endpoint():
    """A missing or explicitly-None endpoint is unset — mirror Converter.timeslot's guard.

    Uses .get() so a missing key reads as None (and doesn't mutate the defaultdict
    by inserting a 0), rather than raising ValueError in TimeSlot.from_repr.
    """
    rc = RegisterCache(registers={HR(0): 1030, HR(1): None})
    assert rc.to_timeslot(HR(0), HR(1)) is None  # endpoint explicitly None
    assert rc.to_timeslot(HR(0), HR(9)) is None  # endpoint missing entirely
    assert HR(9) not in rc  # .get() must not have inserted a default 0
