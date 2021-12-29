from pymodbus.client.sync import BaseModbusClient
from pymodbus.transaction import FifoTransactionManager


class GivTransactionManager(FifoTransactionManager):
    """Implements a ModbusTransactionManager.

    The only reason this exists is to be able to specify the ADU size
    for automated frame header processing. This is because we don't
    extend GivModbusFramer from ModbusSocketFramer which has this
    hardcoded, but we need to specify a different header length because
    GivEnergy calculates its PDU lengths differently from standard
    Modbus.

    TODO have this create correct (fixed) transaction IDs instead of
    overriding in GivModbusFramer::buildPacket
    """

    def __init__(self, client: BaseModbusClient, **kwargs):
        """Constructor.

        Args:
            client: synchronous client socket wrapper
        """
        super().__init__(client, **kwargs)
        self.base_adu_size = 8
