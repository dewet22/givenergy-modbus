from unittest.mock import MagicMock as Mock

import pytest

from givenergy_modbus.modbus import GivEnergyModbusTcpClient
from givenergy_modbus.model.register import HoldingRegister  # type: ignore  # shut up mypy
from givenergy_modbus.pdu import ReadHoldingRegistersRequest, ReadInputRegistersRequest


def test_read_holding_registers():
    """Ensure we read the ranges of known registers."""
    c = GivEnergyModbusTcpClient()
    mock_call = Mock(name='execute', return_value=Mock(name='ReadHoldingRegistersResponse'))
    c.execute = mock_call
    c.read_holding_registers(2, 22)
    assert mock_call.call_count == 1
    assert mock_call.call_args_list[0].args[0].__class__ == ReadHoldingRegistersRequest
    assert mock_call.call_args_list[0].args[0].base_register == 2
    assert mock_call.call_args_list[0].args[0].register_count == 22


def test_read_input_registers():
    """Ensure we read the ranges of known registers."""
    c = GivEnergyModbusTcpClient()
    mock_call = Mock(name='execute', return_value=Mock(name='ReadInputRegistersResponse'))
    c.execute = mock_call
    c.read_input_registers(3, 33)
    assert mock_call.call_count == 1
    assert mock_call.call_args_list[0].args[0].__class__ == ReadInputRegistersRequest
    assert mock_call.call_args_list[0].args[0].base_register == 3
    assert mock_call.call_args_list[0].args[0].register_count == 33


def test_write_holding_register():
    """Ensure we can write to holding registers."""
    c = GivEnergyModbusTcpClient()
    mock_call = Mock(name='execute', return_value=Mock(value=5, name='WriteHoldingRegisterResponse'))
    c.execute = mock_call
    c.write_holding_register(HoldingRegister.ENABLE_CHARGE_TARGET, 5)
    assert mock_call.call_count == 1

    mock_call = Mock(name='execute', return_value=Mock(value=2, name='WriteHoldingRegisterResponse'))
    c.execute = mock_call
    with pytest.raises(AssertionError) as e:
        c.write_holding_register(HoldingRegister.ENABLE_CHARGE_TARGET, 5)
    assert mock_call.call_count == 1
    assert e.value.args[0] == 'Register read-back value 0x0002 != written value 0x0005.'

    mock_call = Mock(name='execute', return_value=Mock(value=2, name='WriteHoldingRegisterResponse'))
    with pytest.raises(ValueError) as e:
        c.write_holding_register(HoldingRegister.INVERTER_STATE, 5)
    assert mock_call.call_count == 0
    assert e.value.args[0] == 'Register INVERTER_STATE is not safe to write to.'
