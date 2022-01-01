#!/usr/bin/env python
from __future__ import annotations

from pymodbus.client.sync import ModbusTcpClient

from .decoder import GivEnergyResponseDecoder
from .framer import GivModbusFramer
from .pdu import ReadHoldingRegistersRequest, ReadInputRegistersRequest
from .transaction import GivTransactionManager


class GivEnergyClient(ModbusTcpClient):
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
        self.framer = GivModbusFramer(GivEnergyResponseDecoder(), client=self)
        self.transaction = GivTransactionManager(client=self, **kwargs)

    # def execute(self, request: ModbusPDU = None) -> ModbusPDU:
    #     """This exists purely for type annotations."""
    #     return super().execute(request)

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
            + self.execute(ReadInputRegistersRequest(base_register=120, register_count=60)).register_values
            + self.execute(ReadInputRegistersRequest(base_register=180, register_count=2)).register_values
        )
