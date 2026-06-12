"""Tests for the LV BCU stack-level block model (#241)."""

from givenergy_modbus.model.lv_bcu import LV_BCU_ADDRESS, LvBcu
from givenergy_modbus.model.register import IR
from givenergy_modbus.model.register_cache import RegisterCache


def test_address_constant():
    assert LV_BCU_ADDRESS == 0x31


def test_from_registers_field_values():
    """Decode the block as observed in the field (#238: two LV plants, BMS fw 3022).

    Status words zero, request currents 167 A in both directions — the only
    populated shape seen on real hardware so far.
    """
    bcu = LvBcu.from_register_cache(RegisterCache({IR(60): 0, IR(61): 0, IR(62): 167, IR(63): 167}))
    assert bcu.bms_status_1 == 0
    assert bcu.bms_status_2 == 0
    assert bcu.request_charge_current == 167
    assert bcu.request_discharge_current == 167
    assert bcu.is_valid()


def test_all_zero_block_is_absent():
    """All-zero decodes as absent, not error (firmware-gated, #241).

    Units without the block still answer reads at 0x31 — with zeros — so
    presence requires at least one non-zero word.
    """
    bcu = LvBcu.from_register_cache(RegisterCache({IR(60): 0, IR(61): 0, IR(62): 0, IR(63): 0}))
    assert not bcu.is_valid()


def test_any_nonzero_word_is_present():
    """A non-zero status word alone marks the block present, even with zero currents."""
    bcu = LvBcu.from_register_cache(RegisterCache({IR(60): 1, IR(61): 0, IR(62): 0, IR(63): 0}))
    assert bcu.is_valid()


def test_empty_cache():
    bcu = LvBcu.from_register_cache(RegisterCache())
    assert bcu.bms_status_1 is None
    assert bcu.bms_status_2 is None
    assert bcu.request_charge_current is None
    assert bcu.request_discharge_current is None
    assert not bcu.is_valid()
