from givenergy_modbus.pdu import ReadInputRegistersRequest
from givenergy_modbus.util import friendly_class_name, hexxed


def test_friendly_class_name():
    """Test our class names, including from other modules."""
    assert str(ReadInputRegistersRequest) == "<class 'givenergy_modbus.pdu.ReadInputRegistersRequest'>"
    assert friendly_class_name(ReadInputRegistersRequest) == "ReadInputRegistersRequest"
    assert friendly_class_name(ReadInputRegistersRequest(foo=1, bar=2)) == "ReadInputRegistersRequest"


def test_hexxed():
    """Test our hex representations."""
    assert hexxed(0x0) == '0x0000'
    assert hexxed(4) == '0x0004'
    assert hexxed(0x438734873847) == '0x438734873847'
    assert hexxed('asdf') == 'asdf'
    assert hexxed(0.5) == 0.5
