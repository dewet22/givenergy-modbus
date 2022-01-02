from unittest.mock import MagicMock as Mock

from givenergy_modbus.client import GivEnergyModbusClient
from givenergy_modbus.pdu import ReadHoldingRegistersRequest, ReadInputRegistersRequest


def test_read_all_holding_registers():
    """Ensure we read the ranges of known registers."""
    c = GivEnergyModbusClient()
    mock_call = Mock(name='execute', return_value=Mock(register_values=[1, 2, 3], name='ReadHoldingRegistersResponse'))
    c.execute = mock_call
    assert c.read_all_holding_registers() == [1, 2, 3, 1, 2, 3, 1, 2, 3]
    assert mock_call.call_count == 3
    req1 = mock_call.call_args_list[0].args[0]
    req2 = mock_call.call_args_list[1].args[0]
    req3 = mock_call.call_args_list[2].args[0]

    assert req1.__class__ == ReadHoldingRegistersRequest
    assert req1.base_register == 0
    assert req1.register_count == 60
    assert req2.__class__ == ReadHoldingRegistersRequest
    assert req2.base_register == 60
    assert req2.register_count == 60
    assert req3.__class__ == ReadHoldingRegistersRequest
    assert req3.base_register == 120
    assert req3.register_count == 1


def test_read_all_input_registers():
    """Ensure we read the ranges of known registers."""
    c = GivEnergyModbusClient()
    mock_call = Mock(name='execute', return_value=Mock(register_values=[1, 2, 3], name='ReadInputRegistersResponse'))
    c.execute = mock_call
    assert c.read_all_input_registers() == [1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3]
    assert mock_call.call_count == 4
    req1 = mock_call.call_args_list[0].args[0]
    req2 = mock_call.call_args_list[1].args[0]
    req3 = mock_call.call_args_list[2].args[0]
    req4 = mock_call.call_args_list[3].args[0]

    assert req1.__class__ == ReadInputRegistersRequest
    assert req1.base_register == 0
    assert req1.register_count == 60
    assert req2.__class__ == ReadInputRegistersRequest
    assert req2.base_register == 60
    assert req2.register_count == 60
    assert req3.__class__ == ReadInputRegistersRequest
    assert req3.base_register == 120
    assert req3.register_count == 60
    assert req4.__class__ == ReadInputRegistersRequest
    assert req4.base_register == 180
    assert req4.register_count == 2
