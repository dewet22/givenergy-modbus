import logging
from typing import Dict, List

from pydantic import BaseModel

from givenergy_modbus.client import Message
from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import Inverter
from givenergy_modbus.model.register import HoldingRegister, InputRegister
from givenergy_modbus.model.register_cache import RegisterCache
from givenergy_modbus.pdu.read_registers import ReadHoldingRegistersResponse, ReadInputRegistersResponse
from givenergy_modbus.pdu.transparent import TransparentResponse
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest, WriteHoldingRegisterResponse

_logger = logging.getLogger(__name__)


class Plant(BaseModel):
    """Representation of a complete GivEnergy plant."""

    register_caches: Dict[int, RegisterCache] = {}

    class Config:  # noqa: D106
        # arbitrary_types_allowed = True
        orm_mode = True

    def update(self, message: Message):
        """Update the Plant state from a PDU message."""
        pdu = message.pdu
        if not isinstance(pdu, TransparentResponse):
            _logger.info(f'Ignoring non-Transparent response {pdu}')
            return
        if pdu.error:
            _logger.info(f'Ignoring error response {pdu}')
            return
        _logger.debug(f'Handling {pdu}')

        # transparently store cloud and app updates in the "normal" inverter address
        slave_address = pdu.slave_address if pdu.slave_address not in (0x11, 0x00) else 0x32

        if slave_address not in self.register_caches:
            _logger.debug(f'First time encountering slave address 0x{slave_address:02x}')
            self.register_caches[slave_address] = RegisterCache()

        if isinstance(pdu, ReadHoldingRegistersResponse):
            self.register_caches[slave_address].update_with_validate(
                {HoldingRegister(k): v for k, v in pdu.to_dict().items()}
            )
        elif isinstance(pdu, ReadInputRegistersResponse):
            self.register_caches[slave_address].update_with_validate(
                {InputRegister(k): v for k, v in pdu.to_dict().items()}
            )
        if isinstance(pdu, WriteHoldingRegisterResponse):
            if message.provenance:
                # ensure our own writes were successful
                request_pdu = message.provenance.pdu
                if not isinstance(request_pdu, WriteHoldingRegisterRequest):
                    raise ValueError(f'Incorrect request {request_pdu} for {pdu}')
                if pdu.error or pdu.register != request_pdu.register or pdu.value != request_pdu.value:
                    raise ValueError(f'Register write failed: {pdu} from {request_pdu}')
            else:
                # trust unsolicited updates blindly
                _logger.info(f'Updating from unsolicited {pdu}')
            self.register_caches[slave_address].update_with_validate({pdu.register: pdu.value})

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
