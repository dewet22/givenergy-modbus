import logging
import warnings
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from givenergy_modbus.model import GivEnergyBaseModel
from givenergy_modbus.model.battery import Battery, BatteryRegisterGetter
from givenergy_modbus.model.devices import Inverter as UnifiedInverter
from givenergy_modbus.model.ems import Ems
from givenergy_modbus.model.gateway import GatewayV1, GatewayV2, select_gateway
from givenergy_modbus.model.hv_bcu import Bcu, BcuRegisterGetter, Bmu, HvStack
from givenergy_modbus.model.inverter import (
    AC_COUPLED_MODELS,
    Model,
    SinglePhaseInverter,
    SinglePhaseInverterRegisterGetter,
    inverter_address_for,
)
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

# Models with registers in the 1000-range (HR 1000–1124, IR 1000–1413), i.e. genuinely
# three-phase units that expose the per-phase bank. NB: the residential ALL_IN_ONE (DTC
# family "8", e.g. 0x8001) is HV but SINGLE-phase — it has no 1000-range bank (it error-
# responds to those reads) and its data lives in the single-phase IR(0)/IR(180) banks. It
# is intentionally excluded here (and from the decode-layout set in inverter_threephase.py)
# while remaining in _HV_MODELS / _EXTENDED_SLOT_MODELS. Confirmed against real AIO hardware
# (HR(0)=0x8001, owner-confirmed 1-phase) and the GE spec sheet (3.6 kW/16 A). See #105.
_THREE_PHASE_MODELS: frozenset[Model] = frozenset(
    {
        Model.HYBRID_3PH,
        Model.AC_3PH,
        Model.AIO_COMMERCIAL,
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

# Models that expose the HR(300–359) AC-output config block: export_priority (HR311),
# battery_*_limit_ac (HR313/314), enable_eps (HR317), pause mode/slot (HR318–320).
# Present on AC-coupled inverters AND the All-in-One (which has an AC output stage with
# the same export/EPS/AC-limit controls). DC-coupled/hybrid inverters lack the block and
# time out when polled for it (#162). Evidence: Model.AC fixtures answer HR(300,60); the
# AIO fixture answers HR(300,21) and a live AIO populates export_priority/enable_eps/
# battery_*_limit_ac (#105). NB this is deliberately a separate set from AC_COUPLED_MODELS
# (the is_ac_coupled predicate, which hass uses to scope AC controls) — whether the AIO is
# "AC-coupled" for that purpose is a separate consumer decision; here we only care which
# models carry this register block.
_AC_CONFIG_BLOCK_MODELS: frozenset[Model] = frozenset(
    {
        Model.AC,
        Model.AC_3PH,
        Model.ALL_IN_ONE,
    }
)

# Models with a *readable* Smart Load slot block at HR(540-599). Deliberately empty:
# the block was added speculatively from the GivEnergy app's Direct Control catalogue
# (which only proves the writable surface, not that a live read answers), and no model
# has yet been confirmed to return data on real hardware. HYBRID_GEN1 is confirmed to
# *time out* on the read (#179, two independent reports). device_type here is the
# firmware-resolved variant (resolve_model), so members may be gen-specific once any
# model is confirmed. Until then the bulk read is gated off everywhere; the
# smart_load_slot_* decode Defs and set_smart_load_slot_* write helpers are unaffected.
_SMART_LOAD_CAPABLE_MODELS: frozenset[Model] = frozenset()


_CAPABILITIES_LEGACY_ALIASES = {
    "inverter_slave": "inverter_address",
    "meter_slaves": "meter_addresses",
    "lv_battery_slaves": "lv_battery_addresses",
    "bcu_slaves": "bcu_stacks",
}


def _map_legacy_aliases(kwargs: dict[str, Any], *, stacklevel: int) -> None:
    """Rename legacy ``*_slave(s)`` keys to canonical names, warn, and enforce mutual exclusivity.

    Mutates ``kwargs`` in place. Shared between PlantCapabilities.__init__
    (stacklevel=3, the caller's frame) and the model_validate validator
    (stacklevel=2, best-effort — Pydantic internals limit what's reachable).
    """
    for old, new in _CAPABILITIES_LEGACY_ALIASES.items():
        if old not in kwargs:
            continue
        if new in kwargs:
            raise TypeError(f"pass either {old}= or {new}=, not both")
        warnings.warn(
            f"PlantCapabilities.{old} is deprecated; use {new}",
            DeprecationWarning,
            stacklevel=stacklevel,
        )
        kwargs[new] = kwargs.pop(old)


def _coerce_model(value: Any) -> Model | None:
    """Best-effort coerce a device_type input to a Model, or None if it can't.

    Accepts a Model instance, the enum name (``"HYBRID_GEN1"``), or the enum
    value (``"2"`` / ``2``). Returns None on failure so the caller can defer to
    Pydantic's own field validation for the canonical error.
    """
    if isinstance(value, Model):
        return value
    try:
        return Model[value]
    except (KeyError, TypeError):
        pass
    try:
        return Model(str(value))
    except ValueError:
        return None


def _derive_inverter_address(mapping: dict[str, Any]) -> None:
    """Fill in ``inverter_address`` from ``device_type`` when not pinned explicitly.

    Mutates ``mapping`` in place. 0x11 for most models, 0x31 for AC/HYBRID_GEN1
    (issue #119). Payloads that already carry an explicit ``inverter_address``
    (e.g. persisted state via ``from_dict``) are left untouched — so a stored
    pre-#119 ``0x32`` surfaces as a PlantTopologyMismatch on the next detect()
    and self-heals rather than being silently rewritten.
    """
    if mapping.get("inverter_address") is not None:
        return
    model = _coerce_model(mapping.get("device_type"))
    if model is not None:
        mapping["inverter_address"] = inverter_address_for(model)


class PlantCapabilities(BaseModel):
    """Describes the hardware topology discovered by Client.detect().

    Returned by Client.detect(); callers assign it to plant.capabilities or
    persist it for faster restarts (see fork-merge-plan deferred items).

    Legacy ``*_slave(s)`` keyword aliases are mapped to the canonical names
    in ``__init__`` (for ``PlantCapabilities(...)`` callers) and again in the
    ``_accept_legacy_aliases`` model_validator (for ``model_validate({...})``
    callers). Both paths emit a DeprecationWarning.
    """

    # `extra="forbid"` preserves the historic contract that unknown kwargs
    # raise TypeError. The pre-Pydantic __init__ enforced this manually.
    model_config = ConfigDict(extra="forbid")

    device_type: Model
    inverter_address: int = 0x32
    meter_addresses: list[int] = Field(default_factory=list)
    lv_battery_addresses: list[int] = Field(default_factory=list)
    # Each entry is (bcu_offset, num_modules) where the BCU device address is 0x70 + bcu_offset.
    bcu_stacks: list[tuple[int, int]] = Field(default_factory=list)

    def __init__(
        self,
        device_type: Model | None = None,
        inverter_address: int | None = None,
        meter_addresses: list[int] | None = None,
        lv_battery_addresses: list[int] | None = None,
        bcu_stacks: list[tuple[int, int]] | None = None,
        **kwargs: Any,
    ) -> None:
        # Custom __init__ for two reasons:
        # 1. Preserves the historic positional-argument shape that the
        #    @dataclass form supported (PlantCapabilities(Model.HYBRID, 0x32, ...)).
        # 2. Lets us emit the legacy-alias DeprecationWarning at stacklevel=2
        #    pointing at the user's call site — a `model_validator(mode='before')`
        #    sits behind Pydantic internals and can't reach the caller cleanly.
        # Only pass through positional-derived values that were actually supplied
        # so we don't override kwargs the caller may have provided as keywords.
        if device_type is not None:
            kwargs["device_type"] = device_type
        if inverter_address is not None:
            kwargs["inverter_address"] = inverter_address
        if meter_addresses is not None:
            kwargs["meter_addresses"] = meter_addresses
        if lv_battery_addresses is not None:
            kwargs["lv_battery_addresses"] = lv_battery_addresses
        if bcu_stacks is not None:
            kwargs["bcu_stacks"] = bcu_stacks
        _map_legacy_aliases(kwargs, stacklevel=3)
        super().__init__(**kwargs)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_aliases(cls, data: Any) -> Any:
        """Mirror the __init__ alias handling for the ``model_validate`` path.

        ``PlantCapabilities.model_validate({'inverter_slave': 0x33})`` bypasses
        ``__init__``, so we need a validator to catch legacy keys arriving via
        that route. Stacklevel from inside a validator can't reliably reach the
        user (Pydantic internals sit between), but the warning still fires under
        ``pytest.warns`` and ``warnings.catch_warnings`` filtering by category.
        """
        if not isinstance(data, dict):
            return data
        normalised = dict(data)
        _map_legacy_aliases(normalised, stacklevel=2)
        _derive_inverter_address(normalised)
        return normalised

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

    SCHEMA_VERSION: ClassVar[int] = 1

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
            except (KeyError, TypeError):
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
    def is_ac_coupled(self) -> bool:
        """Return True if this system is AC-coupled (no integrated DC battery)."""
        return self.device_type in AC_COUPLED_MODELS

    @property
    def has_extended_slots(self) -> bool:
        """Return True if this system supports the extended 10-slot map (HR 240–299)."""
        return self.device_type in _EXTENDED_SLOT_MODELS

    @property
    def has_ac_config_block(self) -> bool:
        """Return True if this system exposes the HR(300–359) AC-output config block.

        Covers export priority, EPS enable, AC charge/discharge limits and pause mode —
        present on AC-coupled inverters and the All-in-One, absent (times out) on
        DC-coupled/hybrid models. See `_AC_CONFIG_BLOCK_MODELS` (#162).
        """
        return self.device_type in _AC_CONFIG_BLOCK_MODELS

    @property
    def has_smart_load_block(self) -> bool:
        """Return True if this system exposes a readable HR(540–599) Smart Load block.

        Currently False for every model: no inverter has been confirmed to answer the
        read on real hardware, and HYBRID_GEN1 is confirmed to time out on it. See
        `_SMART_LOAD_CAPABLE_MODELS` (#179).
        """
        return self.device_type in _SMART_LOAD_CAPABLE_MODELS

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
    # Ingestion timestamps per committed register block, keyed by
    # (device_address, register_type_name, base_register) → last successful commit time (#65).
    # Maintained continuously by the network consumer's update() calls, so it captures both
    # solicited responses and the dongle's unsolicited fan-out. Consumers (and refresh()'s
    # skip-if-fresh path, #196) use block_age() to reason about freshness. Excluded from
    # model_dump(): it's ephemeral runtime bookkeeping, not part of the plant's dumpable state.
    register_block_updated_at: dict[tuple[int, str, int], datetime] = Field(default_factory=dict, exclude=True)

    def model_post_init(self, __context: Any) -> None:
        """Ensure a default register cache is always present."""
        if not self.register_caches:
            self.register_caches = {0x32: RegisterCache()}

    def _getter_for_device_address(self, device_address: int) -> type[RegisterGetter] | None:
        """Return the RegisterGetter class appropriate for a given device address.

        With capabilities the inverter lives at its model-specific address
        (0x11, or 0x31 for AC/HYBRID_GEN1 — issue #119) and 0x32 is LV battery
        pack #1. Without capabilities we fall back to the legacy mapping where
        the inverter was cached at 0x32, and also treat 0x11/0x31 as inverter so
        replay/debug tooling (which feeds PDUs to a bare Plant) keeps validating
        inverter banks that now arrive at their true wire address.
        """
        if self.capabilities is not None:
            if device_address == self.capabilities.inverter_address:
                return SinglePhaseInverterRegisterGetter
            if 0x32 <= device_address <= 0x37:
                return BatteryRegisterGetter
        else:
            if device_address in (0x11, 0x31, 0x32):
                return SinglePhaseInverterRegisterGetter
            if 0x33 <= device_address <= 0x37:
                return BatteryRegisterGetter
        if 0x01 <= device_address <= 0x08:
            return MeterRegisterGetter
        if 0x70 <= device_address <= 0x8F:
            return BcuRegisterGetter
        return None

    def update(self, pdu: ClientIncomingMessage, *, received_at: datetime | None = None):
        """Update the Plant state from a PDU message.

        ``received_at`` overrides the ingestion timestamp recorded for a committed
        register block (see ``register_block_updated_at`` / #65); it defaults to the
        current UTC time and is provided mainly for deterministic testing and replay.
        """
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

        # Store responses under their true wire device address. The old 0x11/0x00 → 0x32
        # fold was a courtesy to GivEnergy's cloud, not an inverter requirement: querying
        # 0x11 was relayed upstream by the dongle, and sub-5-minute polling there disturbed
        # their 5-minute dashboards — 0x32 was the side-door that left the cloud product
        # alone (0x00 was app traffic folded in on an assumption). Both rationales are now
        # moot (cloud is premium-only). The fold masked that 0x11 is the inverter's
        # canonical address and 0x32 is LV battery pack #1 (issue #119); detect() now
        # resolves the inverter address per model and reads/caches consistently at it.
        device_address = pdu.device_address

        if device_address not in self.register_caches:
            _logger.debug(f"First time encountering device address 0x{device_address:02x}")
            self.register_caches[device_address] = RegisterCache()

        self.inverter_serial_number = pdu.inverter_serial_number
        self.data_adapter_serial_number = pdu.data_adapter_serial_number

        if isinstance(pdu, ReadHoldingRegistersResponse):
            incoming = {HR(k): v for k, v in pdu.to_dict().items()}
            if self._commit_bank(device_address, incoming):
                self._stamp_block(device_address, "HR", pdu.base_register, received_at)
        elif isinstance(pdu, ReadInputRegistersResponse):
            if pdu.is_suspicious():
                # Pattern A dongle-side substitution from #78 — known fingerprint of 16 fixed
                # constants. is_suspicious() logs at debug when it fires.
                return
            incoming = {IR(k): v for k, v in pdu.to_dict().items()}  # type: ignore[misc]
            if self._commit_bank(device_address, incoming):
                self._stamp_block(device_address, "IR", pdu.base_register, received_at)
        elif isinstance(pdu, WriteHoldingRegisterResponse):
            if pdu.register == 0:
                _logger.warning(f"Ignoring, likely corrupt: {pdu}")
            else:
                # Writes target the inverter and the echo comes back on the write address
                # (0x11), but the model reads caps.inverter_address (0x31 for AC/HYBRID_GEN1,
                # 0x11 otherwise). 0x11 and 0x31 are the same device (a facade), so route the
                # echo to where reads land — otherwise plant.inverter won't reflect the write
                # until the next load_config(), and refresh() (IR-only) never will. The cache
                # may not exist yet if the write precedes the first read at inverter_address.
                target = self.capabilities.inverter_address if self.capabilities is not None else device_address
                self.register_caches.setdefault(target, RegisterCache()).update({HR(pdu.register): pdu.value})

    def _commit_bank(self, device_address: int, incoming: dict) -> bool:
        """Validate incoming register bank against bounds and commit if clean.

        Returns True if the bank was committed to the cache, False if it was discarded —
        so the caller only records an ingestion timestamp (#65) for banks that actually
        landed.
        """
        getter_cls = self._getter_for_device_address(device_address)
        if getter_cls is not None:
            if not getter_cls.is_coherent(incoming, self.register_caches[device_address]):
                # Common on a shared bus: other clients (cloud, mobile app, GivTCP) poll
                # empty slots beyond the user's actual hardware, and we see the responses
                # go by. The discard is correct; logging at WARNING was actionable noise.
                _logger.debug("Discarding register bank with invalid serial for device 0x%02x", device_address)
                return False
            violations = getter_cls.validate_bank(incoming, self.register_caches[device_address])
            if violations:
                _logger.debug(
                    "Bounds violations in register bank for device 0x%02x: %s",
                    device_address,
                    violations,
                )
                # TODO(enforcement): add `return False` here to discard the entire bank on any
                # violation. When that happens, also raise this back to WARNING — at that point
                # it has user-visible consequences (a poll cycle's data is dropped).
        self.register_caches[device_address].update(incoming)
        return True

    def _stamp_block(
        self, device_address: int, reg_type: str, base_register: int, received_at: datetime | None
    ) -> None:
        """Record the ingestion time of a committed register block (#65)."""
        self.register_block_updated_at[(device_address, reg_type, base_register)] = received_at or datetime.now(UTC)

    def block_age(
        self, device_address: int, reg_type: str, base_register: int, *, now: datetime | None = None
    ) -> float | None:
        """Seconds since a register block was last committed, or None if never seen.

        ``reg_type`` is ``"HR"`` or ``"IR"``. Used to reason about freshness — e.g.
        refresh()'s skip-if-fresh path for the fan-out IR(0,60) block (#196), and the
        staleness signal that pairs with all-zero-bank rejection (#206).
        """
        ts = self.register_block_updated_at.get((device_address, reg_type, base_register))
        if ts is None:
            return None
        return ((now or datetime.now(UTC)) - ts).total_seconds()

    @property
    def inverter(self) -> SinglePhaseInverter | ThreePhaseInverter:
        """Return the inverter model, dispatching on device type when capabilities are available.

        Tolerates the inverter-address cache not yet existing — for AC/HYBRID_GEN1 the
        address is 0x31, which detect() doesn't populate (it only reads identity at 0x11),
        so this would otherwise KeyError between detect() and the first poll. Returns an
        empty-cache model in that window, matching the .ems / .gateway accessors. (#119)
        """
        if self.capabilities:
            cache = self.register_caches.get(self.capabilities.inverter_address, RegisterCache())
            return select_inverter(self.capabilities.device_type, cache)
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
            except (KeyError, ValueError):
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
