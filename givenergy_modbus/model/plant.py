import logging
from typing import Any

from givenergy_modbus.model import GivEnergyBaseModel
from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import Inverter
from givenergy_modbus.model.register import HoldingRegister, InputRegister
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import (
    ClientIncomingMessage,
    NullResponse,
    ReadHoldingRegistersResponse,
    ReadInputRegistersResponse,
    TransparentResponse,
    WriteHoldingRegisterResponse,
)

_logger = logging.getLogger(__name__)


class Plant(GivEnergyBaseModel):
    """Representation of a complete GivEnergy plant."""

    register_caches: dict[int, RegisterCache] = {}
    inverter_serial_number: str = ''
    data_adapter_serial_number: str = ''

    class Config:  # noqa: D106
        allow_mutation = True
        frozen = False

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if not self.register_caches:
            self.register_caches = {0x32: RegisterCache()}

    def update(self, pdu: ClientIncomingMessage):
        """Update the Plant state from a PDU message."""
        if not isinstance(pdu, TransparentResponse):
            _logger.debug(f'Ignoring non-Transparent response {pdu}')
            return
        if isinstance(pdu, NullResponse):
            _logger.debug(f'Ignoring Null response {pdu}')
            return
        if pdu.error:
            _logger.debug(f'Ignoring error response {pdu}')
            return
        _logger.debug(f'Handling {pdu}')

        # transparently store cloud and app updates in the "normal" inverter address
        slave_address = pdu.slave_address if pdu.slave_address not in (0x11, 0x00) else 0x32

        if slave_address not in self.register_caches:
            _logger.debug(f'First time encountering slave address 0x{slave_address:02x}')
            self.register_caches[slave_address] = RegisterCache()

        self.inverter_serial_number = pdu.inverter_serial_number
        self.data_adapter_serial_number = pdu.data_adapter_serial_number

        if isinstance(pdu, ReadHoldingRegistersResponse):
            self.register_caches[slave_address].update({HoldingRegister(k): v for k, v in pdu.to_dict().items()})
        elif isinstance(pdu, ReadInputRegistersResponse):
            self.register_caches[slave_address].update({InputRegister(k): v for k, v in pdu.to_dict().items()})
        elif isinstance(pdu, WriteHoldingRegisterResponse):
            if pdu.register == HoldingRegister(0):
                _logger.warning(f'Ignoring, likely corrupt: {pdu}')
            self.register_caches[slave_address].update({pdu.register: pdu.value})

    @property
    def inverter(self) -> Inverter:
        """Return Inverter model for the Plant."""
        return Inverter.from_registers(self.register_caches[0x32])

    @property
    def number_batteries(self) -> int:
        """Determine the number of batteries connected to the system based on whether the register data is valid."""
        i = 0
        for i in range(6):
            try:
                assert Battery.from_registers(self.register_caches[i + 0x32]).is_valid()
            except (KeyError, AssertionError):
                break
        return i

    @property
    def batteries(self) -> list[Battery]:
        """Return Battery models for the Plant."""
        return [Battery.from_registers(self.register_caches[i + 0x32]) for i in range(self.number_batteries)]
