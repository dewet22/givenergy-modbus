from __future__ import annotations

from pymodbus.client.sync import ModbusTcpClient

from .decoder import GivEnergyResponseDecoder
from .framer import GivEnergyModbusFramer
from .model.inverter import Inverter
from .model.register_banks import HoldingRegister
from .pdu import ReadHoldingRegistersRequest, ReadInputRegistersRequest, WriteHoldingRegisterRequest
from .transaction import GivEnergyTransactionManager


class GivEnergyModbusClient(ModbusTcpClient):
    """GivEnergy Modbus Client implementation.

    This class ties together all the pieces to create a functional client that can converse with a
    GivEnergy Modbus implementation over TCP. It only needs to exist as a thin wrapper around the
    ModbusTcpClient to hot patch in our own Framer and TransactionManager since there are hardcoded
    classes for Decoder and TransactionManager throughout constructors up the call chain.
    """

    def __init__(self, **kwargs):
        """Constructor."""
        kwargs.setdefault("port", 8899)  # GivEnergy default instead of the standard 502
        super().__init__(**kwargs)
        self.framer = GivEnergyModbusFramer(GivEnergyResponseDecoder(), client=self)
        self.transaction = GivEnergyTransactionManager(client=self, **kwargs)

    def __repr__(self):
        """Return a useful representation."""
        return f"GivEnergyClient({self.host}:{self.port}): timeout={self.timeout})"

    def read_all_holding_registers(self) -> list[int]:
        """Read all known holding registers."""
        return (
            self.execute(ReadHoldingRegistersRequest(base_register=0, register_count=60)).register_values
            + self.execute(ReadHoldingRegistersRequest(base_register=60, register_count=60)).register_values
            + self.execute(ReadHoldingRegistersRequest(base_register=120, register_count=1)).register_values
        )

    def read_all_input_registers(self) -> list[int]:
        """Read all known input registers."""
        return (
            self.execute(ReadInputRegistersRequest(base_register=0, register_count=60)).register_values
            + self.execute(ReadInputRegistersRequest(base_register=60, register_count=60)).register_values
            # Nothing useful lives here apparently, so just fill with zeroes
            # + self.execute(ReadInputRegistersRequest(base_register=120, register_count=60)).register_values
            + [0] * 60
            + self.execute(ReadInputRegistersRequest(base_register=180, register_count=2)).register_values
        )

    def write_holding_register(self, register: HoldingRegister, value: int):
        """Write a value to a single holding register."""
        if not register.write_safe:  # type: ignore  # shut up mypy
            raise ValueError(f'Register {register.name} is not safe to write to.')
        result = self.execute(WriteHoldingRegisterRequest(register=register.value, value=value))
        if result.value != value:
            raise ValueError(f'Returned value {result.value} != written value {value}.')
        return result

    def get_inverter(self) -> Inverter:
        """Return a current view of inverter data."""
        return Inverter(
            holding_registers=self.read_all_holding_registers(), input_registers=self.read_all_input_registers()
        )
