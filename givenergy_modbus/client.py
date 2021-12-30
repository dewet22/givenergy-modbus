#!/usr/bin/env python
from __future__ import annotations

from pymodbus.client.sync import ModbusTcpClient

from .decoder import GivEnergyResponseDecoder
from .framer import GivModbusFramer
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
