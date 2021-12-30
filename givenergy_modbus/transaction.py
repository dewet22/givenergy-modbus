from pymodbus.transaction import FifoTransactionManager


class GivTransactionManager(FifoTransactionManager):
    """Implements a ModbusTransactionManager.

    The only reason this exists is to be able to specify the ADU size for automated response frame processing
    since the socket needs to know how many bytes to expect in response to a given Request. See
    `ModbusTransactionManager::execute` where it checks whether the framer is an instance of
    `ModbusSocketFramer` to inform the expected response length, and even lower down the call chain
    in `ModbusTransactionManager::_recv` where there's more byte calculations based on the TransactionManager's
    provenance.

    We could've extended `GivModbusFramer` from `ModbusSocketFramer` instead, but that brings a different set
    of problems around implementation divergence in the GivEnergy implementation that would probably have been
    more work instead. Full novel in the `GivModbusFramer` class description.
    """

    def __init__(self, **kwargs):
        """Constructor."""
        super().__init__(**kwargs)
        self.base_adu_size = 8  # frame length calculation shenanigans, see `GivModbusFramer`
