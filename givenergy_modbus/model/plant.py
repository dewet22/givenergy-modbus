import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import ConfigDict

from givenergy_modbus.model import GivEnergyBaseModel
from givenergy_modbus.model.battery import Battery, BatteryRegisterGetter
from givenergy_modbus.model.ems import Ems
from givenergy_modbus.model.gateway import Gateway, Gateway2, select_gateway
from givenergy_modbus.model.hv_bcu import Bcu, BcuRegisterGetter, Bmu, HvStack
from givenergy_modbus.model.inverter import Model, SinglePhaseInverter, SinglePhaseInverterRegisterGetter
from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter, select_inverter
from givenergy_modbus.model.meter import Meter, MeterRegisterGetter
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

# Models whose battery architecture is HV (BCU/BMU stacks rather than LV packs).
# Coarse families "4" (HYBRID_3PH), "6" (AC_3PH) and "8" (ALL_IN_ONE and variants)
# are all HV; specific sub-variants are included explicitly.
_HV_MODELS: frozenset[Model] = frozenset(
    {
        Model.HYBRID_3PH,
        Model.AC_3PH,
        Model.ALL_IN_ONE,
        Model.HYBRID_HV_GEN3,
        Model.ALL_IN_ONE_HYBRID,
    }
)


@dataclass
class PlantCapabilities:
    """Describes the hardware topology discovered by Client.detect().

    Returned by Client.detect(); callers assign it to plant.capabilities or
    persist it for faster restarts (see fork-merge-plan deferred items).
    """

    device_type: Model
    inverter_slave: int = 0x32
    meter_slaves: list[int] = field(default_factory=list)
    lv_battery_slaves: list[int] = field(default_factory=list)
    # Each entry is (slave_offset, num_modules) where the BCU slave address is 0x70 + slave_offset.
    bcu_slaves: list[tuple[int, int]] = field(default_factory=list)

    @property
    def is_hv(self) -> bool:
        """Return True if this system uses HV battery stacks (BCU/BMU) rather than LV packs."""
        return self.device_type in _HV_MODELS

    def to_dict(self) -> dict:
        """Serialise to a JSON-safe dict for persistence."""
        return {
            "device_type": self.device_type.value,
            "inverter_slave": self.inverter_slave,
            "meter_slaves": self.meter_slaves,
            "lv_battery_slaves": self.lv_battery_slaves,
            "bcu_slaves": [list(s) for s in self.bcu_slaves],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlantCapabilities":
        """Deserialise from a previously persisted dict."""
        return cls(
            device_type=Model(data["device_type"]),
            inverter_slave=data["inverter_slave"],
            meter_slaves=data["meter_slaves"],
            lv_battery_slaves=data["lv_battery_slaves"],
            bcu_slaves=[tuple(s) for s in data["bcu_slaves"]],  # type: ignore[misc]
        )


class Plant(GivEnergyBaseModel):
    """Representation of a complete GivEnergy plant."""

    model_config = ConfigDict(frozen=False, use_enum_values=True, arbitrary_types_allowed=True)

    register_caches: dict[int, RegisterCache] = {}
    capabilities: PlantCapabilities | None = None
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
        if 0x01 <= slave_address <= 0x08:
            return MeterRegisterGetter
        if 0x33 <= slave_address <= 0x37:
            return BatteryRegisterGetter
        if 0x70 <= slave_address <= 0x8F:
            return BcuRegisterGetter
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
            if not getter_cls.is_coherent(incoming, self.register_caches[slave_address]):
                _logger.warning("Discarding incoherent register bank for slave 0x%02x", slave_address)
                return
            violations = getter_cls.validate_bank(incoming, self.register_caches[slave_address])
            if violations:
                _logger.error(
                    "Bounds violations in register bank for slave 0x%02x: %s",
                    slave_address,
                    violations,
                )
                # TODO(enforcement): add `return` here to discard the entire bank on any violation.
        self.register_caches[slave_address].update(incoming)

    @property
    def inverter(self) -> SinglePhaseInverter | ThreePhaseInverter:
        """Return the inverter model, dispatching on device type when capabilities are available."""
        if self.capabilities:
            return select_inverter(
                self.capabilities.device_type, self.register_caches[self.capabilities.inverter_slave]
            )
        return SinglePhaseInverter.from_register_cache(self.register_caches[0x32])

    @property
    def number_batteries(self) -> int:
        """Determine the number of batteries connected to the system based on whether the register data is valid."""
        if self.capabilities:
            return len(self.capabilities.lv_battery_slaves)
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
        if self.capabilities:
            return [
                Battery.from_register_cache(self.register_caches[addr])
                for addr in self.capabilities.lv_battery_slaves
                if addr in self.register_caches
            ]
        return [Battery.from_register_cache(self.register_caches[i + 0x32]) for i in range(self.number_batteries)]

    @property
    def hv_stacks(self) -> list[HvStack]:
        """Return HV battery stacks (BCU + BMUs) for HV systems; empty list for LV systems."""
        if not self.capabilities or not self.capabilities.bcu_slaves:
            return []
        stacks = []
        for offset, num_modules in self.capabilities.bcu_slaves:
            slave_addr = 0x70 + offset
            cache = self.register_caches.get(slave_addr, RegisterCache())
            bcu = Bcu.from_register_cache(cache)
            bmus = [Bmu.from_register_cache(cache, i) for i in range(num_modules)]
            stacks.append(HvStack(slave_address=slave_addr, bcu=bcu, bmus=bmus))
        return stacks

    @property
    def meters(self) -> dict[int, Meter]:
        """Return Meter models keyed by slave address."""
        if not self.capabilities or not self.capabilities.meter_slaves:
            return {}
        return {
            addr: Meter.from_register_cache(self.register_caches[addr])
            for addr in self.capabilities.meter_slaves
            if addr in self.register_caches
        }

    @property
    def ems(self) -> Ems | None:
        """Return Ems model for EMS/EMS_COMMERCIAL device types; None otherwise."""
        if not self.capabilities or self.capabilities.device_type not in (Model.EMS, Model.EMS_COMMERCIAL):
            return None
        cache = self.register_caches.get(self.capabilities.inverter_slave, RegisterCache())
        return Ems.from_register_cache(cache)

    @property
    def gateway(self) -> Gateway | Gateway2 | None:
        """Return Gateway or Gateway2 model for GATEWAY device type; None otherwise."""
        if not self.capabilities or self.capabilities.device_type != Model.GATEWAY:
            return None
        cache = self.register_caches.get(self.capabilities.inverter_slave, RegisterCache())
        return select_gateway(cache)
