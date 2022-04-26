import logging
from typing import Dict, List

from pydantic import BaseModel

from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import Inverter  # type: ignore  # shut up mypy
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import BasePDU
from givenergy_modbus.pdu.transparent import TransparentResponse

_logger = logging.getLogger(__name__)


class Plant(BaseModel):
    """Representation of a complete GivEnergy plant."""

    register_caches: Dict[int, RegisterCache] = {}

    class Config:  # noqa: D106
        arbitrary_types_allowed = True
        orm_mode = True
        # allow_mutation = False

    def __init__(self, *args, **kwargs):
        """Constructor. Use `number_batteries` to specify the total number of batteries installed."""
        super().__init__(*args, **kwargs)
        if not self.register_caches:  # prepopulate well-known / expected slave addresses
            for i in (0x00, 0x11, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37):
                self.register_caches[i] = RegisterCache(i)

    def update(self, pdu: BasePDU):
        """Update the Plant state using a received Modbus PDU message."""
        if not isinstance(pdu, TransparentResponse):
            return
        if pdu.slave_address not in self.register_caches:
            _logger.warning(f'Unexpected slave address 0x{pdu.slave_address:02x}')
            self.register_caches[pdu.slave_address] = RegisterCache(slave_address=pdu.slave_address)

        self.register_caches[pdu.slave_address].update_from_pdu(pdu)

    @property
    def inverter(self) -> Inverter:
        """Return Inverter model for the Plant."""
        return Inverter.from_orm(self.register_caches[0x32])

    @property
    def number_batteries(self) -> int:
        """Determine the number of batteries connected to the system based on whether the register data is valid."""
        i = 0
        for i in range(6):
            try:
                assert Battery.from_orm(self.register_caches[i + 0x32]).is_valid()
            except (KeyError, AssertionError):
                break
        return i

    @property
    def batteries(self) -> List[Battery]:
        """Return Battery models for the Plant."""
        return [Battery.from_orm(self.register_caches[i + 0x32]) for i in range(self.number_batteries)]
