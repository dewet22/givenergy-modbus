import logging
from typing import Any, Dict, Optional, Type

import pytest

from givenergy_modbus.exceptions import ExceptionBase, InvalidFrame, InvalidPduState
from givenergy_modbus.model.register import HoldingRegister
from givenergy_modbus.pdu import (
    BasePDU,
    ClientIncomingMessage,
    ClientOutgoingMessage,
    HeartbeatMessage,
    HeartbeatRequest,
    HeartbeatResponse,
    NullResponse,
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
    ReadInputRegistersRequest,
    ReadInputRegistersResponse,
    ReadRegistersMessage,
    ReadRegistersRequest,
    TransparentMessage,
    TransparentRequest,
    TransparentResponse,
    WriteHoldingRegisterRequest,
    WriteHoldingRegisterResponse,
)
from givenergy_modbus.pdu.write_registers import WRITE_SAFE_REGISTERS
from tests.conftest import ALL_MESSAGES, PduTestCaseSig


def test_str():
    """Ensure human-friendly string representations."""
    # ABCs before main function definitions
    assert '/BasePDU(' not in str(BasePDU())
    assert '/Request(' not in str(ClientIncomingMessage())
    assert '/Response(' not in str(ClientOutgoingMessage())
    assert str(BasePDU()).startswith('<givenergy_modbus.pdu.base.BasePDU object at ')
    assert str(ClientIncomingMessage()).startswith('<givenergy_modbus.pdu.base.ClientIncomingMessage object at ')
    assert str(ClientIncomingMessage(foo=1)).startswith('<givenergy_modbus.pdu.base.ClientIncomingMessage object at ')

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

    assert str(TransparentMessage(foo=3, bar=6)) == '2:_/TransparentMessage(slave_address=0x32)'
    assert str(TransparentRequest(foo=3, bar=6)) == '2:_/TransparentRequest(slave_address=0x32)'
    assert str(TransparentRequest(inner_function_code=44)) == '2:_/TransparentRequest(slave_address=0x32)'
    assert str(TransparentResponse(foo=3, bar=6)) == '2:_/TransparentResponse(slave_address=0x32)'
    assert str(TransparentResponse(inner_function_code=44)) == '2:_/TransparentResponse(slave_address=0x32)'

    assert str(ReadRegistersMessage()) == (
        '2:_/ReadRegistersMessage(slave_address=0x32 base_register=0 register_count=0)'
    )
    assert str(ReadRegistersMessage(foo=1)) == (
        '2:_/ReadRegistersMessage(slave_address=0x32 base_register=0 register_count=0)'
    )
    assert str(ReadRegistersMessage(base_register=50)) == (
        '2:_/ReadRegistersMessage(slave_address=0x32 base_register=50 register_count=0)'
    )

    assert str(ReadRegistersRequest(base_register=3, register_count=6)) == (
        '2:_/ReadRegistersRequest(slave_address=0x32 base_register=3 register_count=6)'
    )
    assert str(NullResponse(foo=1)) == '2:0/NullResponse(slave_address=0x32 nulls=[0]*62)'

    assert str(ReadHoldingRegistersRequest(foo=1)) == (
        '2:3/ReadHoldingRegistersRequest(slave_address=0x32 base_register=0 register_count=0)'
    )

    with pytest.raises(InvalidPduState, match='Register must be set'):
        WriteHoldingRegisterRequest(foo=1)
    with pytest.raises(InvalidPduState, match='Register must be set'):
        WriteHoldingRegisterResponse(foo=1)
    assert str(WriteHoldingRegisterResponse(register=18, value=7)) == (
        '2:6/WriteHoldingRegisterResponse(HoldingRegister(18)/INVERTER_BATTERY_BMS_FIRMWARE_VERSION -> 7/0x0007)'
    )
    assert str(WriteHoldingRegisterResponse(error=True, register=7, value=6)) == (
        '2:6/WriteHoldingRegisterResponse(ERROR HoldingRegister(7)/ENABLE_AMMETER -> True/0x0006)'
    )
    assert str(WriteHoldingRegisterResponse(error=True, inverter_serial_number='SA1234G567', register=18, value=5)) == (
        '2:6/WriteHoldingRegisterResponse(ERROR HoldingRegister(18)/INVERTER_BATTERY_BMS_FIRMWARE_VERSION -> 5/0x0005)'
    )

    assert str(HeartbeatRequest(foo=1)) == (
        '1/HeartbeatRequest(data_adapter_serial_number=AB1234G567 data_adapter_type=0)'
    )
    assert str(HeartbeatResponse(foo=1)) == (
        '1/HeartbeatResponse(data_adapter_serial_number=AB1234G567 data_adapter_type=0)'
    )


@pytest.mark.parametrize(PduTestCaseSig, ALL_MESSAGES)
def test_str_actual_messages(
    str_repr: str,
    pdu_class: Type[BasePDU],
    constructor_kwargs: Dict[str, Any],
    mbap_header: bytes,
    inner_frame: bytes,
    ex: Optional[ExceptionBase],
):
    assert str(pdu_class(**constructor_kwargs)) == str_repr


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
    assert not hasattr(ClientIncomingMessage, 'function_code')
    assert not hasattr(ClientIncomingMessage, 'function_code')
    assert not hasattr(ClientIncomingMessage, 'transparent_function_code')
    assert not hasattr(ClientIncomingMessage(), 'function_code')
    assert not hasattr(ClientIncomingMessage(), 'function_code')
    assert not hasattr(ClientIncomingMessage(), 'transparent_function_code')

    assert ReadHoldingRegistersRequest(error=True).transparent_function_code == 3

    assert ReadHoldingRegistersRequest(function_code=12).function_code != 12
    assert ReadHoldingRegistersRequest(main_function_code=12).function_code != 12
    assert ReadHoldingRegistersRequest(transparent_function_code=12).function_code != 12
    assert ReadHoldingRegistersRequest(function_code=12).transparent_function_code != 12
    assert ReadHoldingRegistersRequest(main_function_code=12).transparent_function_code != 12
    assert ReadHoldingRegistersRequest(transparent_function_code=12).transparent_function_code != 12


@pytest.mark.parametrize(PduTestCaseSig, ALL_MESSAGES)
def test_encoding(
    str_repr: str,
    pdu_class: Type[BasePDU],
    constructor_kwargs: Dict[str, Any],
    mbap_header: bytes,
    inner_frame: bytes,
    ex: Optional[ExceptionBase],
):
    """Ensure PDU objects can be encoded to the correct wire format."""
    pdu = pdu_class(**constructor_kwargs)
    if ex:
        with pytest.raises(type(ex), match=ex.message):
            pdu.encode()
    else:
        assert pdu.encode().hex() == (mbap_header + inner_frame).hex()


@pytest.mark.parametrize(PduTestCaseSig, ALL_MESSAGES)
def test_decoding(
    str_repr: str,
    pdu_class: Type[BasePDU],
    constructor_kwargs: Dict[str, Any],
    mbap_header: bytes,
    inner_frame: bytes,
    ex: Optional[ExceptionBase],
    caplog,
):
    """Ensure we correctly decode Request messages to their unencapsulated PDU."""
    assert mbap_header[-1] == pdu_class.function_code
    frame = mbap_header + inner_frame
    caplog.set_level(logging.DEBUG)  # FIXME remove

    if issubclass(pdu_class, ClientIncomingMessage):
        decoder = ClientIncomingMessage.decode_bytes
    else:
        decoder = ClientOutgoingMessage.decode_bytes

    if ex:
        with pytest.raises(type(ex), match=ex.message):
            decoder(frame)
    else:
        constructor_kwargs['raw_frame'] = mbap_header + inner_frame
        pdu = decoder(frame)
        assert isinstance(pdu, pdu_class)
        assert pdu.__dict__ == constructor_kwargs
        assert str(pdu) == str_repr


@pytest.mark.parametrize(PduTestCaseSig, ALL_MESSAGES)
def test_decoding_wrong_streams(
    str_repr: str,
    pdu_class: Type[BasePDU],
    constructor_kwargs: Dict[str, Any],
    mbap_header: bytes,
    inner_frame: bytes,
    ex: Optional[ExceptionBase],
):
    """Ensure we correctly decode Request messages to their unencapsulated PDU."""
    if ex:
        return
    frame = mbap_header + inner_frame

    if issubclass(pdu_class, ClientIncomingMessage):
        decoder = ClientIncomingMessage.decode_bytes
    else:
        decoder = ClientOutgoingMessage.decode_bytes

    with pytest.raises(InvalidFrame, match='Transaction ID 0x[0-9a-f]{4} != 0x5959'):
        decoder(frame[2:])
    with pytest.raises(
        InvalidFrame, match=f'Header length {len(frame) - 6} != remaining frame length {len(frame) - 8}'
    ):
        decoder(frame[:-2])
    with pytest.raises(
        InvalidFrame, match=f'Header length {len(frame) - 6} != remaining frame length {len(frame) - 4}'
    ):
        decoder(frame + b'\x22\x22')
    with pytest.raises(InvalidFrame, match='Transaction ID 0x[0-9a-f]{4} != 0x5959'):
        decoder(frame[-10:])
    with pytest.raises(InvalidFrame, match='Transaction ID 0x[0-9a-f]{4} != 0x5959'):
        decoder(frame[::-1])


@pytest.mark.skip('Needs more thinking')
def test_writable_registers_equality():
    req = WriteHoldingRegisterRequest(register=4, value=22)
    assert req.register == HoldingRegister(4)
    assert str(req) == '2:6/WriteHoldingRegisterRequest(HoldingRegister(4)/HOLDING_REG004 -> 22/0x0016)'
    assert req == WriteHoldingRegisterRequest(register=4, value=22)
    assert req != WriteHoldingRegisterRequest(register=4, value=32)
    assert req != WriteHoldingRegisterRequest(register=5, value=22)
    assert req != WriteHoldingRegisterResponse(register=4, value=22)

    req = WriteHoldingRegisterResponse(register=5, value=33)
    assert req.register == HoldingRegister(5)
    assert str(req) == '2:6/WriteHoldingRegisterResponse(HoldingRegister(5)/HOLDING_REG005 -> 33/0x0021)'
    assert req != WriteHoldingRegisterRequest(register=5, value=22)

    req = WriteHoldingRegisterResponse(register=6, value=55, error=True)
    assert req.register == HoldingRegister(6)
    assert str(req) == '2:6/WriteHoldingRegisterResponse(ERROR HoldingRegister(6)/HOLDING_REG006 -> 55/0x0037)'
    assert req != WriteHoldingRegisterRequest(register=6, value=55)
    assert req == WriteHoldingRegisterResponse(register=6, value=55)
    assert req == WriteHoldingRegisterResponse(register=6, value=55, error=True)


def test_writable_registers_consistent():
    """Ensure HoldingRegisters declared write-safe match the WriteHoldingRegisterRequest allow list."""
    write_safe_holding_registers = set()
    for r in HoldingRegister.__members__.values():
        if r.write_safe:
            write_safe_holding_registers.add(r)

    assert WRITE_SAFE_REGISTERS == write_safe_holding_registers


@pytest.mark.parametrize('r', range(max(map(lambda x: x.value, HoldingRegister.__members__.values()))))
def test_non_writable_registers_raise(r: int):
    hr = HoldingRegister(r)
    if hr in WRITE_SAFE_REGISTERS:
        WriteHoldingRegisterRequest(register=hr, value=22).ensure_valid_state()
    else:
        with pytest.raises(InvalidPduState, match=f'{hr.name} is not safe to write to'):
            WriteHoldingRegisterRequest(register=hr, value=22).ensure_valid_state()


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
    assert r1.shape_hash() == r2.shape_hash()
    assert r1.has_same_shape(r2)
    assert r1 != r2
    assert r1.has_same_shape(ReadInputRegistersRequest()) is False
    with pytest.raises(NotImplementedError):
        r1.has_same_shape(object())
    r2 = ReadInputRegistersResponse(slave_address=3)
    assert r1.has_same_shape(r2) is False
    r2 = ReadInputRegistersResponse(base_register=1)
    assert r1.has_same_shape(r2) is False

    r1 = ReadInputRegistersResponse(base_register=1, register_count=2, register_values=[33, 45])
    r2 = ReadInputRegistersResponse(base_register=1, register_count=2, register_values=[10, 11])
    assert r1.has_same_shape(r2)
    assert r1 != r2
    r2 = ReadInputRegistersResponse(error=True, base_register=1, register_count=2, register_values=[3])
    assert r1.has_same_shape(r2)
    assert r1 != r2
    r2 = ReadInputRegistersResponse(error=True, register_count=2, register_values=[])
    assert r1.has_same_shape(r2) is False
    assert r1 != r2

    test_set = {r1, r2}
    assert len(test_set) == 2
    assert r1 in test_set
    assert r2 in test_set

    r = WriteHoldingRegisterResponse(register=2)
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=2))
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=2, value=10))
    assert r.has_same_shape(WriteHoldingRegisterRequest(register=2)) is False
    assert r.has_same_shape(ReadInputRegistersResponse(register=2)) is False
    assert r.has_same_shape(ReadInputRegistersRequest(register=2)) is False
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=2, slave_address=3)) is False
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=1)) is False
    assert r.has_same_shape(WriteHoldingRegisterResponse(register=3, value=10)) is False

    r1 = WriteHoldingRegisterResponse(register=2, value=42)
    r2 = WriteHoldingRegisterResponse(register=2, value=10)
    assert r1.has_same_shape(r2)
    assert r1 != r2


@pytest.mark.skip('Needs more thinking')
def test_hashing():
    r1 = WriteHoldingRegisterResponse(register=2, value=10)
    r2 = WriteHoldingRegisterResponse(register=2, value=10)
    assert r1 == r2

    test_set = {
        WriteHoldingRegisterResponse(register=2, value=42),
        WriteHoldingRegisterResponse(register=2, value=10),
        WriteHoldingRegisterResponse(register=2, value=10),
    }
    assert len(test_set) == 2
    assert WriteHoldingRegisterResponse(register=2, value=42) in test_set
    assert WriteHoldingRegisterResponse(register=2, value=10) in test_set

    assert (
        len(
            {
                WriteHoldingRegisterRequest(register=2, value=42),
                WriteHoldingRegisterResponse(register=2, value=42),
            }
        )
        == 2
    )


def test_expected_response():
    req = ReadInputRegistersRequest(base_register=34, register_count=2)
    res = req.expected_response()
    assert isinstance(res, ReadInputRegistersResponse)
    assert res.base_register == req.base_register
    assert res.register_count == req.register_count
    assert res.slave_address == req.slave_address

    assert res != req
    assert req.has_same_shape(res) is False
    assert req.expected_response().has_same_shape(res)
    assert res.has_same_shape(req) is False
