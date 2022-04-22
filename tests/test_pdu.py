import pytest

from givenergy_modbus.model.register import HoldingRegister  # type: ignore  # shut up mypy
from givenergy_modbus.pdu.heartbeat import *
from givenergy_modbus.pdu.null import NullResponse
from givenergy_modbus.pdu.read_registers import *
from givenergy_modbus.pdu.write_registers import *
from tests import ALL_MESSAGES, CLIENT_MESSAGES, SERVER_MESSAGES, PduTestCaseSig, _lookup_pdu_class


def test_str():
    """Ensure human-friendly string representations."""
    # ABCs before main function definitions
    assert '/BasePDU(' not in str(BasePDU())
    assert '/Request(' not in str(Request())
    assert '/Response(' not in str(Response())
    assert str(BasePDU()).startswith('<givenergy_modbus.pdu.BasePDU object at ')
    assert str(Request()).startswith('<givenergy_modbus.pdu.Request object at ')
    assert str(Request(foo=1)).startswith('<givenergy_modbus.pdu.Request object at ')

    # __str__() gets defined at the main function ABC
    assert str(HeartbeatMessage(foo=3, bar=6)) == (
        '1/HeartbeatMessage(data_adapter_serial_number=AB1234G567 data_adapter_type=0)'
    )
    assert str(HeartbeatMessage(data_adapter_serial_number='xxx', data_adapter_type=33)) == (
        '1/HeartbeatMessage(data_adapter_serial_number=xxx data_adapter_type=33)'
    )
    assert str(HeartbeatRequest(foo=3, bar=6)) == (
        '1/HeartbeatRequest(data_adapter_serial_number=AB1234G567 data_adapter_type=0)'
    )
    assert str(HeartbeatResponse(data_adapter_serial_number='xxx', data_adapter_type=33)) == (
        '1/HeartbeatResponse(data_adapter_serial_number=xxx data_adapter_type=33)'
    )

    assert str(TransparentMessage(foo=3, bar=6)) == '2:_/TransparentMessage()'
    assert str(TransparentRequest(foo=3, bar=6)) == '2:_/TransparentRequest()'
    assert str(TransparentRequest(inner_function_code=44)) == '2:_/TransparentRequest()'
    assert str(TransparentResponse(foo=3, bar=6)) == '2:_/TransparentResponse()'
    assert str(TransparentResponse(inner_function_code=44)) == '2:_/TransparentResponse()'

    assert str(ReadRegisters()) == '2:_/ReadRegisters(base_register=0 register_count=0)'
    assert str(ReadRegisters(foo=1)) == '2:_/ReadRegisters(base_register=0 register_count=0)'
    assert str(ReadRegisters(base_register=50)) == '2:_/ReadRegisters(base_register=50 register_count=0)'

    assert str(ReadRegistersRequest(base_register=3, register_count=6)) == (
        '2:_/ReadRegistersRequest(base_register=3 register_count=6)'
    )
    assert str(NullResponse(foo=1)) == "2:0/NullResponse()"

    assert str(ReadHoldingRegistersRequest(foo=1)) == (
        "2:3/ReadHoldingRegistersRequest(base_register=0 register_count=0)"
    )

    assert str(WriteHoldingRegisterRequest(foo=1)) == "2:6/WriteHoldingRegisterRequest(register=? value=?)"
    assert str(WriteHoldingRegisterResponse(foo=1)) == "2:6/WriteHoldingRegisterResponse(register=? value=?)"
    assert str(WriteHoldingRegisterResponse(error=True, register=3, value=5)) == (
        "2:6/WriteHoldingRegisterResponse(ERROR register=3 value=5)"
    )
    assert str(WriteHoldingRegisterResponse(error=True, inverter_serial_number='SA1234G567', register=3, value=5)) == (
        "2:6/WriteHoldingRegisterResponse(ERROR inverter_serial_number=SA1234G567 register=3 value=5)"
    )

    assert str(HeartbeatRequest(foo=1)) == (
        "1/HeartbeatRequest(data_adapter_serial_number=AB1234G567 data_adapter_type=0)"
    )
    assert str(HeartbeatResponse(foo=1)) == (
        "1/HeartbeatResponse(data_adapter_serial_number=AB1234G567 data_adapter_type=0)"
    )


@pytest.mark.parametrize(PduTestCaseSig, CLIENT_MESSAGES + SERVER_MESSAGES)
def test_str_actual_messages(pdu_class_name, constructor_kwargs, mbap_header, inner_frame, ex, str_repr):
    # pdu_class_name, constructor_kwargs, _, _, expected_exception, str_repr = data

    pdu = _lookup_pdu_class(pdu_class_name)(**constructor_kwargs)
    assert str(pdu) == str_repr


def test_class_equivalence():
    """Confirm some behaviours on subclassing."""
    assert issubclass(ReadHoldingRegistersRequest, ReadRegistersRequest)
    assert issubclass(ReadInputRegistersRequest, ReadRegistersRequest)
    assert not issubclass(ReadHoldingRegistersRequest, ReadInputRegistersRequest)
    assert isinstance(ReadHoldingRegistersRequest(), ReadRegistersRequest)
    assert isinstance(ReadInputRegistersRequest(), ReadRegistersRequest)
    assert not isinstance(ReadInputRegistersRequest(), ReadHoldingRegistersRequest)
    assert ReadInputRegistersRequest is ReadInputRegistersRequest


def test_cannot_change_function_code():
    """Disabuse any use of function_code in PDU constructors."""
    assert not hasattr(Request(), 'function_code')
    assert not hasattr(Request(), 'main_function_code')
    assert not hasattr(Request(), 'inner_function_code')

    assert ReadHoldingRegistersRequest(error=True).inner_function_code == 3

    assert ReadHoldingRegistersRequest(function_code=12).main_function_code != 12
    assert ReadHoldingRegistersRequest(main_function_code=12).main_function_code != 12
    assert ReadHoldingRegistersRequest(inner_function_code=12).main_function_code != 12
    assert ReadHoldingRegistersRequest(function_code=12).inner_function_code != 12
    assert ReadHoldingRegistersRequest(main_function_code=12).inner_function_code != 12
    assert ReadHoldingRegistersRequest(inner_function_code=12).inner_function_code != 12


@pytest.mark.parametrize(PduTestCaseSig, ALL_MESSAGES)
def test_server_encoding(str_repr, pdu_class_name, constructor_kwargs, mbap_header, inner_frame, ex):
    """Ensure we correctly encode unencapsulated Request messages."""
    pdu = _lookup_pdu_class(pdu_class_name)(**constructor_kwargs)
    if ex:
        with pytest.raises(ex.__class__, match=ex.args[0]) as e:
            pdu.encode()
        assert e.value.args == (ex.args[0], pdu)
    else:
        assert pdu.encode() == inner_frame


@pytest.mark.parametrize(PduTestCaseSig, ALL_MESSAGES)
def test_server_decoding(str_repr, pdu_class_name, constructor_kwargs, mbap_header, inner_frame, ex):
    """Ensure we correctly decode Request messages to their unencapsulated PDU."""
    pdu = _lookup_pdu_class(pdu_class_name)()
    if ex:
        with pytest.raises(ex.__class__, match=ex.args[0]) as e:
            pdu.decode(inner_frame)
        assert e.value.args == (ex.args[0], pdu)
    else:
        pdu.decode(inner_frame)
        for (arg, val) in constructor_kwargs.items():
            assert hasattr(pdu, arg)
            assert getattr(pdu, arg) == val, f'<obj>.{arg} == {getattr(pdu, arg)}, expected {val}'


def test_writable_registers_match():
    """Ensure HoldingRegisters declared write-safe match the WriteHoldingRegisterRequest allow list."""
    write_safe_holding_registers = set()
    for r in HoldingRegister.__members__.values():
        if r.write_safe:
            write_safe_holding_registers.add(r.value)

    assert WriteHoldingRegisterRequest.writable_registers == write_safe_holding_registers


def test_read_registers_response_as_dict():
    """Ensure a ReadRegistersResponse can be turned into a dict representation."""
    r = ReadHoldingRegistersResponse(base_register=100, register_count=10, register_values=list(range(10))[::-1])
    assert r.to_dict() == {100: 9, 101: 8, 102: 7, 103: 6, 104: 5, 105: 4, 106: 3, 107: 2, 108: 1, 109: 0}

    r = ReadHoldingRegistersResponse(base_register=1000, register_count=10, register_values=['a'] * 10)
    assert r.to_dict() == {
        1000: 'a',
        1001: 'a',
        1002: 'a',
        1003: 'a',
        1004: 'a',
        1005: 'a',
        1006: 'a',
        1007: 'a',
        1008: 'a',
        1009: 'a',
    }


def test_has_same_shape():
    """Ensure we can compare PDUs sensibly."""
    r1 = ReadInputRegistersResponse()
    r2 = ReadInputRegistersResponse()
    assert r1._shape_hash() == r2._shape_hash()
    assert r1.has_same_shape(r2)
    assert r1 != r2
    assert r1.has_same_shape(ReadInputRegistersRequest()) is False
    assert r1.has_same_shape(object()) is NotImplemented
    r2 = ReadInputRegistersResponse(slave_address=3)
    assert r1.has_same_shape(r2) is False
    r2 = ReadInputRegistersResponse(base_register=1)
    assert r1.has_same_shape(r2) is False

    r1 = ReadInputRegistersResponse(register_count=2, register_values=[33, 45])
    r2 = ReadInputRegistersResponse(register_count=2, register_values=[10, 11])
    assert r1.has_same_shape(r2)
    assert r1 != r2
    r1 = ReadInputRegistersResponse(register_count=2, register_values=[10, 11])
    assert r1.has_same_shape(r2)
    assert r1 != r2

    test_set = {r1, r2}
    assert len(test_set) == 2
    assert r1 in test_set
    assert r2 in test_set

    r = WriteHoldingRegisterResponse()
    assert r.has_same_shape(WriteHoldingRegisterResponse())
    assert r.has_same_shape(WriteHoldingRegisterResponse(value=10))
    assert r.has_same_shape(WriteHoldingRegisterRequest()) is False
    assert r.has_same_shape(ReadInputRegistersResponse()) is False
    assert r.has_same_shape(ReadInputRegistersRequest()) is False
    assert r.has_same_shape(WriteHoldingRegisterResponse(slave_address=3)) is False
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=1)) is False
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=2, value=10)) is False

    r1 = WriteHoldingRegisterResponse(register=2, value=42)
    r2 = WriteHoldingRegisterResponse(register=2, value=10)
    assert r1.has_same_shape(r2)
    assert r1 != r2
    r1 = WriteHoldingRegisterResponse(register=2, value=10)
    assert r1 != r2

    test_set = {r1, r2}
    assert len(test_set) == 2
    assert r1 in test_set
    assert r2 in test_set
