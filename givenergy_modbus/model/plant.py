import logging
from typing import Dict, List

from pydantic import BaseModel

from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import Inverter  # type: ignore  # shut up mypy
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu import ModbusPDU

_logger = logging.getLogger(__package__)


class Plant(BaseModel):
    """Representation of a complete GivEnergy plant."""

    register_caches: Dict[int, RegisterCache] = {}
    number_batteries: int = 0

    class Config:  # noqa: D106
        arbitrary_types_allowed = True
        orm_mode = True
        # allow_mutation = False

    def __init__(self, *args, **kwargs):
        """Constructor. Use `number_batteries` to specify the total number of batteries installed."""
        super().__init__(*args, **kwargs)
        # ensure expected RegisterCaches are populated
        if not self.register_caches:
            self.register_caches = {0x32: RegisterCache(0x32)}
        if self.number_batteries > 1:
            for i in range(self.number_batteries - 1):
                self.register_caches[i + 0x33] = RegisterCache(i + 0x33)

    def update(self, pdu: ModbusPDU):
        """Update the Plant state using a received Modbus PDU message."""
        if pdu.slave_address not in self.register_caches:
            _logger.warning(f'Unexpected slave address {hex(pdu.slave_address)}')
            self.register_caches[pdu.slave_address] = RegisterCache(slave_address=pdu.slave_address)
        self.register_caches[pdu.slave_address].update_from_pdu(pdu)

    @property
    def inverter(self) -> Inverter:
        """Return Inverter model for the Plant."""
        return Inverter.from_orm(self.register_caches[0x32])

    @property
    def batteries(self) -> List[Battery]:
        """Return Battery models for the Plant."""
        return [Battery.from_orm(self.register_caches[i + 0x32]) for i in range(self.number_batteries)]
