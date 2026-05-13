import logging
from typing import Any

from pydantic import ConfigDict

from givenergy_modbus.model import GivEnergyBaseModel
from givenergy_modbus.model.battery import Battery, BatteryRegisterGetter
from givenergy_modbus.model.inverter import SinglePhaseInverter, SinglePhaseInverterRegisterGetter
from givenergy_modbus.model.register import HR, IR, RegisterGetter
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

    model_config = ConfigDict(frozen=False, use_enum_values=True, arbitrary_types_allowed=True)

    register_caches: dict[int, RegisterCache] = {}
    inverter_serial_number: str = ""
    data_adapter_serial_number: str = ""

    def model_post_init(self, __context: Any) -> None:
        """Ensure a default register cache is always present."""
        if not self.register_caches:
            self.register_caches = {0x32: RegisterCache()}

    def _getter_for_slave(self, slave_address: int) -> type[RegisterGetter] | None:
        """Return the RegisterGetter class appropriate for a given slave address."""
        if slave_address == 0x32:
            return SinglePhaseInverterRegisterGetter
        if 0x33 <= slave_address <= 0x37:
            return BatteryRegisterGetter
        return None

    def update(self, pdu: ClientIncomingMessage):
        """Update the Plant state from a PDU message."""
        if not isinstance(pdu, TransparentResponse):
            _logger.debug(f"Ignoring non-Transparent response {pdu}")
            return
        if isinstance(pdu, NullResponse):
            _logger.debug(f"Ignoring Null response {pdu}")
            return
        if pdu.error:
            _logger.debug(f"Ignoring error response {pdu}")
            return
        _logger.debug(f"Handling {pdu}")

        if pdu.slave_address in (0x11, 0x00):
            # rewrite cloud and mobile app responses to "normal" inverter address
            slave_address = 0x32
        else:
            slave_address = pdu.slave_address

        if slave_address not in self.register_caches:
            _logger.debug(f"First time encountering slave address 0x{slave_address:02x}")
            self.register_caches[slave_address] = RegisterCache()

        self.inverter_serial_number = pdu.inverter_serial_number
        self.data_adapter_serial_number = pdu.data_adapter_serial_number

        if isinstance(pdu, ReadHoldingRegistersResponse):
            incoming = {HR(k): v for k, v in pdu.to_dict().items()}
            self._commit_bank(slave_address, incoming)
        elif isinstance(pdu, ReadInputRegistersResponse):
            incoming = {IR(k): v for k, v in pdu.to_dict().items()}
            self._commit_bank(slave_address, incoming)
        elif isinstance(pdu, WriteHoldingRegisterResponse):
            if pdu.register == 0:
                _logger.warning(f"Ignoring, likely corrupt: {pdu}")
            else:
                self.register_caches[slave_address].update({HR(pdu.register): pdu.value})

    def _commit_bank(self, slave_address: int, incoming: dict) -> None:
        """Validate incoming register bank against bounds and commit if clean."""
        getter_cls = self._getter_for_slave(slave_address)
        if getter_cls is not None:
            violations = getter_cls.validate_bank(incoming, self.register_caches[slave_address])
            if violations:
                _logger.warning(
                    "Discarding register bank for slave 0x%02x: bounds violations in %s",
                    slave_address,
                    violations,
                )
                return
        self.register_caches[slave_address].update(incoming)

    @property
    def inverter(self) -> SinglePhaseInverter:
        """Return SinglePhaseInverter model for the Plant."""
        return SinglePhaseInverter.from_register_cache(self.register_caches[0x32])

    @property
    def number_batteries(self) -> int:
        """Determine the number of batteries connected to the system based on whether the register data is valid."""
        count = 0
        for i in range(6):
            try:
                battery = Battery.from_register_cache(self.register_caches[i + 0x32])
            except (KeyError, ValueError):  # fmt: skip  # TODO: drop parens when 3.13 support ends (PEP 758)
                # KeyError: no cache for that slave yet. ValueError: an enum-typed
                # register held a value outside the known set. Either way, treat as
                # "not a battery" and stop probing rather than aborting the caller.
                break
            if not battery.is_valid():
                break
            count += 1
        return count

    @property
    def batteries(self) -> list[Battery]:
        """Return Battery models for the Plant."""
        return [Battery.from_register_cache(self.register_caches[i + 0x32]) for i in range(self.number_batteries)]
