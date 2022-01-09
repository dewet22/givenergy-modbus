from __future__ import annotations

from pymodbus.client.sync import ModbusTcpClient

from .decoder import GivEnergyResponseDecoder
from .framer import GivEnergyModbusFramer
from .model.register import HoldingRegister  # type: ignore  # no idea why this is failing
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


class GivEnergyModbusTcpClient(ModbusTcpClient):
    """GivEnergy Modbus Client implementation.

    This class ties together all the pieces to create a functional client that can converse with a
    GivEnergy Modbus implementation over TCP. It exists as a thin wrapper around the ModbusTcpClient
    to hot patch in our own Framer and TransactionManager since they are hardcoded classes for Decoder
    and TransactionManager throughout constructors up the call chain.

    We also provide a few convenience methods to read and write registers.
    """

    def __init__(self, **kwargs):
        """Constructor."""
        kwargs.setdefault("port", 8899)  # GivEnergy default instead of the standard 502
        super().__init__(**kwargs)
        self.framer = GivEnergyModbusFramer(GivEnergyResponseDecoder(), client=self)
        self.transaction = GivEnergyTransactionManager(client=self, **kwargs)

    def __repr__(self):
        """Return a user-friendly representation."""
        return f"GivEnergyModbusTcpClient({self.host}:{self.port}): timeout={self.timeout})"

    def execute(self, request: ModbusPDU = None):
        """Send the given PDU to the remote device and return any PDU returned in response."""
        try:
            return super().execute(request)
        except Exception as e:
            # This seems to help with inverters becoming unresponsive from the portal."""
            self.close()
            raise e

    def read_holding_registers(self, address, count=1, **kwargs) -> ReadHoldingRegistersResponse:
        """Read specified Holding Registers and return the Response PDU object."""
        return self.execute(ReadHoldingRegistersRequest(base_register=address, register_count=count, **kwargs))

    def read_input_registers(self, address, count=1, **kwargs) -> ReadInputRegistersResponse:
        """Read specified Input Registers and return the Response PDU object."""
        return self.execute(ReadInputRegistersRequest(base_register=address, register_count=count, **kwargs))

    # def read_all_holding_registers(self) -> list[int]:
    #     """Read all known holding registers."""
    #     return (
    #         self.execute(ReadHoldingRegistersRequest(base_register=0, register_count=60)).register_values
    #         + self.execute(ReadHoldingRegistersRequest(base_register=60, register_count=60)).register_values
    #         + self.execute(ReadHoldingRegistersRequest(base_register=120, register_count=60)).register_values
    #         # + self.execute(ReadHoldingRegistersRequest(base_register=180, register_count=30)).register_values
    #     )

    # def read_all_input_registers(self) -> list[int]:
    #     """Read all known input registers."""
    #     return (
    #         self.execute(ReadInputRegistersRequest(base_register=0, register_count=60)).register_values
    #         + self.execute(ReadInputRegistersRequest(base_register=60, register_count=60)).register_values
    #         + self.execute(ReadInputRegistersRequest(base_register=120, register_count=60)).register_values
    #         + self.execute(ReadInputRegistersRequest(base_register=180, register_count=60)).register_values
    #         + self.execute(ReadInputRegistersRequest(base_register=240, register_count=60)).register_values
    #     )

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
