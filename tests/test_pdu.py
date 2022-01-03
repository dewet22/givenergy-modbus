from typing import Any

import pytest

from givenergy_modbus.pdu import (
    ModbusRequest,
    ReadHoldingRegistersRequest,
    ReadRegistersRequest,
    ReadRegistersResponse,
    WriteHoldingRegisterRequest,
)

from . import REQUEST_PDU_MESSAGES, RESPONSE_PDU_MESSAGES, _lookup_pdu_class


def test_str():
    """Test we can represent an instance of PDUs nicely."""
    assert str(ReadRegistersRequest(base_register=3, register_count=6)) == (
        "_/ReadRegistersRequest({check: 0x0000, base_register: 0x0003, register_count: 0x0006})"
    )
    assert str(ModbusRequest(foo=1)) == "_/ModbusRequest({check: 0x0000})"
    assert str(ModbusRequest) == "<class 'givenergy_modbus.pdu.ModbusRequest'>"
    assert str(ModbusRequest(foo=1)) == "_/ModbusRequest({check: 0x0000})"
    assert str(ModbusRequest) == "<class 'givenergy_modbus.pdu.ModbusRequest'>"

    assert str(ReadHoldingRegistersRequest(foo=1)) == (
        "3/ReadHoldingRegistersRequest({check: 0x0000, base_register: 0x0000, register_count: 0x0000})"
    )
    assert str(ReadHoldingRegistersRequest) == "<class 'givenergy_modbus.pdu.ReadHoldingRegistersRequest'>"

    assert str(WriteHoldingRegisterRequest(foo=1)) == (
        "6/WriteHoldingRegisterRequest({check: 0x0000, register: None, value: None})"
    )
    assert str(WriteHoldingRegisterRequest) == "<class 'givenergy_modbus.pdu.WriteHoldingRegisterRequest'>"


def test_cannot_change_function_code():
    """Prevent (accidentally) changing the function_code via kwargs in the constructor."""
    assert ModbusRequest()
    assert ReadHoldingRegistersRequest(function_code=3)

    with pytest.raises(ValueError) as e:
        assert ModbusRequest(function_code=12)
    assert e.value.args[0] == "Specified function code 12 is different from what _/ModbusRequest() is expecting."

    with pytest.raises(ValueError) as e:
        ReadRegistersRequest(function_code=12, base_register=3, register_count=6)
    assert e.value.args[0] == (
        "Specified function code 12 is different from what _/ReadRegistersRequest() is expecting."
    )

    with pytest.raises(ValueError) as e:
        assert ReadHoldingRegistersRequest(function_code=14)
    assert e.value.args[0] == (
        "Specified function code 14 is different from what 3/ReadHoldingRegistersRequest() is expecting."
    )


@pytest.mark.parametrize("data", REQUEST_PDU_MESSAGES)
def test_request_pdu_encoding(data: tuple[str, dict[str, Any], bytes, bytes]):
    """Ensure we correctly encode unencapsulated Request messages."""
    pdu_fn, pdu_fn_kwargs, mbap_head, encoded_pdu = data

    pdu: ReadRegistersRequest = _lookup_pdu_class(pdu_fn)(**pdu_fn_kwargs)
    assert pdu.encode() == encoded_pdu


@pytest.mark.parametrize("data", REQUEST_PDU_MESSAGES)
def test_request_pdu_decoding(data: tuple[str, dict[str, Any], bytes, bytes]):
    """Ensure we correctly decode Request messages to their unencapsulated PDU."""
    pdu_fn, pdu_fn_kwargs, mbap_head, encoded_pdu = data

    pdu: ReadRegistersRequest = _lookup_pdu_class(pdu_fn)()
    pdu.decode(encoded_pdu)
    if pdu_fn_kwargs:
        i = 0
        for (arg, val) in pdu_fn_kwargs.items():
            i += 1
            assert getattr(pdu, arg) == val, f'test {i}: "{arg}" value was not decoded/stored correctly'
        assert i == len(pdu_fn_kwargs.keys())
        assert i > 0


@pytest.mark.parametrize("data", RESPONSE_PDU_MESSAGES)
def test_response_pdu_encoding(data: tuple[str, dict[str, Any], bytes, bytes]):
    """Ensure we correctly encode unencapsulated Response messages."""
    pdu_fn, pdu_fn_kwargs, _, encoded_pdu = data

    pdu: ReadRegistersResponse = _lookup_pdu_class(pdu_fn)(**pdu_fn_kwargs)
    assert pdu.encode() == encoded_pdu


@pytest.mark.parametrize("data", RESPONSE_PDU_MESSAGES)
def test_response_pdu_decoding(data: tuple[str, dict[str, Any], bytes, bytes]):
    """Ensure we correctly decode Response messages to their unencapsulated PDU."""
    pdu_fn, pdu_fn_kwargs, mbap_header, encoded_pdu = data

    pdu: ReadRegistersResponse = _lookup_pdu_class(pdu_fn)()
    pdu.decode(encoded_pdu)
    if pdu_fn_kwargs:
        i = 0
        for (arg, val) in pdu_fn_kwargs.items():
            i += 1
            assert getattr(pdu, arg) == val, f'test {i}: "{arg}" value was not decoded/stored correctly'
        assert i == len(pdu_fn_kwargs.keys())
        assert i > 0
