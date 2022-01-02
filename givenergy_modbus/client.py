#!/usr/bin/env python
from __future__ import annotations

from typing import cast

from pymodbus.client.sync import ModbusTcpClient

from .decoder import GivEnergyResponseDecoder
from .framer import GivEnergyModbusFramer
from .model.inverter import Inverter, InverterData
from .pdu import ReadHoldingRegistersRequest, ReadInputRegistersRequest
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
            + self.execute(ReadInputRegistersRequest(base_register=120, register_count=60)).register_values
            + self.execute(ReadInputRegistersRequest(base_register=180, register_count=2)).register_values
        )

    def refresh(self) -> InverterData:
        """Return a refreshed view of inverter data."""
        return cast(
            InverterData,
            Inverter(
                holding_registers=self.read_all_holding_registers(), input_registers=self.read_all_input_registers()
            ).as_dict(),
        )
