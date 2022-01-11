from __future__ import annotations

import logging

from pymodbus.client.sync import ModbusTcpClient

from .decoder import GivEnergyResponseDecoder
from .framer import GivEnergyModbusFramer
from .model.register import HoldingRegister  # type: ignore
from .pdu import (
    ModbusPDU,
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
    ReadInputRegistersRequest,
    ReadInputRegistersResponse,
    WriteHoldingRegisterRequest,
    WriteHoldingRegisterResponse,
)
from .transaction import GivEnergyTransactionManager

_logger = logging.getLogger(__package__)


class GivEnergyModbusTcpClient(ModbusTcpClient):
    """GivEnergy Modbus Client implementation.

    This class ties together all the pieces to create a functional client that can converse with a
    GivEnergy Modbus implementation over TCP. It exists as a thin wrapper around the ModbusTcpClient
    to hot patch in our own Framer and TransactionManager since they are hardcoded classes for Decoder
    and TransactionManager throughout constructors up the call chain.

    We also provide a few convenience methods to read and write registers.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("port", 8899)  # GivEnergy default instead of the standard 502
        super().__init__(**kwargs)
        self.framer = GivEnergyModbusFramer(GivEnergyResponseDecoder(), client=self)
        self.transaction = GivEnergyTransactionManager(client=self, **kwargs)

    def __repr__(self):
        return f"GivEnergyModbusTcpClient({self.host}:{self.port}): timeout={self.timeout})"

    def execute(self, request: ModbusPDU = None):
        """Send the given PDU to the remote device and return any PDU returned in response."""
        _logger.info(f'Sending request {request}')
        try:
            return super().execute(request)
        except Exception as e:
            # This seems to help with inverters becoming unresponsive from the portal."""
            self.close()
            raise e

    def read_holding_registers(self, address, count=1, **kwargs) -> ReadHoldingRegistersResponse:
        """Read specified Holding Registers and return the Response PDU object."""
        ret: ReadHoldingRegistersResponse = self.execute(
            ReadHoldingRegistersRequest(base_register=address, register_count=count, **kwargs)
        )
        if ret.base_register != address:
            raise AssertionError(
                f'Returned base register ({ret.base_register}) ' f'does not match that from request ({address}).'
            )
        if ret.register_count != count:
            raise AssertionError(
                f'Returned register count ({ret.register_count}) ' f'does not match that from request ({count}).'
            )
        return ret

    def read_input_registers(self, address, count=1, **kwargs) -> ReadInputRegistersResponse:
        """Read specified Input Registers and return the Response PDU object."""
        ret: ReadInputRegistersResponse = self.execute(
            ReadInputRegistersRequest(base_register=address, register_count=count, **kwargs)
        )
        if ret.base_register != address:
            raise AssertionError(
                f'Returned base register ({ret.base_register}) ' f'does not match that from request ({address}).'
            )
        if ret.register_count != count:
            raise AssertionError(
                f'Returned register count ({ret.register_count}) ' f'does not match that from request ({count}).'
            )
        return ret

    def write_holding_register(self, register: HoldingRegister, value: int) -> None:
        """Write a value to a single holding register."""
        if not register.write_safe:  # type: ignore  # shut up mypy
            raise ValueError(f'Register {register.name} is not safe to write to.')
        if value != value & 0xFFFF:
            raise ValueError(f'Value {value} must fit in 2 bytes.')
        result: WriteHoldingRegisterResponse = self.execute(
            WriteHoldingRegisterRequest(register=register.value, value=value)
        )
        if result.value != value:
            raise AssertionError(f'Register read-back value 0x{result.value:04x} != written value 0x{value:04x}.')
