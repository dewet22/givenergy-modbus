from __future__ import annotations

import logging
from abc import ABC

from pymodbus.client.sync import ModbusTcpClient
from pymodbus.exceptions import ModbusIOException

from givenergy_modbus.framer import ClientFramer
from givenergy_modbus.model.register import HoldingRegister, InputRegister, Register  # type: ignore
from givenergy_modbus.pdu import BasePDU
from givenergy_modbus.pdu.read_registers import (
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
    ReadInputRegistersRequest,
    ReadInputRegistersResponse,
    ReadRegistersRequest,
    ReadRegistersResponse,
)
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest, WriteHoldingRegisterResponse

_logger = logging.getLogger(__name__)


class BaseClient(ABC):
    """GivEnergy Modbus Client base class.

    This class ties together all the pieces to create a functional client that can converse with a
    GivEnergy Modbus implementation over TCP. It exists as a thin wrapper around the ModbusTcpClient
    to hot patch in our own Framer and TransactionManager since they are hardcoded classes for Decoder
    and TransactionManager throughout constructors up the call chain.

    We also provide a few convenience methods to read and write registers.
    """

    host: str
    port: int

    def __init__(self, host, **kwargs):
        kwargs.setdefault("port", 8899)  # GivEnergy default instead of the standard 502
        self.host = host
        self.port = kwargs['port']
        self.framer = ClientFramer()
        self.timeout = 2

    def __repr__(self):
        return f"{self.__class__.__name__}({self.host}:{self.port}): timeout={self.timeout})"

    def execute(self, request: BasePDU = None) -> BasePDU | None:
        """Send the given PDU to the remote device and return any PDU returned in response."""
        raise NotImplementedError()

    def read_registers(self, kind: type[Register], base_address: int, register_count: int, **kwargs) -> dict[int, int]:
        """Create and execute requests to read register ranges of the given type."""
        raise NotImplementedError()

    def read_holding_registers(self, address: int, count: int = 60, **kwargs) -> dict[int, int]:
        """Convenience method to help read out holding registers."""
        return self.read_registers(HoldingRegister, address, count, **kwargs)

    def read_input_registers(self, address: int, count: int = 60, **kwargs) -> dict[int, int]:
        """Convenience method to help read out input registers."""
        return self.read_registers(InputRegister, address, count, **kwargs)

    def write_holding_register(self, register: HoldingRegister, value: int) -> None:
        """Write a value to a single holding register."""
        raise NotImplementedError()


class SyncClient(BaseClient, ModbusTcpClient):
    """GivEnergy Modbus synchronous client implementation."""

    def execute(self, request: BasePDU = None) -> BasePDU | None:
        """Send the given PDU to the remote device and return any PDU returned in response."""
        _logger.debug(f'Sending request {request}')
        try:
            response = super().execute(request)
            if isinstance(response, ModbusIOException):
                _logger.exception(response)
            return response
        except ModbusIOException as e:
            _logger.exception(e)
            self.close()
            return None
        except Exception as e:
            # This seems to help with inverters becoming unresponsive from the portal."""
            _logger.exception(e)
            self.close()
            return None

    def read_registers(self, kind: type[Register], base_address: int, register_count: int, **kwargs) -> dict[int, int]:
        """Read out registers from the correct location depending on type specified."""
        t_req: type[ReadRegistersRequest]
        t_res: type[ReadRegistersResponse]
        if kind is HoldingRegister:
            t_req, t_res = ReadHoldingRegistersRequest, ReadHoldingRegistersResponse
        elif kind is InputRegister:
            t_req, t_res = ReadInputRegistersRequest, ReadInputRegistersResponse
        else:
            _logger.error(f'Unknown type of Register specified: {kind}')
            return {}

        response = self.execute(t_req(base_register=base_address, register_count=register_count, **kwargs))
        if response and isinstance(response, t_res):
            if response.base_register != base_address:
                _logger.error(
                    f'Returned base register ({response.base_register}) '
                    f'does not match that from request ({base_address}).'
                )
                return {}
            if response.register_count != register_count:
                _logger.error(
                    f'Returned register count ({response.register_count}) '
                    f'does not match that from request ({register_count}).'
                )
                return {}
            return response.to_dict()
        _logger.error(f'Did not receive expected response type: {t_res.__name__} != {response.__class__.__name__}')
        # FIXME this contract needs improving
        return {}

    def write_holding_register(self, register: HoldingRegister, value: int) -> None:
        """Write a value to a single holding register."""
        if not register.write_safe:  # type: ignore  # shut up mypy
            raise ValueError(f'Register {register.name} is not safe to write to')
        if value != value & 0xFFFF:
            raise ValueError(f'Value {value} must fit in 2 bytes')
        _logger.info(f'Attempting to write {value}/{hex(value)} to Holding Register {register.value}/{register.name}')
        request = WriteHoldingRegisterRequest(register=register.value, value=value)
        result = self.execute(request)
        if isinstance(result, WriteHoldingRegisterResponse):
            if result.value != value:
                raise AssertionError(f'Register read-back value 0x{result.value:04x} != written value 0x{value:04x}')
        else:
            raise AssertionError(f'Unexpected response from remote end: {result}')
