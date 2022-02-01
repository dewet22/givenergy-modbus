import sys
from unittest.mock import MagicMock as Mock

import pytest

from givenergy_modbus.modbus import GivEnergyModbusTcpClient
from givenergy_modbus.model.register import HoldingRegister  # type: ignore  # shut up mypy
from givenergy_modbus.pdu import (
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
    ReadInputRegistersRequest,
    ReadInputRegistersResponse,
    WriteHoldingRegisterResponse,
)


class MockedReadHoldingRegistersResponse(Mock, ReadHoldingRegistersResponse):  # noqa: D101
    __test__ = False  # squelch PytestCollectionWarning


class MockedReadInputRegistersResponse(Mock, ReadInputRegistersResponse):  # noqa: D101
    __test__ = False  # squelch PytestCollectionWarning


class MockedWriteHoldingRegisterResponse(Mock, WriteHoldingRegisterResponse):  # noqa: D101
    __test__ = False  # squelch PytestCollectionWarning


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
def test_read_holding_registers():
    """Ensure we read the ranges of known registers."""
    c = GivEnergyModbusTcpClient()
    response = Mock(name='ReadHoldingRegistersResponse', base_register=2, register_count=22)
    mock_call = Mock(name='execute', return_value=response)
    c.execute = mock_call
    c.read_holding_registers(2, 22)
    assert mock_call.call_count == 1
    assert mock_call.call_args_list[0].args[0].__class__ == ReadHoldingRegistersRequest
    assert mock_call.call_args_list[0].args[0].base_register == 2
    assert mock_call.call_args_list[0].args[0].register_count == 22


def test_read_holding_registers_validates_response_base_register():
    """Ensure we read the ranges of known registers."""
    c = GivEnergyModbusTcpClient()
    response = MockedReadHoldingRegistersResponse(base_register=33, register_count=22)
    mock_call = Mock(name='execute', return_value=response)
    c.execute = mock_call
    assert c.read_holding_registers(2, 22) == {}


def test_read_holding_registers_validates_response_register_count():
    """Ensure we read the ranges of known registers."""
    c = GivEnergyModbusTcpClient()
    response = MockedReadHoldingRegistersResponse(base_register=33, register_count=22)
    mock_call = Mock(name='execute', return_value=response)
    c.execute = mock_call
    assert c.read_holding_registers(33, 11) == {}


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
def test_read_input_registers():
    """Ensure we read the ranges of known registers."""
    c = GivEnergyModbusTcpClient()
    response = Mock(name='ReadInputRegistersResponse', base_register=33, register_count=22)
    mock_call = Mock(name='execute', return_value=response)
    c.execute = mock_call
    c.read_input_registers(33, 22)
    assert mock_call.call_count == 1
    assert mock_call.call_args_list[0].args[0].__class__ == ReadInputRegistersRequest
    assert mock_call.call_args_list[0].args[0].base_register == 33
    assert mock_call.call_args_list[0].args[0].register_count == 22


def test_read_input_registers_validates_response_base_register():
    """Ensure we read the ranges of known registers."""
    c = GivEnergyModbusTcpClient()
    response = MockedReadInputRegistersResponse(base_register=33, register_count=22)
    mock_call = Mock(name='execute', return_value=response)
    c.execute = mock_call
    assert c.read_input_registers(2, 22) == {}


def test_read_input_registers_validates_response_register_count():
    """Ensure we read the ranges of known registers."""
    c = GivEnergyModbusTcpClient()
    response = MockedReadInputRegistersResponse(base_register=33, register_count=22)
    mock_call = Mock(name='execute', return_value=response)
    c.execute = mock_call
    assert c.read_input_registers(33, 11) == {}


@pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8 or higher")
def test_write_holding_register():
    """Ensure we can write to holding registers."""
    c = GivEnergyModbusTcpClient()
    mock_call = Mock(name='execute', return_value=MockedWriteHoldingRegisterResponse(value=5))
    c.execute = mock_call
    c.write_holding_register(HoldingRegister.ENABLE_CHARGE_TARGET, 5)
    assert mock_call.call_count == 1
    assert str(mock_call.call_args_list[0].args[0]) == (
        '6/WriteHoldingRegisterRequest({check: 0x0000, register: 0x0014, value: 0x0005})'
    )

    mock_call = Mock(name='execute', return_value=MockedWriteHoldingRegisterResponse(value=2))
    c.execute = mock_call
    with pytest.raises(AssertionError) as e:
        c.write_holding_register(HoldingRegister.ENABLE_CHARGE_TARGET, 5)
    assert e.value.args[0] == 'Register read-back value 0x0002 != written value 0x0005'
    assert mock_call.call_count == 1
    assert str(mock_call.call_args_list[0].args[0]) == (
        '6/WriteHoldingRegisterRequest({check: 0x0000, register: 0x0014, value: 0x0005})'
    )

    mock_call = Mock(name='execute', return_value=MockedWriteHoldingRegisterResponse(value=2))
    with pytest.raises(ValueError) as e:
        c.write_holding_register(HoldingRegister.INVERTER_STATE, 5)
    assert e.value.args[0] == 'Register INVERTER_STATE is not safe to write to'
    assert mock_call.call_count == 0
