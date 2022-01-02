from datetime import time

import pytest

from givenergy_modbus.pdu import ReadInputRegistersRequest
from givenergy_modbus.util import charge_slot_to_time_range, friendly_class_name, hexlify, hexxed


def test_friendly_class_name():
    """Test our class names, including from other modules."""
    assert str(ReadInputRegistersRequest) == "<class 'givenergy_modbus.pdu.ReadInputRegistersRequest'>"
    assert friendly_class_name(ReadInputRegistersRequest) == "ReadInputRegistersRequest"
    assert friendly_class_name(ReadInputRegistersRequest(foo=1, bar=2)) == "ReadInputRegistersRequest"


def test_hexlify():
    """Test our hexlify representations."""
    assert hexlify(0x0) == '00'
    assert hexlify(4) == '04'
    assert hexlify(0x438734873847) == '4387 3487 3847'
    assert hexlify('asdf') == 'asdf'
    assert hexlify(0.5) == '0.5'


def test_hexxed():
    """Test our hex representations."""
    assert hexxed(0x0) == '0x0000'
    assert hexxed(4) == '0x0004'
    assert hexxed(0x438734873847) == '0x438734873847'
    assert hexxed('asdf') == 'asdf'
    assert hexxed(0.5) == 0.5


def test_charge_slot_to_time_range():
    """Ensure we can convert BCD-encoded time slots."""
    assert charge_slot_to_time_range(0, 0) == (time(hour=0, minute=0), time(hour=0, minute=0))
    assert charge_slot_to_time_range(30, 430) == (time(hour=0, minute=30), time(hour=4, minute=30))
    assert charge_slot_to_time_range(123, 234) == (time(hour=1, minute=23), time(hour=2, minute=34))
    with pytest.raises(ValueError) as e:
        charge_slot_to_time_range(678, 789)
    assert e.value.args[0] == 'minute must be in 0..59'
    with pytest.raises(ValueError) as e:
        charge_slot_to_time_range(9999, 9999)
    assert e.value.args[0] == 'hour must be in 0..23'
