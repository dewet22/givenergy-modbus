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


# ---------------------------------------------------------------------------
# redact_serials
# ---------------------------------------------------------------------------


def _encode_serial(serial: str, reg_cls, base: int) -> dict:
    """Encode a 10-char serial string into 5 consecutive register values."""
    padded = serial.encode("latin1").ljust(10, b"\x00")[:10]
    return {reg_cls(base + i): int.from_bytes(padded[i * 2 : i * 2 + 2], "big") for i in range(5)}


def test_redact_serials_battery_ir_group():
    """Battery serial in IR(110-114) is redacted; unrelated registers are untouched."""
    registers = _encode_serial("CE2231A123", IR, 110)
    registers[IR(0)] = 1234  # unrelated register
    rc = RegisterCache(registers)

    result = rc.redact_serials()

    expected_regs = _encode_serial("CE2231A000", IR, 110)
    for reg, val in expected_regs.items():
        assert result[reg] == val, f"{reg} mismatch"
    assert result[IR(0)] == 1234  # untouched


def test_redact_serials_inverter_hr_group():
    """Inverter serial HR(13-17) redacted; HR(8-12) also redacted via the explicit group.

    HR(8-12) is the legacy first_battery_serial_number location, removed from the LUT in
    #191 but kept in the redaction set explicitly (AIO stores the unit serial there
    byte-swapped, recoverable). Guards against that group going missing.
    """
    registers = {**_encode_serial("SA2231A456", HR, 13), **_encode_serial("BA2231A789", HR, 8)}
    registers[HR(0)] = 42  # unrelated

    result = RegisterCache(registers).redact_serials()

    expected_inv = _encode_serial("SA2231A000", HR, 13)
    expected_bat = _encode_serial("BA2231A000", HR, 8)
    for reg, val in {**expected_inv, **expected_bat}.items():
        assert result[reg] == val, f"{reg} mismatch"
    assert result[HR(0)] == 42


def test_redact_serials_is_idempotent():
    """Redacting twice produces the same result as redacting once."""
    rc = RegisterCache(_encode_serial("CE2231A123", IR, 110))
    once = rc.redact_serials()
    twice = once.redact_serials()
    assert dict(once) == dict(twice)


def test_redact_serials_leaves_unrecognised_shape_unchanged():
    """A value in an HR/IR serial group that matches no GE pattern is left unchanged (fail-open).

    Serial groups are applied without device-type context and overlap (BMU groups overlap LV
    battery data), so a non-matching value can't be distinguished from non-serial data — blanking
    it would destroy legitimate data. The fail-closed guarantee lives at the header-serial and MR
    boundaries instead. See redact_serials() docstring.
    """
    registers = _encode_serial("ZZZZZZZZZZ", IR, 110)
    result = RegisterCache(registers).redact_serials()
    assert dict(result) == dict(RegisterCache(registers))


def test_redact_serials_preserves_overlapping_non_serial_data():
    """A full LV battery bank redacts the serial but preserves overlapping non-serial data.

    Regression for the overlap found in review: the globally-applied BMU serial group IR(114-118)
    overlaps the LV battery serial (IR114) and real data (IR115 = usb_device_inserted). Redacting
    must zero only the battery serial's unit digits and leave IR(115) intact.
    """
    registers = _encode_serial("CE2231A123", IR, 110)  # battery serial IR(110-114)
    registers[IR(115)] = 8  # usb_device_inserted — legitimate non-serial data

    result = RegisterCache(registers).redact_serials()

    redacted_serial = b"".join((result[IR(110 + i)] & 0xFFFF).to_bytes(2, "big") for i in range(5))
    assert redacted_serial.decode("latin1").replace("\x00", "").upper() == "CE2231A000"
    assert result[IR(115)] == 8, "overlapping non-serial data must be preserved"


def test_redact_serials_absent_group_not_injected():
    """A serial group absent from the cache must not appear in the output."""
    rc = RegisterCache({IR(0): 99})
    result = rc.redact_serials()
    # IR(110-114) not present originally — must not appear in result
    for i in range(5):
        assert IR(110 + i) not in result


def test_redact_serials_does_not_mutate_original():
    """redact_serials() returns a new cache; the original is unmodified."""
    original_vals = _encode_serial("CE2231A123", IR, 110)
    rc = RegisterCache(original_vals)
    _ = rc.redact_serials()
    for reg, val in original_vals.items():
        assert rc[reg] == val, f"original mutated at {reg}"


def test_redact_serials_empty_cache():
    """redact_serials() on an empty cache returns an empty cache."""
    result = RegisterCache().redact_serials()
    assert len(result) == 0


def test_redact_serials_none_valued_register_skips_group():
    """A group containing a register explicitly set to None is skipped, not crashed."""
    registers = _encode_serial("CE2231A123", IR, 110)
    registers[IR(110)] = None  # corrupt one register in the group
    rc = RegisterCache(registers)
    # Must not raise; the group is skipped so the None value is preserved.
    result = rc.redact_serials()
    assert result.get(IR(110)) is None


def test_redact_serials_bmu_serial_redacted():
    """BMU 0 serial in IR(114-118) is redacted (explicit group, not in REGISTER_LUT)."""
    # BMU serial base = 114 + 120*0 = 114.
    registers = _encode_serial("HX2231A456", IR, 114)
    registers[IR(0)] = 7  # unrelated
    result = RegisterCache(registers).redact_serials()

    expected = _encode_serial("HX2231A000", IR, 114)
    for reg, val in expected.items():
        assert result[reg] == val, f"{reg} mismatch"
    assert result[IR(0)] == 7  # untouched


def test_redact_serials_meter_mr_group():
    """The meter product serial (MR 60-61) is blanked in a share-safe export (audit H2).

    The meter identifier is a short 2-register value that doesn't match the GE serial pattern,
    so it can't be pattern-redacted — redact_serials() zeroes it instead, so a shared export
    doesn't leak the meter identity.
    """
    val = "AB12".encode("latin1")  # 4-char meter identifier across MR(60-61)
    registers = {MR(60): int.from_bytes(val[0:2], "big"), MR(61): int.from_bytes(val[2:4], "big")}

    result = RegisterCache(registers).redact_serials()

    assert result[MR(60)] == 0
    assert result[MR(61)] == 0


def test_redact_serials_byte_swapped_aio_serial_hr8():
    """A byte-swapped AIO serial at HR(8-12) is redacted via RegisterCache.redact_serials() (audit H2).

    AIO firmware stores the unit serial byte-swapped (CH… → HC…) at HR(8-12); HC2114G047 matches
    the standard pattern, so it must redact to HC2114G000. Closes the coverage gap vs the
    FrameRedactor path (already covered in test_capture.py).
    """
    registers = _encode_serial("HC2114G047", HR, 8)
    result = RegisterCache(registers).redact_serials()
    raw = b"".join((result[HR(8 + i)] & 0xFFFF).to_bytes(2, "big") for i in range(5))
    assert raw.decode("latin1").replace("\x00", "").upper() == "HC2114G000"


def test_redact_serials_leaves_partial_group_unchanged():
    """A partially-present serial group is left unchanged and no absent registers are injected.

    Without all registers the group can't be decoded; like the unrecognised-shape case, the cache
    redaction fails open here to avoid destroying data it can't positively identify as a serial.
    """
    registers = {HR(13): 0x5341, HR(14): 0x3231}  # "SA21" fragment of the inverter serial group
    result = RegisterCache(registers).redact_serials()
    assert result[HR(13)] == 0x5341
    assert result[HR(14)] == 0x3231
    assert HR(15) not in result, "absent registers must not be injected"


def test_redact_serials_blanks_partial_meter_identifier():
    """A partial meter identifier is still blanked — MR is a distinct namespace with no overlap.

    Unlike HR/IR (where a partial group can't be distinguished from non-serial data), MR can't
    overlap ordinary registers, so a present fragment is always sensitive and safe to blank.
    """
    result = RegisterCache({MR(60): 0x4142}).redact_serials()  # "AB" fragment; MR(61) absent
    assert result[MR(60)] == 0
    assert MR(61) not in result, "absent MR register must not be injected"
