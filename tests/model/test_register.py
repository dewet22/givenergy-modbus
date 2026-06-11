import json
import logging
from datetime import datetime

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


def test_converter_pf_signed():
    """Signed int16 x 1e-4 power-factor decode (EE [-1, +1]) — see #246."""
    assert Converter.pf_signed(9998) == 0.9998  # near-unity import (capture, meter 0x03)
    assert Converter.pf_signed(64670) == -0.0866  # small export (capture, meter 0x01)
    assert Converter.pf_signed(0) == 0.0
    assert Converter.pf_signed(10_000) == 1.0
    assert Converter.pf_signed(0x10000 - 10_000) == -1.0
    assert Converter.pf_signed(None) is None


def test_converter_timeslot_sentinel():
    from givenergy_modbus.model import TimeSlot

    assert Converter.timeslot(0, 430) == TimeSlot.from_repr(0, 430)
    assert Converter.timeslot(None, 430) is None
    assert Converter.timeslot(0, None) is None
    # raw value 60 is a hardware sentinel for "unset"; minutes=60 would raise ValueError
    assert Converter.timeslot(60, 2359) is None
    assert Converter.timeslot(0, 60) is None


def test_converter_timeslot_degrades_on_invalid_value():
    """Adversarial / corrupt register values must degrade to None, not raise (audit M4)."""
    # minutes 99 / hour 25 are out of range but not the 60 sentinel — previously raised ValueError
    assert Converter.timeslot(1099, 1200) is None
    assert Converter.timeslot(1030, 2530) is None


def test_converter_datetime_degrades_on_invalid_value():
    """A device-supplied month=0 / hour=24 must degrade to None, not raise (audit M4)."""
    assert Converter.datetime(24, 13, 1, 0, 0, 0) is None  # month 13
    assert Converter.datetime(24, 1, 1, 24, 0, 0) is None  # hour 24
    # a fully valid set still composes
    assert Converter.datetime(24, 6, 10, 12, 0, 0) == datetime(2024, 6, 10, 12, 0, 0)


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


def test_converter_serial_decodes_like_string():
    # 'CE' 0x4345, '2231' 0x3232 0x3331, 'G454' 0x4734 0x3534 → CE2231G454
    regs = (0x4345, 0x3232, 0x3331, 0x4734, 0x3534)
    assert Converter.serial(*regs) == "CE2231G454"
    assert Converter.serial(*regs) == Converter.string(*regs)
    assert Converter.serial(0x4345, None, 0x3331, 0x4734, 0x3534) is None


def test_redact_serial_standard_form():
    # Family prefix, YYWW date and middle letter preserved; trailing unit digits zeroed.
    assert Converter.redact_serial("CE2231G454") == "CE2231G000"
    assert Converter.redact_serial("WO2310G227") == "WO2310G000"


def test_redact_serial_ems_form():
    # Three-letter prefix + YYWW kept; trailing three digits zeroed.
    assert Converter.redact_serial("EMS2522018") == "EMS2522000"


def test_redact_serial_passthrough_and_empty():
    assert Converter.redact_serial(None) is None
    assert Converter.redact_serial("") == ""
    # Unrecognised shapes (e.g. a 4-char meter code) are returned unchanged, not mangled.
    assert Converter.redact_serial("AB12") == "AB12"
    # Already-redacted input is idempotent.
    assert Converter.redact_serial("CE2231G000") == "CE2231G000"


def test_redact_serial_strict_fails_closed():
    """redact_serial_strict redacts recognised serials and blanks everything else (fail-closed)."""
    assert Converter.redact_serial_strict("CE2231G454") == "CE2231G000"  # recognised, redacted
    assert Converter.redact_serial_strict("EMS2522018") == "EMS2522000"  # recognised EMS form
    assert Converter.redact_serial_strict("CE2231G000") == "CE2231G000"  # recognised, already redacted
    assert Converter.redact_serial_strict("UNKNOWN123") == ""  # valid charset, unknown pattern → blank
    assert Converter.redact_serial_strict("AB12") == ""  # short non-GE identifier → blank
    assert Converter.redact_serial_strict("") == ""
    assert Converter.redact_serial_strict(None) == ""


def test_battery_max_power():
    from givenergy_modbus.model.inverter import _battery_max_power

    # DTC "2001" prefix "20" + Gen2/3 fw → 3600W
    assert _battery_max_power("2001", 300) == 3600
    # DTC "2001" prefix "20" + Gen1 fw → 2600W
    assert _battery_max_power("2001", 100) == 2600
    # Known non-'20' DTC
    assert _battery_max_power("8001", 0) == 6000
    # Unknown DTC → None (table is incomplete/unverified; "unknown", not 0 W)
    assert _battery_max_power("9999", 0) is None
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
    # out-of-range word → None (LUT covers 0..7 only; word 8+ unreachable)
    assert _inverter_fault_code2(0xFFFF, 8) is None
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


def test_bounds_below_min_returns_none(caplog):
    defn = RegisterDefinition(Converter.uint16, None, IR(1), min=10, max=100)
    cache = RegisterCache({IR(1): 5})

    class _G(RegisterGetter):
        REGISTER_LUT = {"field": defn}

    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _G(cache).get("field")
    assert val is None
    assert any("out of bounds" in r.message for r in caplog.records)


def test_bounds_above_max_returns_none(caplog):
    defn = RegisterDefinition(Converter.uint16, None, IR(0), max=100)
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _getter(defn, 101).get("field")
    assert val is None
    assert any("out of bounds" in r.message for r in caplog.records)


def test_bounds_checked_post_conversion(caplog):
    # Raw value 550 → deci → 55.0; bounds 0.0–100.0 should pass
    defn = RegisterDefinition(Converter.uint16, Converter.deci, IR(0), min=0.0, max=100.0)
    assert _getter(defn, 550).get("field") == pytest.approx(55.0)
    # Raw value 1010 → deci → 101.0; exceeds max=100.0 — logs and returns None.
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _getter(defn, 1010).get("field")
    assert val is None
    assert any("out of bounds" in r.message for r in caplog.records)


def test_bounds_checked_post_signed_conversion(caplog):
    # int16 of raw 65535 → -1; below min=0 — logs and returns None.
    defn = RegisterDefinition(Converter.int16, None, IR(0), min=0)
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _getter(defn, 65535).get("field")
    assert val is None
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

    # One register non-zero → still bounds-checked (and suppressed).
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _G(RegisterCache({IR(0): 0, IR(1): 5})).get("field")
    assert val is None
    assert any("out of bounds" in r.message for r in caplog.records)


def test_no_bounds_unchanged():
    defn = RegisterDefinition(Converter.uint16, None, IR(0))
    assert _getter(defn, 65535).get("field") == 65535


def test_missing_register_skips_bounds():
    defn = RegisterDefinition(Converter.uint16, None, IR(0), min=0, max=100)
    getter = type("_G", (RegisterGetter,), {"REGISTER_LUT": {"field": defn}})(RegisterCache())
    assert getter.get("field") is None


# ---------------------------------------------------------------------------
# Regression: #82 library-side corruption (suppress, don't pass through)
# ---------------------------------------------------------------------------


def test_issue_82_ir100_corruption_values_suppressed():
    """Manifestation 1: Battery.soc at IR(100), declared min=0 max=100, suppress garbage.

    Sample values from a user's HA recorder DB over 4 days — none should leak to
    downstream consumers.
    """
    defn = RegisterDefinition(Converter.uint16, None, IR(100), min=0, max=100)

    class _G(RegisterGetter):
        REGISTER_LUT = {"soc": defn}

    for corrupt in (57946, 63055, 37978, 5710):
        cache = RegisterCache({IR(100): corrupt})
        assert _G(cache).get("soc") is None, f"corrupt value {corrupt} should be suppressed"


def test_issue_82_ir59_corruption_values_suppressed():
    """Manifestation 2: SinglePhaseInverter.battery_soc at IR(59), declared min=0 max=100.

    Sample values from the counter-shaped corruption observed in HA over the same window.
    """
    defn = RegisterDefinition(Converter.uint16, None, IR(59), min=0, max=100)

    class _G(RegisterGetter):
        REGISTER_LUT = {"battery_soc": defn}

    for corrupt in (44820, 45123, 46789, 47168):
        cache = RegisterCache({IR(59): corrupt})
        assert _G(cache).get("battery_soc") is None, f"corrupt value {corrupt} should be suppressed"


def test_issue_82_healthy_soc_values_pass_through():
    """Counter-example: healthy SOC values in range still decode normally."""
    defn = RegisterDefinition(Converter.uint16, None, IR(100), min=0, max=100)

    class _G(RegisterGetter):
        REGISTER_LUT = {"soc": defn}

    for healthy in (0, 1, 50, 83, 100):
        cache = RegisterCache({IR(100): healthy})
        assert _G(cache).get("soc") == healthy


# ---------------------------------------------------------------------------
# Regression: #180 unmapped enum value must not abort the whole build
# ---------------------------------------------------------------------------


def test_unmapped_enum_value_returns_none(caplog):
    """A garbage register value that isn't a valid enum member degrades to None.

    Reproduces #180: HR(29) held 62453, which is not a BatteryCalibrationStage,
    and the strict Enum.__call__ raised ValueError mid-build(), aborting the entire
    inverter decode. The offending field should resolve to None instead.
    """
    from givenergy_modbus.model.inverter import BatteryCalibrationStage

    defn = RegisterDefinition(Converter.uint16, BatteryCalibrationStage, IR(0))
    with caplog.at_level(logging.DEBUG, logger="givenergy_modbus.model.register"):
        val = _getter(defn, 62453).get("field")
    assert val is None
    assert any("not a valid BatteryCalibrationStage" in r.message for r in caplog.records)


def test_valid_enum_value_still_decodes():
    """Counter-example: a defined enum member decodes normally."""
    from givenergy_modbus.model.inverter import BatteryCalibrationStage

    defn = RegisterDefinition(Converter.uint16, BatteryCalibrationStage, IR(0))
    assert _getter(defn, 1).get("field") == BatteryCalibrationStage.DISCHARGE


def test_non_enum_converter_valueerror_still_propagates():
    """The guard is scoped to enums only — a real converter bug must not be swallowed."""

    def _boom(_val):
        raise ValueError("converter bug")

    defn = RegisterDefinition(Converter.uint16, _boom, IR(0))
    with pytest.raises(ValueError, match="converter bug"):
        _getter(defn, 1).get("field")


def test_unmapped_enum_value_survives_full_inverter_build():
    """Integration: a bad HR(29) leaves battery_calibration_stage None, rest decodes."""
    from givenergy_modbus.model.inverter import SinglePhaseInverter

    cache = RegisterCache({HR(k): v for k, v in HOLDING_REGISTERS.items()})
    cache.update({IR(k): v for k, v in INPUT_REGISTERS.items()})
    cache[HR(29)] = 62453

    inverter = SinglePhaseInverter.from_register_cache(cache)
    assert inverter.battery_calibration_stage is None
    assert inverter.serial_number is not None


# ---------------------------------------------------------------------------
# is_valid_serial
# ---------------------------------------------------------------------------


def test_is_valid_serial_accepts_alphanumeric():
    assert is_valid_serial("SA1234G567")
    assert is_valid_serial("BG1234G567")


def test_is_valid_serial_accepts_ems_format_without_warning(caplog):
    """EMS controller serials (3-letter prefix + 7 digits) are valid and must not warn."""
    import logging

    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.register"):
        assert is_valid_serial("EMS2522018") is True
    assert not any("no known GivEnergy pattern" in r.message for r in caplog.records)


def test_is_valid_serial_warns_on_unexpected_pattern(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="givenergy_modbus.model.register"):
        result = is_valid_serial("AAAAAAAAAA")  # 10 alnum uppercase, matches neither known pattern
    assert result is True
    assert "matches no known GivEnergy pattern" in caplog.text


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


# ---------------------------------------------------------------------------
# Display precision (derived from register scaling)
# ---------------------------------------------------------------------------


def test_precision_from_pre_conv_scalers():
    """milli/centi/deci scaling on the pre-converter implies 3/2/1 decimals."""
    assert RegisterDefinition(Converter.milli, None, IR(0)).precision == 3
    assert RegisterDefinition(Converter.centi, None, IR(0)).precision == 2
    assert RegisterDefinition(Converter.deci, None, IR(0)).precision == 1


def test_precision_integer_converters_are_zero():
    assert RegisterDefinition(Converter.uint16, None, IR(0)).precision == 0
    assert RegisterDefinition(Converter.int16, None, IR(0)).precision == 0
    assert RegisterDefinition(Converter.uint32, None, IR(0), IR(1)).precision == 0


def test_precision_post_conv_wins_over_pre_conv():
    """When the scaling lives on the post-converter (e.g. uint32 -> deci) it decides."""
    assert RegisterDefinition(Converter.uint32, Converter.deci, IR(0), IR(1)).precision == 1
    assert RegisterDefinition(Converter.int16, Converter.centi, IR(0)).precision == 2


def test_precision_non_numeric_is_none():
    """Enums, bools, strings and timeslots have no numeric precision."""
    assert RegisterDefinition(Converter.bool, None, IR(0)).precision is None
    assert RegisterDefinition(Converter.string, None, IR(0)).precision is None
    assert RegisterDefinition(Converter.hex, None, IR(0)).precision is None


def test_precision_tuple_converter_unwrapped():
    """A (converter, *args) tuple resolves to the converter's precision."""
    assert RegisterDefinition((Converter.duint8, 0), None, IR(0)).precision == 0
    # A raw bitfield extracts an integer bit range -> 0 decimals.
    assert RegisterDefinition((Converter.bitfield, 0, 1), None, IR(0)).precision == 0


def test_precision_enum_over_bitfield_is_none():
    """An enum post-conv over a bitfield pre-conv is non-numeric (precision None).

    EMS status registers extract a bitfield then decode it to a Status enum;
    the enum wins, so they have no numeric precision despite the integer bitfield.
    """
    from givenergy_modbus.model.ems import Ems

    assert Ems.precision_of("meter_1_status") is None


def test_getter_precision_of_known_and_unknown():
    class _G(RegisterGetter):
        REGISTER_LUT = {"volts": RegisterDefinition(Converter.centi, None, IR(0))}

    assert _G.precision_of("volts") == 2
    assert _G.precision_of("missing") is None  # not in LUT -> caller's default


def test_model_precision_of_is_model_specific():
    """The same attribute can scale differently per model — query the concrete model.

    i_battery is centivolts (2 dp) on single-phase but decivolts (1 dp) on
    three-phase; this is the whole reason precision is exposed per model.
    """
    from givenergy_modbus.model.inverter import SinglePhaseInverter
    from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter

    assert SinglePhaseInverter.precision_of("i_battery") == 2
    assert ThreePhaseInverter.precision_of("i_battery") == 1
    # A computed attribute (not register-backed) falls through to None.
    assert SinglePhaseInverter.precision_of("p_pv") is None


def test_model_precision_of_across_models():
    from givenergy_modbus.model.battery import Battery
    from givenergy_modbus.model.inverter import SinglePhaseInverter

    assert SinglePhaseInverter.precision_of("v_battery") == 2  # centi
    assert SinglePhaseInverter.precision_of("e_pv_total") == 1  # uint32 -> deci
    assert Battery.precision_of("soc") == 0  # uint16
    assert Battery.precision_of("v_out") == 3  # uint32 -> milli
    assert Battery.precision_of("serial_number") is None  # string


def test_register_public_index_and_reg_type():
    """Register.index / Register.reg_type are the public forms of _idx / _type (#247)."""
    assert HR(13).index == 13
    assert HR(13).reg_type == "HR"
    assert IR(95).index == 95
    assert IR(95).reg_type == "IR"
    from givenergy_modbus.model.register import MR

    assert MR(60).index == 60
    assert MR(60).reg_type == "MR"


def test_registers_of_mirrors_lut():
    """RegisterGetter.registers_of() returns the backing registers in wire order (#247)."""
    from givenergy_modbus.model.inverter import SinglePhaseInverterRegisterGetter as G

    regs = G.registers_of("serial_number")
    assert [(r.reg_type, r.index) for r in regs] == [("HR", 13), ("HR", 14), ("HR", 15), ("HR", 16), ("HR", 17)]
    # Unknown / computed attributes yield an empty tuple, so callers can iterate unconditionally.
    assert G.registers_of("no_such_attribute") == ()
