import json
import logging

import pytest

from givenergy_modbus.model.register import (
    HR,
    IR,
    MR,
    Converter,
    RegisterDefinition,
    RegisterEncoder,
    RegisterGetter,
    is_valid_serial,
)
from givenergy_modbus.model.register_cache import RegisterCache

# fmt: off
INPUT_REGISTERS: dict[int, int] = dict(enumerate([
    0, 14, 10, 70, 0, 2367, 0, 1832, 0, 0,  # 00x
    0, 0, 159, 4990, 0, 12, 4790, 4, 4, 5,  # 01x
    9, 0, 6, 0, 0, 0, 209, 0, 946, 0,  # 02x
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
HOLDING_REGISTERS: dict[int, int] = dict(enumerate([
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
    # 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 12x
    # 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 13x
    # 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 14x
    # 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 15x
    # 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # 16x
]))
# fmt: on


def test_register():
    assert HR(0) == HR(0)
    assert HR(0) != HR(1)
    assert HR(0) != IR(0)
    assert {HR(0): 1, IR(1): 2} == {HR(0): 1, IR(1): 2}
    assert {HR(0): 1, IR(1): 2} != {HR(1): 1, IR(2): 2}

    assert str(HR(22)) == "HR_22"
    assert str(IR(99)) == "IR_99"
    assert str(MR(7)) == "MR_7"
    assert json.dumps(HR(22), cls=RegisterEncoder) == '"HR_22"'
    assert json.dumps(IR(56), cls=RegisterEncoder) == '"IR_56"'
    assert json.dumps(MR(3), cls=RegisterEncoder) == '"MR_3"'

    assert MR(0) == MR(0)
    assert MR(0) != MR(1)
    assert MR(0) != HR(0)
    assert MR(0) != IR(0)
    assert {MR(0): 1, MR(1): 2} == {MR(0): 1, MR(1): 2}

    assert str({HR(0): 1234, HR(1): 0x4321, HR(2): 0xABCD, IR(0): 2}) == (
        "{HR_0: 1234, HR_1: 17185, HR_2: 43981, IR_0: 2}"
    )
    with pytest.raises(TypeError, match="keys must be str, int, float, bool or None, not HR"):
        json.dumps({HR(0): 1234, HR(1): 17185, HR(2): 43981, IR(0): 2}, cls=RegisterEncoder)


def test_converter_timeslot_sentinel():
    from givenergy_modbus.model import TimeSlot

    assert Converter.timeslot(0, 430) == TimeSlot.from_repr(0, 430)
    assert Converter.timeslot(None, 430) is None
    assert Converter.timeslot(0, None) is None
    # raw value 60 is a hardware sentinel for "unset"; minutes=60 would raise ValueError
    assert Converter.timeslot(60, 2359) is None
    assert Converter.timeslot(0, 60) is None


def test_converter_bitfield():
    assert Converter.bitfield(0b1010_0011_0000_0001, 0, 0) == 1  # MSB
    assert Converter.bitfield(0b1010_0011_0000_0001, 15, 15) == 1  # LSB
    assert Converter.bitfield(0b1010_0000_0000_0000, 0, 3) == 0b1010
    assert Converter.bitfield(0xFFFF, 0, 15) == 0xFFFF
    assert Converter.bitfield(0x0000, 0, 15) == 0
    assert Converter.bitfield(None, 0, 0) is None


def test_converter_gateway_version():
    # 'GA' = 0x4741, '00' = 0x3030, digits 0,0,0,9 stored as byte values in two registers
    first = 0x4741  # 'G','A'
    second = 0x3030  # '0','0'
    third = 0x0000  # digits '0','0'
    fourth = 0x0009  # digits '0','9'
    assert Converter.gateway_version(first, second, third, fourth) == "GA000009"

    assert Converter.gateway_version(None, second, third, fourth) is None
    assert Converter.gateway_version(first, None, third, fourth) is None


def test_battery_max_power():
    from givenergy_modbus.model.inverter import _battery_max_power

    # DTC "2001" prefix "20" + Gen2/3 fw → 3600W
    assert _battery_max_power("2001", 300) == 3600
    # DTC "2001" prefix "20" + Gen1 fw → 2600W
    assert _battery_max_power("2001", 100) == 2600
    # Known non-'20' DTC
    assert _battery_max_power("8001", 0) == 6000
    # Unknown DTC → 0
    assert _battery_max_power("9999", 0) == 0
    assert _battery_max_power(None, 100) is None
    assert _battery_max_power("2001", None) is None


def test_gateway_fault_code():
    from givenergy_modbus.model.gateway import _gateway_fault_code

    assert _gateway_fault_code(None) is None
    assert _gateway_fault_code(0) == []
    # bit 0 (MSB of 32-bit) → "Relay 1&2 bonding"
    result = _gateway_fault_code(0x80000000)
    assert result == ["Relay 1&2 bonding"]
    # bit 31 (LSB) → "Grid mode Off"
    result = _gateway_fault_code(0x00000001)
    assert result == ["Grid mode Off"]
    # bit 12 is None → no output (0x80000000 >> 12 = 0x00080000)
    assert _gateway_fault_code(0x00080000) == []


def test_inverter_fault_code():
    from givenergy_modbus.model.inverter import _inverter_fault_code

    assert _inverter_fault_code(None) is None
    assert _inverter_fault_code(0) == []
    # bit 3 (from MSB) → "Backup Overload Fault"
    result = _inverter_fault_code(0b0001_0000_0000_0000_0000_0000_0000_0000)
    assert result == ["Backup Overload Fault"]
    # bits 6+7 → "Grid Monitor Comm Fault" + "ARM Comms Fault"
    result = _inverter_fault_code(0b0000_0011_0000_0000_0000_0000_0000_0000)
    assert "Grid Monitor Comm Fault" in result
    assert "ARM Comms Fault" in result
    # None bits produce no output
    assert _inverter_fault_code(0b1110_0000_0000_0000_0000_0000_0000_0000) == []


def test_inverter_fault_code2():
    from givenergy_modbus.model.inverter_threephase import _inverter_fault_code2

    assert _inverter_fault_code2(None, 0) is None
    assert _inverter_fault_code2(0, 0) == []
    # word 0, bit 0 (MSB) → "Battery Voltage High"
    result = _inverter_fault_code2(0x8000, 0)
    assert result == ["Battery Voltage High"]
    # word 3, bit 0 (MSB) → "Battery reversed"
    result = _inverter_fault_code2(0x8000, 3)
    assert result == ["Battery reversed"]
    # out-of-range word → None
    assert _inverter_fault_code2(0xFFFF, 9) is None
    # None bits produce no output (word 4 has mostly None)
    assert _inverter_fault_code2(0x8000, 4) == []


# ---------------------------------------------------------------------------
# RegisterDefinition bounds
# ---------------------------------------------------------------------------


def _getter(defn: RegisterDefinition, raw: int) -> RegisterGetter:
    """Build a single-register getter wired to a cache containing `raw`."""

    class _G(RegisterGetter):
        REGISTER_LUT = {"field": defn}

    return _G(RegisterCache({IR(0): raw}))


def test_bounds_within_range():
    defn = RegisterDefinition(Converter.uint16, None, IR(0), min=0, max=100)
    assert _getter(defn, 50).get("field") == 50


def test_bounds_at_limits():
    defn = RegisterDefinition(Converter.uint16, None, IR(0), min=0, max=100)
    assert _getter(defn, 0).get("field") == 0
    assert _getter(defn, 100).get("field") == 100


def test_bounds_below_min_logs_and_passes_through(caplog):
    defn = RegisterDefinition(Converter.uint16, None, IR(1), min=10, max=100)
    cache = RegisterCache({IR(1): 5})

    class _G(RegisterGetter):
        REGISTER_LUT = {"field": defn}

    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _G(cache).get("field")
    assert val == 5
    assert any("out of bounds" in r.message for r in caplog.records)


def test_bounds_above_max_logs_and_passes_through(caplog):
    defn = RegisterDefinition(Converter.uint16, None, IR(0), max=100)
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _getter(defn, 101).get("field")
    assert val == 101
    assert any("out of bounds" in r.message for r in caplog.records)


def test_bounds_checked_post_conversion(caplog):
    # Raw value 550 → deci → 55.0; bounds 0.0–100.0 should pass
    defn = RegisterDefinition(Converter.uint16, Converter.deci, IR(0), min=0.0, max=100.0)
    assert _getter(defn, 550).get("field") == pytest.approx(55.0)
    # Raw value 1010 → deci → 101.0; exceeds max=100.0 — logs at debug, value passes through
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _getter(defn, 1010).get("field")
    assert val == pytest.approx(101.0)
    assert any("out of bounds" in r.message for r in caplog.records)


def test_bounds_checked_post_signed_conversion(caplog):
    # int16 of raw 65535 → -1; below min=0 — logs at debug, value passes through
    defn = RegisterDefinition(Converter.int16, None, IR(0), min=0)
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _getter(defn, 65535).get("field")
    assert val == -1
    assert any("out of bounds" in r.message for r in caplog.records)
    assert _getter(defn, 10).get("field") == 10


def test_all_zero_raw_registers_exempt_from_bounds(caplog):
    # Mirrors the meter `frequency` case: hardware pads unwired devices with 0x0000, which
    # would otherwise spam the log when min > 0. The exemption is checked at the raw register
    # level, not post-conv, so the intent ("hardware didn't populate this") stays unambiguous.
    defn = RegisterDefinition(Converter.uint16, Converter.centi, IR(0), min=40.0, max=70.0)
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _getter(defn, 0).get("field")
    assert val == pytest.approx(0.0)
    assert not any("out of bounds" in r.message for r in caplog.records)


def test_multi_register_all_zero_exempt_from_bounds(caplog):
    # Multi-register field: both raw registers must be 0x0000 for the exemption to apply.
    defn = RegisterDefinition(Converter.uint32, None, IR(0), IR(1), min=100, max=1_000_000)

    class _G(RegisterGetter):
        REGISTER_LUT = {"field": defn}

    # Both registers zero → exempt.
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _G(RegisterCache({IR(0): 0, IR(1): 0})).get("field")
    assert val == 0
    assert not any("out of bounds" in r.message for r in caplog.records)

    # One register non-zero → still bounds-checked (and flagged).
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _G(RegisterCache({IR(0): 0, IR(1): 5})).get("field")
    assert val == 5
    assert any("out of bounds" in r.message for r in caplog.records)


def test_no_bounds_unchanged():
    defn = RegisterDefinition(Converter.uint16, None, IR(0))
    assert _getter(defn, 65535).get("field") == 65535


def test_missing_register_skips_bounds():
    defn = RegisterDefinition(Converter.uint16, None, IR(0), min=0, max=100)
    getter = type("_G", (RegisterGetter,), {"REGISTER_LUT": {"field": defn}})(RegisterCache())
    assert getter.get("field") is None


# ---------------------------------------------------------------------------
# is_valid_serial
# ---------------------------------------------------------------------------


def test_is_valid_serial_accepts_alphanumeric():
    assert is_valid_serial("SA1234G567")
    assert is_valid_serial("BG1234G567")


def test_is_valid_serial_warns_on_unexpected_pattern(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.register"):
        result = is_valid_serial("AAAAAAAAAA")  # 10 alnum uppercase but not AA0000A000
    assert result is True
    assert "does not match expected pattern" in caplog.text


def test_is_valid_serial_rejects_wrong_length():
    assert not is_valid_serial("ABC123")  # too short
    assert not is_valid_serial("A")
    assert not is_valid_serial("SA1234G5678")  # too long


def test_is_valid_serial_rejects_blanks():
    assert not is_valid_serial(None)
    assert not is_valid_serial("")
    assert not is_valid_serial("          ")
    assert not is_valid_serial("\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")


def test_is_valid_serial_rejects_non_alphanumeric():
    assert not is_valid_serial("SA-1234567")
    assert not is_valid_serial("SA 1234567")
    assert not is_valid_serial("sa1234g567")  # lowercase


# ---------------------------------------------------------------------------
# RegisterGetter.is_coherent
# ---------------------------------------------------------------------------


def _serial_getter(serial_registers: tuple) -> type[RegisterGetter]:
    """Build a RegisterGetter subclass whose 'serial_number' spans the given registers."""
    defn = RegisterDefinition(Converter.string, None, *serial_registers)

    class _G(RegisterGetter):
        REGISTER_LUT = {"serial_number": defn}

    return _G


def test_is_coherent_passes_when_no_serial_in_lut():
    defn = RegisterDefinition(Converter.uint16, None, IR(0))

    class _G(RegisterGetter):
        REGISTER_LUT = {"field": defn}

    assert _G.is_coherent({IR(0): 42}, RegisterCache()) is True


def test_is_coherent_passes_when_serial_not_in_incoming_bank():
    G = _serial_getter((IR(10), IR(11), IR(12), IR(13), IR(14)))
    assert G.is_coherent({IR(0): 42}, RegisterCache()) is True


def test_is_coherent_passes_with_valid_serial():
    # "SA1234G567" across 5 registers (2 chars each): 0x5341, 0x3132, 0x3334, 0x4735, 0x3637
    G = _serial_getter((IR(10), IR(11), IR(12), IR(13), IR(14)))
    incoming = {IR(10): 0x5341, IR(11): 0x3132, IR(12): 0x3334, IR(13): 0x4735, IR(14): 0x3637}
    assert G.is_coherent(incoming, RegisterCache()) is True


def test_is_coherent_fails_with_invalid_serial():
    G = _serial_getter((IR(10), IR(11), IR(12), IR(13), IR(14)))
    incoming = {IR(10): 0x0000, IR(11): 0x0000, IR(12): 0x0000, IR(13): 0x0000, IR(14): 0x0000}
    assert G.is_coherent(incoming, RegisterCache()) is False


def test_is_coherent_uses_committed_plus_incoming():
    G = _serial_getter((IR(10), IR(11), IR(12), IR(13), IR(14)))
    committed = RegisterCache({IR(10): 0x5341, IR(11): 0x3132, IR(12): 0x3334, IR(13): 0x4735})
    incoming = {IR(14): 0x3637}  # final register arriving now
    assert G.is_coherent(incoming, committed) is True
