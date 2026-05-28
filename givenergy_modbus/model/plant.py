import logging
import warnings
from dataclasses import dataclass, field
from typing import Any

from pydantic import ConfigDict

from givenergy_modbus.model import GivEnergyBaseModel
from givenergy_modbus.model.battery import Battery, BatteryRegisterGetter
from givenergy_modbus.model.devices import Inverter as UnifiedInverter
from givenergy_modbus.model.ems import Ems
from givenergy_modbus.model.gateway import GatewayV1, GatewayV2, select_gateway
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

# Models with registers in the 1000-range (HR 1000–1124, IR 1000–1413).
_THREE_PHASE_MODELS: frozenset[Model] = frozenset(
    {
        Model.HYBRID_3PH,
        Model.AC_3PH,
        Model.AIO_COMMERCIAL,
        Model.ALL_IN_ONE,
        Model.ALL_IN_ONE_HYBRID,
        Model.HYBRID_HV_GEN3,
    }
)

# Models that use the extended 10-slot map (HR 240–299 for slots 3–10).
_EXTENDED_SLOT_MODELS: frozenset[Model] = frozenset(
    {
        Model.HYBRID_GEN3,
        Model.HYBRID_GEN4,
        Model.ALL_IN_ONE,
        Model.ALL_IN_ONE_HYBRID,
        Model.HYBRID_HV_GEN3,
    }
)


_CAPABILITIES_LEGACY_ALIASES = {
    "inverter_slave": "inverter_address",
    "meter_slaves": "meter_addresses",
    "lv_battery_slaves": "lv_battery_addresses",
    "bcu_slaves": "bcu_stacks",
}


@dataclass(init=False)
class PlantCapabilities:
    """Describes the hardware topology discovered by Client.detect().

    Returned by Client.detect(); callers assign it to plant.capabilities or
    persist it for faster restarts (see fork-merge-plan deferred items).
    """

    device_type: Model
    inverter_address: int = 0x32
    meter_addresses: list[int] = field(default_factory=list)
    lv_battery_addresses: list[int] = field(default_factory=list)
    # Each entry is (bcu_offset, num_modules) where the BCU device address is 0x70 + bcu_offset.
    bcu_stacks: list[tuple[int, int]] = field(default_factory=list)

    def __init__(
        self,
        device_type: Model,
        inverter_address: int | None = None,
        meter_addresses: list[int] | None = None,
        lv_battery_addresses: list[int] | None = None,
        bcu_stacks: list[tuple[int, int]] | None = None,
        **legacy_kwargs: Any,
    ) -> None:
        new_values: dict[str, Any] = {
            "inverter_address": inverter_address,
            "meter_addresses": meter_addresses,
            "lv_battery_addresses": lv_battery_addresses,
            "bcu_stacks": bcu_stacks,
        }
        for old, new in _CAPABILITIES_LEGACY_ALIASES.items():
            if old in legacy_kwargs:
                if new_values[new] is not None:
                    raise TypeError(f"pass either {old}= or {new}=, not both")
                warnings.warn(
                    f"PlantCapabilities.{old} is deprecated; use {new}",
                    DeprecationWarning,
                    stacklevel=2,
                )
                new_values[new] = legacy_kwargs.pop(old)
        if legacy_kwargs:
            raise TypeError(f"unexpected keyword arguments: {sorted(legacy_kwargs)}")
        self.device_type = device_type
        self.inverter_address = new_values["inverter_address"] if new_values["inverter_address"] is not None else 0x32
        self.meter_addresses = new_values["meter_addresses"] if new_values["meter_addresses"] is not None else []
        self.lv_battery_addresses = (
            new_values["lv_battery_addresses"] if new_values["lv_battery_addresses"] is not None else []
        )
        self.bcu_stacks = new_values["bcu_stacks"] if new_values["bcu_stacks"] is not None else []

    @property
    def inverter_slave(self) -> int:
        """Deprecated alias for `inverter_address`."""
        warnings.warn(
            "PlantCapabilities.inverter_slave is deprecated; use inverter_address",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.inverter_address

    @inverter_slave.setter
    def inverter_slave(self, value: int) -> None:
        warnings.warn(
            "PlantCapabilities.inverter_slave is deprecated; use inverter_address",
            DeprecationWarning,
            stacklevel=2,
        )
        self.inverter_address = value

    @property
    def meter_slaves(self) -> list[int]:
        """Deprecated alias for `meter_addresses`."""
        warnings.warn(
            "PlantCapabilities.meter_slaves is deprecated; use meter_addresses",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.meter_addresses

    @meter_slaves.setter
    def meter_slaves(self, value: list[int]) -> None:
        warnings.warn(
            "PlantCapabilities.meter_slaves is deprecated; use meter_addresses",
            DeprecationWarning,
            stacklevel=2,
        )
        self.meter_addresses = value

    @property
    def lv_battery_slaves(self) -> list[int]:
        """Deprecated alias for `lv_battery_addresses`."""
        warnings.warn(
            "PlantCapabilities.lv_battery_slaves is deprecated; use lv_battery_addresses",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.lv_battery_addresses

    @lv_battery_slaves.setter
    def lv_battery_slaves(self, value: list[int]) -> None:
        warnings.warn(
            "PlantCapabilities.lv_battery_slaves is deprecated; use lv_battery_addresses",
            DeprecationWarning,
            stacklevel=2,
        )
        self.lv_battery_addresses = value

    @property
    def bcu_slaves(self) -> list[tuple[int, int]]:
        """Deprecated alias for `bcu_stacks`."""
        warnings.warn(
            "PlantCapabilities.bcu_slaves is deprecated; use bcu_stacks",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.bcu_stacks

    @bcu_slaves.setter
    def bcu_slaves(self, value: list[tuple[int, int]]) -> None:
        warnings.warn(
            "PlantCapabilities.bcu_slaves is deprecated; use bcu_stacks",
            DeprecationWarning,
            stacklevel=2,
        )
        self.bcu_stacks = value

    @property
    def is_hv(self) -> bool:
        """Return True if this system uses HV battery stacks (BCU/BMU) rather than LV packs."""
        return self.device_type in _HV_MODELS

    SCHEMA_VERSION = 1

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict for caller-managed persistence.

        Round-trips through from_dict(). Addresses render as `0x..` strings to
        match the form used in logs, exceptions, and code. The schema_version
        field gives future-us an escape hatch for format changes.
        """
        return {
            "schema_version": self.SCHEMA_VERSION,
            "device_type": self.device_type.name,
            "inverter_address": f"0x{self.inverter_address:02x}",
            "meter_addresses": [f"0x{a:02x}" for a in self.meter_addresses],
            "lv_battery_addresses": [f"0x{a:02x}" for a in self.lv_battery_addresses],
            "bcu_stacks": [[offset, modules] for offset, modules in self.bcu_stacks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlantCapabilities":
        """Reconstruct from a to_dict() payload.

        Accepts two on-disk shapes:

        - **v2.0.0 (legacy, no `schema_version`)**: `device_type` as the enum
          value (e.g. `"2"`), addresses as raw integers, no `schema_version`
          key. Persisted by the v2.0.0 `to_dict()`.
        - **v2.0.1+ (versioned)**: `schema_version` present and equal to
          `SCHEMA_VERSION`, `device_type` as enum name (e.g. `"HYBRID_GEN1"`),
          addresses as `"0x..."` hex strings.

        A `schema_version` that's present but doesn't match `SCHEMA_VERSION`
        raises `ValueError` — callers can catch and re-run detect() without
        prior. Pre-rename `*_slave(s)` key aliases are normalised silently so
        state persisted under the older conventions still loads cleanly.
        """
        normalised: dict[str, Any] = dict(data)
        for old, new in _CAPABILITIES_LEGACY_ALIASES.items():
            if old in normalised and new not in normalised:
                normalised[new] = normalised.pop(old)
        version = normalised.get("schema_version")
        if version is not None and version != cls.SCHEMA_VERSION:
            raise ValueError(f"unsupported PlantCapabilities schema_version {version!r}; expected {cls.SCHEMA_VERSION}")

        def _addr(v: Any) -> int:
            # Accept either hex strings (the v2.0.1+ canonical form) or raw ints
            # (the v2.0.0 legacy form, or hand-edited payloads).
            return int(v, 0) if isinstance(v, str) else int(v)

        def _device_type(v: Any) -> Model:
            # v2.0.1+ persists the enum name (Model["HYBRID_GEN1"]); v2.0.0
            # persisted the enum value (Model("2")). Try the name lookup first
            # — it's what every payload emitted by 2.0.1's to_dict() uses — and
            # fall back to the value lookup so v2.0.0 payloads keep working.
            # `str(v)` on the fallback handles unquoted ints from sloppy JSON
            # tooling (`device_type: 2` instead of `"2"`).
            if isinstance(v, Model):
                return v
            try:
                return Model[v]
            except KeyError, TypeError:
                return Model(str(v))

        # `.get(k) or []` (not `.get(k, [])`) so an explicit `null` in JSON for
        # any of the optional list fields safely degrades to empty rather than
        # raising TypeError on iteration.
        return cls(
            device_type=_device_type(normalised["device_type"]),
            inverter_address=_addr(normalised["inverter_address"]),
            meter_addresses=[_addr(a) for a in (normalised.get("meter_addresses") or [])],
            lv_battery_addresses=[_addr(a) for a in (normalised.get("lv_battery_addresses") or [])],
            # Coerce bcu_stacks entries — hand-edited JSON / differently-serialised
            # payloads can put strings here, which would TypeError downstream
            # (`0x70 + offset` in detect()). Fail loud at parse time instead.
            bcu_stacks=[(int(offset), int(modules)) for offset, modules in (normalised.get("bcu_stacks") or [])],
        )

    def __repr__(self) -> str:
        meters = ", ".join(f"0x{a:02x}" for a in self.meter_addresses)
        batts = ", ".join(f"0x{a:02x}" for a in self.lv_battery_addresses)
        bcus = ", ".join(f"({o}, {n})" for o, n in self.bcu_stacks)
        return (
            f"PlantCapabilities("
            f"device_type=Model.{self.device_type.name}, "
            f"inverter_address=0x{self.inverter_address:02x}, "
            f"meter_addresses=[{meters}], "
            f"lv_battery_addresses=[{batts}], "
            f"bcu_stacks=[{bcus}])"
        )

    @property
    def is_three_phase(self) -> bool:
        """Return True if this system uses three-phase registers (HR/IR 1000-range)."""
        return self.device_type in _THREE_PHASE_MODELS

    @property
    def has_extended_slots(self) -> bool:
        """Return True if this system supports the extended 10-slot map (HR 240–299)."""
        return self.device_type in _EXTENDED_SLOT_MODELS

    @property
    def is_ems(self) -> bool:
        """Return True if this system is an EMS plant controller (HR/IR 2040-range)."""
        return self.device_type in (Model.EMS, Model.EMS_COMMERCIAL)

    @property
    def is_gateway(self) -> bool:
        """Return True if this system is a Gateway (IR 1600-range)."""
        return self.device_type == Model.GATEWAY


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

    def _getter_for_device_address(self, device_address: int) -> type[RegisterGetter] | None:
        """Return the RegisterGetter class appropriate for a given device address."""
        if device_address == 0x32:
            return SinglePhaseInverterRegisterGetter
        if 0x01 <= device_address <= 0x08:
            return MeterRegisterGetter
        if 0x33 <= device_address <= 0x37:
            return BatteryRegisterGetter
        if 0x70 <= device_address <= 0x8F:
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

        if pdu.device_address in (0x11, 0x00):
            # rewrite cloud and mobile app responses to "normal" inverter address
            device_address = 0x32
        else:
            device_address = pdu.device_address

        if device_address not in self.register_caches:
            _logger.debug(f"First time encountering device address 0x{device_address:02x}")
            self.register_caches[device_address] = RegisterCache()

        self.inverter_serial_number = pdu.inverter_serial_number
        self.data_adapter_serial_number = pdu.data_adapter_serial_number

        if isinstance(pdu, ReadHoldingRegistersResponse):
            incoming = {HR(k): v for k, v in pdu.to_dict().items()}
            self._commit_bank(device_address, incoming)
        elif isinstance(pdu, ReadInputRegistersResponse):
            if pdu.is_suspicious():
                # Pattern A dongle-side substitution from #78 — known fingerprint of 16 fixed
                # constants. is_suspicious() logs at debug when it fires.
                return
            incoming = {IR(k): v for k, v in pdu.to_dict().items()}  # type: ignore[misc]
            self._commit_bank(device_address, incoming)
        elif isinstance(pdu, WriteHoldingRegisterResponse):
            if pdu.register == 0:
                _logger.warning(f"Ignoring, likely corrupt: {pdu}")
            else:
                self.register_caches[device_address].update({HR(pdu.register): pdu.value})

    def _commit_bank(self, device_address: int, incoming: dict) -> None:
        """Validate incoming register bank against bounds and commit if clean."""
        getter_cls = self._getter_for_device_address(device_address)
        if getter_cls is not None:
            if not getter_cls.is_coherent(incoming, self.register_caches[device_address]):
                # Common on a shared bus: other clients (cloud, mobile app, GivTCP) poll
                # empty slots beyond the user's actual hardware, and we see the responses
                # go by. The discard is correct; logging at WARNING was actionable noise.
                _logger.debug("Discarding register bank with invalid serial for device 0x%02x", device_address)
                return
            violations = getter_cls.validate_bank(incoming, self.register_caches[device_address])
            if violations:
                _logger.debug(
                    "Bounds violations in register bank for device 0x%02x: %s",
                    device_address,
                    violations,
                )
                # TODO(enforcement): add `return` here to discard the entire bank on any violation.
                # When that happens, also raise this back to WARNING — at that point it has
                # user-visible consequences (a poll cycle's data is dropped).
        self.register_caches[device_address].update(incoming)

    @property
    def inverter(self) -> SinglePhaseInverter | ThreePhaseInverter:
        """Return the inverter model, dispatching on device type when capabilities are available."""
        if self.capabilities:
            return select_inverter(
                self.capabilities.device_type, self.register_caches[self.capabilities.inverter_address]
            )
        return SinglePhaseInverter.from_register_cache(self.register_caches[0x32])

    @property
    def number_batteries(self) -> int:
        """Determine the number of batteries connected to the system based on whether the register data is valid."""
        if self.capabilities:
            return len(self.capabilities.lv_battery_addresses)
        count = 0
        for i in range(6):
            try:
                battery = Battery.from_register_cache(self.register_caches[i + 0x32])
            except (KeyError, ValueError):  # fmt: skip  # TODO: drop parens when 3.13 support ends (PEP 758)
                # KeyError: no cache for that device yet. ValueError: an enum-typed
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
                for addr in self.capabilities.lv_battery_addresses
                if addr in self.register_caches
            ]
        return [Battery.from_register_cache(self.register_caches[i + 0x32]) for i in range(self.number_batteries)]

    @property
    def hv_stacks(self) -> list[HvStack]:
        """Return HV battery stacks (BCU + BMUs) for HV systems; empty list for LV systems."""
        if not self.capabilities or not self.capabilities.bcu_stacks:
            return []
        stacks = []
        for offset, num_modules in self.capabilities.bcu_stacks:
            device_addr = 0x70 + offset
            cache = self.register_caches.get(device_addr, RegisterCache())
            bcu = Bcu.from_register_cache(cache)
            bmus = [Bmu.from_register_cache(cache, i) for i in range(num_modules)]
            stacks.append(HvStack(device_address=device_addr, bcu=bcu, bmus=bmus))
        return stacks

    @property
    def meters(self) -> dict[int, Meter]:
        """Return Meter models keyed by device address."""
        if not self.capabilities or not self.capabilities.meter_addresses:
            return {}
        return {
            addr: Meter.from_register_cache(self.register_caches[addr])
            for addr in self.capabilities.meter_addresses
            if addr in self.register_caches
        }

    @property
    def ems(self) -> Ems | None:
        """Return Ems model for EMS/EMS_COMMERCIAL device types; None otherwise."""
        if not self.capabilities or self.capabilities.device_type not in (Model.EMS, Model.EMS_COMMERCIAL):
            return None
        cache = self.register_caches.get(self.capabilities.inverter_address, RegisterCache())
        return Ems.from_register_cache(cache)

    @property
    def inverters(self) -> list[UnifiedInverter]:
        """Return one :class:`Inverter` facade per inverter in this plant.

        Phase 1 of the Plant refactor — the unified surface that makes
        EMS-managed (blinded) inverters visible without breaking the
        existing :attr:`inverter` / :attr:`ems` accessors.

        For an EMS plant: yields one :class:`Inverter` per non-empty
        managed-inverter slot in the EMS's IR(2040+) rollup
        (``data_source="ems_rollup"``). Direct register-cache inverters
        on the same plant are not yet exposed here — that happens in
        phase 2 once Multi-Client orchestration lands and free-standing
        inverters can be reconciled with the EMS rollup by serial.

        For a non-EMS plant: yields a single :class:`Inverter` wrapping
        the existing :attr:`inverter` (``data_source="direct"``). The
        legacy :attr:`inverter` (singular) accessor remains for
        back-compat and continues to return the directly-decoded
        :class:`SinglePhaseInverter` / :class:`ThreePhaseInverter`.

        See ``docs/v2.1-roadmap.md`` for the wider refactor sketch.
        """
        if self.ems is not None:
            return [UnifiedInverter.from_summary(s) for s in self.ems.managed_inverters]
        return [UnifiedInverter.from_direct(self.inverter)]

    @property
    def gateway(self) -> GatewayV1 | GatewayV2 | None:
        """Return GatewayV1 or GatewayV2 model for GATEWAY device type; None otherwise."""
        if not self.capabilities or self.capabilities.device_type != Model.GATEWAY:
            return None
        cache = self.register_caches.get(self.capabilities.inverter_address, RegisterCache())
        return select_gateway(cache)
