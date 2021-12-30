#!/usr/bin/env python
from __future__ import annotations

from pymodbus.client.sync import BaseModbusClient, ModbusTcpClient
from pymodbus.constants import Defaults
from pymodbus.interfaces import IModbusDecoder, IModbusFramer
from pymodbus.transaction import ModbusTransactionManager

from givenergy_modbus.decoder import GivEnergyClientDecoder
from givenergy_modbus.framer import GivModbusFramer
from givenergy_modbus.transaction import GivTransactionManager


class GivEnergyClient(ModbusTcpClient):
    """GivEnergy Modbus Client implementation.

    This class ties together all the pieces to create a client that can converse with a GivEnergy Modbus
    implementation over TCP.
    """

    def __init__(
        self,
        host: str,
        port: int = 8899,
        source_address: tuple[str, int] = ("", 0),
        timeout: int = Defaults.Timeout,
        framer: IModbusFramer = GivModbusFramer,
        decoder: IModbusDecoder = GivEnergyClientDecoder,
        transaction_manager: ModbusTransactionManager = GivTransactionManager,
        **kwargs,
    ):
        """Constructor.

        Args:
            host: The host to connect to, accepts both IPv4 & IPv6
            port: The TCP port to connect to (usually 8899)

            ***Advanced, only change these if you know what you're doing***
            framer: The modbus framer implementation class to use (default GivModbusFramer)
            decoder: The PDU decoder factory implementation class to use (default GivEnergyClientDecoder)
            transaction_manager: The transaction manager class to use (default GivTransactionManager)
            source_address: The source address/port tuple to explicitly bind to, if needed
            timeout: The timeout to use for this socket (default Defaults.Timeout)
            **kwargs:
        """
        self.host = host
        self.port = port
        self.source_address = source_address
        self.socket = None
        self.timeout = timeout
        # hacky patches to work around hard-coding of class names inside pymodbus
        ModbusTcpClient.ClientDecoder = decoder
        BaseModbusClient.DictTransactionManager = transaction_manager
        super().__init__(host=host, port=port, framer=framer, **kwargs)
