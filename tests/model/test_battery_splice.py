"""Unit tests for the #256 physics-delta classifier (battery_splice.classify_transition).

These pin the threshold tables and the trip logic independent of Plant, so CI re-confirms
the corpus separation rules directly. The Plant-level integration (reject / escrow / commit)
is exercised in test_plant.py.
"""

from givenergy_modbus.model.battery_splice import (
    BANK_BASE,
    IMMUTABLE,
    IMMUTABLE_SCALAR,
    IMMUTABLE_SERIAL,
    THRESHOLD_BY_CLASS,
    classify_transition,
)


def _baseline() -> list[int]:
    """A physically-plausible length-60 raw bank (bank-relative; index i == IR(60+i))."""
    bank = [0] * 60
    for i in range(0, 16):  # cells 3.300 V
        bank[i] = 3300
    for i in range(16, 20):  # cell-mass temps 25.0 °C
        bank[i] = 250
    bank[20] = 52800  # v_cells_sum mV
    bank[21] = 260  # t_bms_mosfet deci
    bank[23] = 52800  # v_out low word
    bank[25] = bank[27] = bank[29] = bank[42] = 16000  # cap pairs low words (centiAh)
    bank[37] = 16  # num_cells
    bank[38] = 3005  # bms_firmware_version
    bank[40] = 55  # soc %
    bank[43], bank[44] = 250, 240  # t_max, t_min
    bank[45], bank[46] = 1000, 1200  # lifetime energy
    bank[50], bank[51], bank[52], bank[53], bank[54] = 0x4247, 0x3132, 0x3334, 0x3536, 0x3738
    bank[55] = 8  # usb_device_inserted (mutable, exempt)
    return bank


def test_identical_banks_have_no_trips():
    base = _baseline()
    assert classify_transition(base, list(base)) == ([], [])


def test_ir115_is_dropped_from_immutable():
    """IR(115) (bank index 55) must not be immutable — it's a mutable usb_device_inserted field."""
    assert 55 not in IMMUTABLE
    assert IMMUTABLE == [37, 38, 50, 51, 52, 53, 54]


def test_immutable_scalar_serial_partition_covers_immutable():
    """The scalar/serial split (#281) partitions IMMUTABLE exactly — no overlap, no gap.

    Scalar/serial sets are ABSOLUTE IR numbers (to match a trip's ``trip[0]``); IMMUTABLE is
    the bank-relative union the classifier loops over.
    """
    assert IMMUTABLE_SCALAR == {97, 98}  # num_cells, bms_firmware_version
    assert IMMUTABLE_SERIAL == {110, 111, 112, 113, 114}  # serial block
    assert IMMUTABLE_SCALAR.isdisjoint(IMMUTABLE_SERIAL)
    assert {BANK_BASE + i for i in IMMUTABLE} == IMMUTABLE_SCALAR | IMMUTABLE_SERIAL


def test_single_cell_voltage_step_is_one_physics_trip():
    base = _baseline()
    new = list(base)
    new[5] = 3700  # +400 mV > 300 mV threshold (#299)
    phys, immut = classify_transition(base, new)
    assert immut == []
    assert phys == [(BANK_BASE + 5, "cell_mV", 3300, 3700)]


def test_within_threshold_jitter_does_not_trip():
    base = _baseline()
    new = list(base)
    new[5] = 3449  # +149 mV, within the 150 mV threshold
    new[16] = 299  # +49 deci, within the 50 threshold
    assert classify_transition(base, new) == ([], [])


def test_constant_register_change_is_immutable_violation():
    base = _baseline()
    new = list(base)
    new[38] = 3006  # bms_firmware_version changed by one
    phys, immut = classify_transition(base, new)
    assert phys == []
    assert immut == [(98, "IMMUTABLE", 3005, 3006)]


def test_serial_change_is_immutable_violation():
    base = _baseline()
    new = list(base)
    new[50] = 0x4248  # first serial word changed
    _phys, immut = classify_transition(base, new)
    assert immut == [(110, "IMMUTABLE", 0x4247, 0x4248)]


def test_pair_rule_uses_assembled_uint32_value():
    """cap_remaining is the IR(88)/IR(89) pair; the trip must report the assembled uint32s."""
    base = _baseline()
    new = list(base)
    new[29] = 36000  # cap_remaining low word: 160 Ah -> 360 Ah
    phys, immut = classify_transition(base, new)
    assert immut == []
    assert phys == [(88, "cap_centiAh", 16000, 36000)]  # high index, assembled values


def test_two_independent_physics_deltas_both_reported():
    base = _baseline()
    new = list(base)
    new[14] = 3700  # a cell, +400 mV > 300 mV threshold (#299)
    new[43] = 0  # t_max to zero
    phys, immut = classify_transition(base, new)
    assert immut == []
    assert {p[0] for p in phys} == {BANK_BASE + 14, 103}


def test_present_gating_skips_rules_with_absent_registers():
    base = _baseline()
    new = list(base)
    new[5] = 3600  # would trip cell_mV...
    # ...but exclude index 5 from `present`, so the rule is skipped.
    present = set(range(60)) - {5}
    assert classify_transition(base, new, present=present) == ([], [])


def test_present_gating_skips_pair_rule_with_absent_register():
    """A PAIR rule is skipped when either of its two words is absent from `present`."""
    base = _baseline()
    new = list(base)
    new[29] = 36000  # would trip the cap_remaining (28, 29) pair...
    present = set(range(60)) - {29}  # ...but its low word is absent, so skip
    assert classify_transition(base, new, present=present) == ([], [])


def test_present_gating_skips_immutable_with_absent_register():
    """An IMMUTABLE check is skipped when its register is absent from `present`."""
    base = _baseline()
    new = list(base)
    new[38] = 3006  # would be a bms_firmware_version immutable violation...
    present = set(range(60)) - {38}  # ...but it's absent, so skip
    assert classify_transition(base, new, present=present) == ([], [])


def test_threshold_table_covers_every_rule_class():
    """Every class name used by a rule must resolve in THRESHOLD_BY_CLASS (escrow lookup)."""
    from givenergy_modbus.model.battery_splice import PAIR_RULES, SCALAR_RULES

    for name, _idxs, thr in SCALAR_RULES:
        assert THRESHOLD_BY_CLASS[name] == thr
    for name, _pair, thr in PAIR_RULES:
        assert THRESHOLD_BY_CLASS[name] == thr


def test_is_corruption_cohort_detects_temp_zero_shape():
    """>=2 cell-mass temps (IR76-79) at zero is the corruption cohort; a clean bank is not (#289)."""
    from givenergy_modbus.model.battery_splice import is_corruption_cohort

    assert not is_corruption_cohort(_baseline())  # temps 250 — plausible
    one_zero = _baseline()
    one_zero[16] = 0
    assert not is_corruption_cohort(one_zero)  # a lone zero temp is not the cohort
    two_zero = _baseline()
    two_zero[16] = two_zero[17] = 0
    assert is_corruption_cohort(two_zero)  # >=2 zero temps → cohort


def test_is_corruption_cohort_skips_absent_temps():
    """A never-read temp register (absent from ``present``) is not counted as a zero (#289)."""
    from givenergy_modbus.model.battery_splice import is_corruption_cohort

    frame = _baseline()  # temps populated and non-zero
    # Two temps absent from the read: their 0-fill must not be mistaken for the corruption cohort.
    present = set(range(60)) - {16, 17}
    frame[16] = frame[17] = 0
    assert not is_corruption_cohort(frame, present)


def test_heal_eligible_accepts_in_range_voltage_cap_trips():
    """A bank whose trips are all voltage/cap-class surges in absolute range is heal-eligible (#299)."""
    from givenergy_modbus.model.battery_splice import heal_eligible

    # cell_mV (3800, in 1000-5000) + v_out_mV (56000, in 16000-80000): both eligible, in range.
    assert heal_eligible([(60, "cell_mV", 3300, 3800), (82, "v_out_mV", 52800, 56000)])
    assert heal_eligible([(84, "cap_centiAh", 16000, 18000)])
    assert not heal_eligible([])  # nothing to heal


def test_heal_eligible_rejects_temp_soc_energy_classes():
    """Any temp/SOC/energy trip makes a bank ineligible — the class-restriction safety spine (#299).

    Covers the IR(103/104) t_max/t_min temp-zero corruption shape that ``is_corruption_cohort``
    (IR76-79 only) does not catch: it's ``cell_temp_deci`` class, so it can never heal.
    """
    from givenergy_modbus.model.battery_splice import heal_eligible

    assert not heal_eligible([(60, "cell_mV", 3300, 3800), (103, "cell_temp_deci", 250, 0)])
    assert not heal_eligible([(81, "mosfet_temp_deci", 260, 800)])
    assert not heal_eligible([(100, "soc_pct", 55, 95)])
    assert not heal_eligible([(105, "e_total_deci", 1000, 2000)])


def test_heal_eligible_rejects_out_of_range_value():
    """A voltage-class trip at a physically impossible value is not heal-eligible (range gate, #299)."""
    from givenergy_modbus.model.battery_splice import heal_eligible

    assert not heal_eligible([(60, "cell_mV", 3300, 5200), (65, "cell_mV", 3300, 5200)])  # >5.0 V
    assert not heal_eligible([(60, "cell_mV", 3300, 500)])  # <1.0 V
