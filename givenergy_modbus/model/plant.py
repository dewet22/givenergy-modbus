import logging
import warnings
from datetime import UTC, datetime
from typing import Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from givenergy_modbus.model import GivEnergyBaseModel
from givenergy_modbus.model.aio_battery import AioBatteryModule
from givenergy_modbus.model.battery import Battery, BatteryRegisterGetter
from givenergy_modbus.model.battery_splice import (
    BANK_BASE,
    IMMUTABLE_SCALAR,
    IMMUTABLE_SERIAL,
    SCALAR_IMMUT_HEAL_POLLS,
    SPLICE_REJECT_HEAL_POLLS,
    STALE_BYPASS_SECONDS,
    THRESHOLD_BY_CLASS,
    classify_transition,
    heal_eligible,
    is_corruption_cohort,
)
from givenergy_modbus.model.devices import DeviceType, PlantDevice
from givenergy_modbus.model.devices import Inverter as UnifiedInverter
from givenergy_modbus.model.ems import Ems
from givenergy_modbus.model.gateway import GatewayV1, GatewayV2, select_gateway
from givenergy_modbus.model.hv_bcu import Bcu, BcuRegisterGetter, Bmu, BmuRegisterGetter, HvStack
from givenergy_modbus.model.inverter import (
    AC_COUPLED_MODELS,
    Model,
    SinglePhaseInverter,
    SinglePhaseInverterRegisterGetter,
    inverter_address_for,
    resolve_model,
)
from givenergy_modbus.model.inverter_threephase import ThreePhaseInverter, select_inverter
from givenergy_modbus.model.lv_bcu import LvBcu, LvBcuRegisterGetter
from givenergy_modbus.model.meter import Meter, MeterRegisterGetter
from givenergy_modbus.model.register import HR, IR, Converter, Register, RegisterGetter, is_valid_serial
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

# Models with a readable HV cabinet topology block at HR(499-510). Deliberately empty:
# no model has been confirmed to return data on real hardware. Gate off until a capture
# confirms the block responds; the hv_* decode Defs are unaffected.
_HV_CABINET_MODELS: frozenset[Model] = frozenset()

# Models with a readable peak-shaving block at HR(20000-20051). Deliberately empty:
# no model has been confirmed to return data on real hardware. Gate off until a capture
# confirms the block responds; the peak_shaving_* decode Defs are unaffected.
_PEAK_SHAVING_MODELS: frozenset[Model] = frozenset()


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

    Mutates ``mapping`` in place. 0x11 for all models since the 0x31 read-alias
    retirement (#189; previously 0x31 for AC/HYBRID_GEN1 — issue #119). Payloads
    that already carry an explicit ``inverter_address`` (e.g. persisted state via
    ``from_dict``) are left untouched — a stored ``0x31`` keeps working against
    the hardware facade and self-heals on the next detect(), while a stored
    pre-#119 ``0x32`` surfaces as a PlantTopologyMismatch rather than being
    silently rewritten.
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
    # AIO (All-in-One) per-module battery device addresses (0x50-0x53). Separate-address
    # layout, distinct from the bcu_stacks stride model — see model/aio_battery.py (#192).
    aio_battery_module_addresses: list[int] = Field(default_factory=list)
    # HV BMU per-module device addresses (0x50+), populated by detect for non-AIO HV stacks.
    # Each module answers at its own IR(60-119) cache (same separate-address layout as AIO);
    # installer-confirmed, not yet wire-confirmed — see model/hv_bcu.py (#265).
    hv_bmu_addresses: list[int] = Field(default_factory=list)
    # LV BCU page address (observed only at 0x31 — see model/lv_bcu.py). None when the
    # block read all-zero at detect time (firmware-gated, #241).
    lv_bcu_address: int | None = None

    def __init__(
        self,
        device_type: Model | None = None,
        inverter_address: int | None = None,
        meter_addresses: list[int] | None = None,
        lv_battery_addresses: list[int] | None = None,
        bcu_stacks: list[tuple[int, int]] | None = None,
        aio_battery_module_addresses: list[int] | None = None,
        lv_bcu_address: int | None = None,
        hv_bmu_addresses: list[int] | None = None,
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
        if aio_battery_module_addresses is not None:
            kwargs["aio_battery_module_addresses"] = aio_battery_module_addresses
        if lv_bcu_address is not None:
            kwargs["lv_bcu_address"] = lv_bcu_address
        if hv_bmu_addresses is not None:
            kwargs["hv_bmu_addresses"] = hv_bmu_addresses
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
            "aio_battery_module_addresses": [f"0x{a:02x}" for a in self.aio_battery_module_addresses],
            "hv_bmu_addresses": [f"0x{a:02x}" for a in self.hv_bmu_addresses],
            "lv_bcu_address": f"0x{self.lv_bcu_address:02x}" if self.lv_bcu_address is not None else None,
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
            aio_battery_module_addresses=[_addr(a) for a in (normalised.get("aio_battery_module_addresses") or [])],
            hv_bmu_addresses=[_addr(a) for a in (normalised.get("hv_bmu_addresses") or [])],
            lv_bcu_address=(
                _addr(normalised["lv_bcu_address"]) if normalised.get("lv_bcu_address") is not None else None
            ),
        )

    def __repr__(self) -> str:
        meters = ", ".join(f"0x{a:02x}" for a in self.meter_addresses)
        batts = ", ".join(f"0x{a:02x}" for a in self.lv_battery_addresses)
        bcus = ", ".join(f"({o}, {n})" for o, n in self.bcu_stacks)
        aio_mods = ", ".join(f"0x{a:02x}" for a in self.aio_battery_module_addresses)
        hv_bmus = ", ".join(f"0x{a:02x}" for a in self.hv_bmu_addresses)
        lv_bcu = f"0x{self.lv_bcu_address:02x}" if self.lv_bcu_address is not None else "None"
        return (
            f"PlantCapabilities("
            f"device_type=Model.{self.device_type.name}, "
            f"inverter_address=0x{self.inverter_address:02x}, "
            f"meter_addresses=[{meters}], "
            f"lv_battery_addresses=[{batts}], "
            f"bcu_stacks=[{bcus}], "
            f"aio_battery_module_addresses=[{aio_mods}], "
            f"hv_bmu_addresses=[{hv_bmus}], "
            f"lv_bcu_address={lv_bcu})"
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
    def has_hv_cabinet_block(self) -> bool:
        """Return True if this system exposes a readable HR(499–510) HV cabinet topology block.

        Currently False for every model: no inverter has been confirmed to answer the read on
        real hardware. See `_HV_CABINET_MODELS` (#265).
        """
        return self.device_type in _HV_CABINET_MODELS

    @property
    def has_peak_shaving_block(self) -> bool:
        """Return True if this system exposes a readable HR(20000–20051) peak-shaving block.

        Currently False for every model: no inverter has been confirmed to answer the read on
        real hardware. See `_PEAK_SHAVING_MODELS`.
        """
        return self.device_type in _PEAK_SHAVING_MODELS

    @property
    def is_ems(self) -> bool:
        """Return True if this system is an EMS plant controller (HR/IR 2040-range)."""
        return self.device_type in (Model.EMS, Model.EMS_COMMERCIAL)

    @property
    def is_gateway(self) -> bool:
        """Return True if this system is a Gateway (IR 1600-range)."""
        return self.device_type == Model.GATEWAY


def _validated_serial(device: Any) -> str | None:
    """Return a device's serial number only when it validates, else None.

    Devices exposing an ``is_valid()`` self-check (battery / meter / BCU) must
    pass it — an absent device's ghost cache decodes to a junk serial we do not
    want to surface. Devices without the check fall back to a truthy
    ``serial_number``.
    """
    is_valid = getattr(device, "is_valid", None)
    if callable(is_valid) and not is_valid():
        return None
    return getattr(device, "serial_number", None) or None


class Plant(GivEnergyBaseModel):
    """Representation of a complete GivEnergy plant."""

    model_config = ConfigDict(frozen=False, use_enum_values=True, arbitrary_types_allowed=True)

    register_caches: dict[int, RegisterCache] = {}
    capabilities: PlantCapabilities | None = None
    # The inverter serial from the response envelope, adopted only from the inverter's own
    # responses (see update()). This is the earliest-available inverter identity — populated at
    # detect() from the 0x11 read — and stays correct across the plant lifecycle, unlike
    # ``Plant.inverter.serial_number`` which is empty in the detect→first-refresh window for
    # AC/HYBRID_GEN1 (reads 0x31, not populated by detect) and reads the 0x32 battery cache on a
    # bare plant. A single unified accessor is tracked in #227. The dongle serial below has no
    # register source — the envelope is its only home.
    inverter_serial_number: str = ""
    data_adapter_serial_number: str = ""
    # Ingestion timestamps per committed register block, keyed by
    # (device_address, register_type_name, base_register) → last successful commit time (#65).
    # Maintained continuously by the network consumer's update() calls, so it captures both
    # solicited responses and the dongle's unsolicited fan-out. Consumers (and refresh()'s
    # skip-if-fresh path, #196) use block_age() to reason about freshness. Excluded from
    # model_dump(): it's ephemeral runtime bookkeeping, not part of the plant's dumpable state.
    register_block_updated_at: dict[tuple[int, str, int, int], datetime] = Field(default_factory=dict, exclude=True)

    # Per-device comms-quality counters (#284): cumulative, monotonic event counts keyed by
    # device_address, for a consumer to surface a plant's "noise floor" without grepping logs.
    # Each counter mirrors a log event one-for-one (so logs and counters always agree) and only
    # ever increments — splice_held_count counts *hold events*, not currently-held banks. In-memory
    # and cumulative-since-construction (a reconnect re-instantiates the Plant; consumers track
    # reset-aware deltas). Excluded from model_dump() like the bookkeeping above — they're runtime
    # diagnostics, not dumpable plant state, but remain public gettable attributes.
    crc_failure_count: dict[int, int] = Field(default_factory=dict, exclude=True)
    splice_reject_count: dict[int, int] = Field(default_factory=dict, exclude=True)
    splice_held_count: dict[int, int] = Field(default_factory=dict, exclude=True)
    retry_count: dict[int, int] = Field(default_factory=dict, exclude=True)
    # Cold-start baseline holds (#289): a battery bank held back while the first frame after an
    # empty cache awaits a corroborating read (vs splice_held_count, which is corruption). A benign
    # "battery initialising / confirming baseline" signal — expected once per device at startup.
    cold_start_held_count: dict[int, int] = Field(default_factory=dict, exclude=True)

    # How long (seconds) to hold last-good for a disputed *constant* battery register (num_cells,
    # bms_firmware_version) before healing to a sustained new value (#286). Splice corruption that
    # flips a constant register reverts within minutes (the bank is held meanwhile, protecting the
    # co-corrupted physics like SOC), while a genuinely poisoned cold-start baseline — or a real
    # firmware upgrade — persists indefinitely and heals after this long. Consumer-tunable via
    # Client(splice_heal_seconds=…). Runtime config; excluded from model_dump.
    splice_heal_seconds: float = Field(default=900.0, exclude=True)

    # How long (seconds) a sustained *legitimate* >=2-physics battery step must persist, evolving
    # smoothly and in-range, before the terminal hard-reject heals to it (#299). ``None`` (default)
    # DISABLES the heal — the >=2-physics path stays terminal, zero behaviour change. A float opts
    # in (recommended 300, = STALE_BYPASS_SECONDS; never set below it). Separate from
    # splice_heal_seconds: that defends scalar poison which persists indefinitely (long window),
    # this a transient charge-knee surge (short window). The positive (heal-fires) path can't be
    # validated against the existing corpus, so it ships off by default until a real near-full-SOC
    # knee capture confirms the smoothness assumption. Consumer-tunable via
    # Client(splice_reject_heal_seconds=…). Runtime config; excluded from model_dump.
    splice_reject_heal_seconds: float | None = Field(default=None, exclude=True)

    # Content-staleness tracker — the duration substrate for frozen-BMS-cache detection (#91).
    # Keyed identically to register_block_updated_at; each value is (content_hash, unchanged_since)
    # where unchanged_since is the ingestion time of the FIRST commit in the current
    # byte-identical run. O(1) per block and survives arbitrarily long unchanged runs (a bounded
    # deque of hashes could not — it evicts the run's origin). Private/ephemeral, resets on
    # reconnect. Surfaced read-only via content_unchanged_seconds(); no freeze *verdict* is
    # exposed — see that method for why a threshold isn't yet derivable.
    _block_unchanged_since: dict = PrivateAttr(default_factory=dict)

    # Splice-guard escrow (#256): per battery device address, the single physics-singleton
    # transition currently held back pending confirmation — (tripping IR number, comparable
    # value held). A held bank never updates the cache, so the next poll re-compares against
    # the same last-good; the held value commits only if the device reads it again within
    # threshold (genuine step persists) rather than snapping back (transient splice reverts).
    # Ephemeral runtime state, rebuilt with a fresh Plant on reconnect; not serialised.
    _splice_escrow: dict[int, tuple[int, int]] = PrivateAttr(default_factory=dict)

    # Cold-start baseline confirmation (#289): per battery device address, the first full bank seen
    # against an empty cache, held pending a corroborating read — (the 60-value bank-relative frame,
    # ingestion time). A cold-start frame is not adopted until the next poll reads it the same (no
    # physics/immutable trip between the two), so a transient sub-bus splice (#256) — different
    # garbage each poll — never corroborates and never poisons the baseline. Most-recent-wins on a
    # disagreement. A persistently-identical scalar-immutable poison corroborates and is left to the
    # #286 heal; a corroborated temp-zero corruption cohort is refused outright (it would hard-reject
    # all healthy data, which the scalar heal can't recover). Ephemeral; rebuilt on reconnect.
    _splice_pending_baseline: dict[int, tuple[list[int], datetime]] = PrivateAttr(default_factory=dict)

    # Splice-guard observation clock (#256): per battery device address, the ingestion time of the
    # last full IR(60,60) bank the guard examined — accepted OR rejected. The stale-baseline bypass
    # keys off this, NOT the last accepted commit: a sustained corruption run (every poll rejected)
    # leaves the last-good commit ageing past the bypass window, but keeps arriving each poll, so
    # this clock stays ~one poll old and the bypass never fires. Only a genuine polling gap (real
    # outage, no banks at all) makes it stale and resets to cold-start adoption. Ephemeral; resets
    # with a fresh Plant on reconnect; not serialised.
    _splice_last_seen: dict[int, datetime] = PrivateAttr(default_factory=dict)

    # Scalar-immutable poison-recovery streak (#281): per battery device address,
    # (signature, started_at, consecutive_count) where signature is the sorted tuple of
    # (IR number, incoming value) over the poll's scalar-immutable trips (IR97/IR98). Tracks a
    # *stable* disagreement on a constant scalar — a real value a healthy pack keeps reporting
    # after a poisoned cold-start baseline, or a genuine BMS firmware upgrade. A changing
    # signature (oscillating garbage) resets it, so corruption never accumulates a streak. Used
    # by both the coherent-physics escrow (confirm on the second identical read) and the
    # physics-drift backstop (force re-baseline once stable). Ephemeral; not serialised.
    _splice_immut_streak: dict[int, tuple[tuple[tuple[int, int], ...], datetime, int]] = PrivateAttr(
        default_factory=dict
    )

    # Sustained-step heal streak (#299): per battery device address, (prev_incoming_frame,
    # started_at, consecutive_count). When a >=2-physics reject is heal-eligible (voltage/cap-class
    # trips, in absolute range — see battery_splice.heal_eligible) and the heal is enabled, the bank
    # is held but the incoming frames are tracked here. The streak advances only while each new frame
    # is a SMOOTH continuation of the *previous incoming* frame (classify_transition between
    # consecutive incomings is clean), so a legitimate charge-knee surge — which drifts smoothly —
    # accumulates, while corruption (which reverts or jumps) restarts the count. After
    # SPLICE_REJECT_HEAL_POLLS smooth polls AND splice_reject_heal_seconds, the latest frame is
    # adopted as the new baseline. Ephemeral; not serialised.
    _splice_reject_streak: dict[int, tuple[list[int], datetime, int]] = PrivateAttr(default_factory=dict)

    # Direct-inverter register caches injected by add_direct_source() for multi-Client
    # reconciliation (#106 Phase 3). Stored separately from register_caches to avoid the
    # Modbus address collision (both EMS controller and direct inverter live at 0x11).
    # Not serialised — ephemeral runtime state rebuilt by the consumer on each run.
    _direct_source_caches: list[RegisterCache] = PrivateAttr(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        """Ensure a default register cache is always present."""
        if not self.register_caches:
            self.register_caches = {0x32: RegisterCache()}

    # Authoritative device-address map (GivEnergy installer app v1.154.3 `device_address_map`),
    # for orientation — not every band is modelled/routed below:
    #   0x11        inverter / EMS controller    (0x31 = legacy pre-#189 facade)
    #   0x21        EMS firmware-version device
    #   0x01-0x08   energy meters
    #   0x20+       BMS cluster (per clusterId)  — UNMODELLED (see #329)
    #   0x23-0x2A   PCS-managed inverters
    #   0x31+/0x32-0x37  LV battery packs
    #   0x50-0x6F   HV BMU (per module)
    #   0x70-0x8F   HV BCU (per stack)
    #   0x90+       HV BAMS                       — UNMODELLED
    # See docs/reference/registers/installer-app-reference.md.
    def _getter_for_device_address(self, device_address: int) -> type[RegisterGetter] | None:
        """Return the RegisterGetter class appropriate for a given device address.

        With capabilities the inverter lives at ``capabilities.inverter_address``
        (0x11 since #189; 0x31 may persist from pre-#189 state and the AC/
        HYBRID_GEN1 hardware facade still answers there) and 0x32 is LV battery
        pack #1. Without capabilities we fall back to the legacy mapping where
        the inverter was cached at 0x32, and also treat 0x11/0x31 as inverter so
        replay/debug tooling (which feeds PDUs to a bare Plant) keeps validating
        inverter banks at either wire address — including passive captures of
        other consumers still polling the 0x31 facade.
        """
        if self.capabilities is not None:
            if device_address == self.capabilities.inverter_address:
                return SinglePhaseInverterRegisterGetter
            # After the inverter check so a (theoretical) pre-#189 persisted
            # inverter_address=0x31 still routes to the inverter getter.
            if device_address == self.capabilities.lv_bcu_address:
                return LvBcuRegisterGetter
            if device_address in self.capabilities.hv_bmu_addresses:
                return BmuRegisterGetter
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

    def redact(self) -> "Plant":
        """Return a share-safe copy: every register cache redacted and the header serials cleared.

        ``redact_serials()`` only covers the register caches; ``inverter_serial_number`` and
        ``data_adapter_serial_number`` live on the Plant itself (populated from the PDU envelope),
        so a dumped Plant still leaks both unless they're redacted here too. The original is left
        untouched (#212/#214 share-safe-export guarantee).
        """
        from givenergy_modbus.model.register import Converter

        # Fail closed: redact_serial_strict blanks any unrecognised identifier rather than leaking
        # it verbatim (redact_serial is fail-open). register_block_updated_at is copied so the
        # redacted snapshot stays independent of later updates to the original.
        return self.model_copy(
            update={
                "register_caches": {addr: cache.redact_serials() for addr, cache in self.register_caches.items()},
                "inverter_serial_number": Converter.redact_serial_strict(self.inverter_serial_number),
                "data_adapter_serial_number": Converter.redact_serial_strict(self.data_adapter_serial_number),
                "register_block_updated_at": dict(self.register_block_updated_at),
            }
        )

    @staticmethod
    def _bump(counter: dict[int, int], device_address: int) -> None:
        """Increment a per-device comms-quality counter (#284)."""
        counter[device_address] = counter.get(device_address, 0) + 1

    def record_retry(self, device_address: int) -> None:
        """Record a consumed read retry for a device (#284); called by the Client per retry."""
        self._bump(self.retry_count, device_address)

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

        # Reject CRC-failed frames before ANY Plant state is mutated. The CRC spans the device
        # address and serial fields in the envelope, so those are untrusted on exactly the frames
        # that fail here — a corrupt 0x11 response must not clobber the stable inverter identity.
        if getattr(pdu, "crc_failed", False) and not getattr(pdu, "lenient_crc_commit", False):
            self._bump(self.crc_failure_count, pdu.device_address)
            _logger.warning(
                "Skipping CRC-failed response from 0x%02x (base=%d) — no Plant state updated",
                pdu.device_address,
                getattr(pdu, "base_register", 0),
            )
            return

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

        # The TCP dongle's serial is identical on every response regardless of the addressed
        # downstream device (verified across the AIO capture: meters, inverter, modules, BCU and
        # BMS all carry the same data_adapter serial), so adopt it from any accepted PDU.
        self.data_adapter_serial_number = pdu.data_adapter_serial_number

        # inverter_serial_number, by contrast, is the *addressed device's* serial in the envelope:
        # battery (0x32-0x37), BCU/BMS (0x70+/0xA0) and AIO battery-module (0x50-0x53) responses
        # carry their own, so adopting it from every PDU let whichever device was polled last
        # clobber the real inverter serial — merging the AIO inverter HA device into a battery
        # module downstream (givenergy-hass#95). The inverter is canonically addressed at 0x11
        # (#189), with 0x31 a hardware facade on AC/HYBRID_GEN1 that other bus consumers may
        # still poll, so gate on that pair — it excludes peripherals and the legacy 0x32
        # (battery pack #1) a pre-#119 persisted capability may still carry until detect()
        # self-heals.
        if device_address in (0x11, 0x31):
            self.inverter_serial_number = pdu.inverter_serial_number

        if isinstance(pdu, ReadHoldingRegistersResponse):
            incoming = {HR(k): v for k, v in pdu.to_dict().items()}
            if self._commit_bank(device_address, incoming, pdu.register_count, received_at=received_at):
                self._stamp_block(device_address, "HR", pdu.base_register, pdu.register_count, received_at)
                self._track_content_change(
                    device_address, "HR", pdu.base_register, pdu.register_count, incoming, received_at
                )
        elif isinstance(pdu, ReadInputRegistersResponse):
            if pdu.is_suspicious():
                # Pattern A dongle-side substitution from #78 — known fingerprint of 16 fixed
                # constants. is_suspicious() logs at debug when it fires.
                return
            incoming = {IR(k): v for k, v in pdu.to_dict().items()}  # type: ignore[misc]
            if self._commit_bank(device_address, incoming, pdu.register_count, received_at=received_at):
                self._stamp_block(device_address, "IR", pdu.base_register, pdu.register_count, received_at)
                self._track_content_change(
                    device_address, "IR", pdu.base_register, pdu.register_count, incoming, received_at
                )
        elif isinstance(pdu, WriteHoldingRegisterResponse):
            if pdu.register == 0:
                _logger.warning(f"Ignoring, likely corrupt: {pdu}")
            else:
                # Writes target the inverter and the echo comes back on the write address
                # (0x11), and the model reads caps.inverter_address. Since #189 unified
                # addressing on 0x11 the two normally coincide, but a pre-#189 persisted
                # capability may still say 0x31 (the AC/HYBRID_GEN1 facade), so keep routing
                # the echo to where reads land — otherwise plant.inverter won't reflect the
                # write until the next load_config(), and refresh() (IR-only) never will. The
                # cache may not exist yet if the write precedes the first read there.
                target = self.capabilities.inverter_address if self.capabilities is not None else device_address
                self.register_caches.setdefault(target, RegisterCache()).update({HR(pdu.register): pdu.value})

    def _commit_bank(
        self,
        device_address: int,
        incoming: dict,
        register_count: int = 60,
        *,
        received_at: datetime | None = None,
    ) -> bool:
        """Validate incoming register bank against bounds and commit if clean.

        Returns True if the bank was committed to the cache, False if it was discarded —
        so the caller only records an ingestion timestamp (#65) for banks that actually
        landed.

        ``register_count`` is the declared size of the PDU response (typically 60 for
        standard IR/HR blocks). It is used by the Pattern B guard: rejection only applies
        to full blocks (>= 60 registers), where a simultaneous all-zero read is genuinely
        suspicious. A short read (e.g. a single power register legitimately settling to
        zero) must not be blocked.

        ``received_at`` is the PDU ingestion timestamp, threaded to the splice guard so it
        can measure baseline staleness consistently with the rest of the stamping logic.
        """
        cache = self.register_caches[device_address]
        # Pattern B (#78/#147/#199, tracked in #206): a bank that previously held non-zero data and
        # now reads entirely zero is a block-level dropout (an empty page served during a
        # transition), not real data — reject it and keep last-good. Contextual, to resolve the
        # dropout-vs-absent ambiguity that made #147 hard to action: was-non-zero & now-all-zero =
        # dropout -> reject; always-zero (absent / first read) -> fall through to the existing
        # serial-coherence / is_valid() handling that already treats all-zero as device-absence.
        # Staleness is free: a rejected bank records no #65 timestamp, so block_age() keeps growing.
        # Gated on register_count >= 60: short reads (fan-out of a single-register query returning
        # zero) are legitimate and must not be blocked here.
        if (
            register_count >= 60
            and incoming
            and all(v == 0 for v in incoming.values())
            and any(cache.get(k) for k in incoming)
        ):
            sample = next(iter(incoming))
            # WARNING (not debug): we have no on-wire capture of this event — surfacing it turns every
            # deployment (and the maintainer's soak run) into an evidence collector. A silent no-op on
            # healthy systems, since it only fires when a present device's bank drops to all-zero.
            _logger.warning(
                "Rejected all-zero %s bank (base %d) for device 0x%02x over non-zero cache — likely a "
                "Pattern B block dropout (#206); keeping last-good. Please report if seen.",
                type(sample).__name__,
                min(r._idx for r in incoming),
                device_address,
            )
            return False
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
        # Battery sub-bus splice guard (#256): valid-CRC, in-bounds, valid-serial garbage that
        # all the checks above wave through. Runs last so the existing serial gate owns serial
        # corruption (quietly) and the bounds pass runs first; it must see last-good, so it sits
        # before the update below. Gated to battery banks via the getter identity.
        if getter_cls is BatteryRegisterGetter and not self._splice_guard(
            device_address, incoming, register_count, now=received_at
        ):
            return False
        self.register_caches[device_address].update(incoming)
        return True

    def _splice_guard(
        self, device_address: int, incoming: dict, register_count: int, now: datetime | None = None
    ) -> bool:
        """Reject (or escrow) a battery bank corrupted by a valid-CRC BMS sub-bus splice (#256).

        Returns True to allow the commit, False to hold last-good. Compares the incoming bank
        against the cached last-good using per-register-class physics thresholds
        (:mod:`givenergy_modbus.model.battery_splice`): a change to a constant register or
        >=2 physically-impossible per-poll deltas is corruption and is rejected outright; a
        lone impossible delta is escrowed — held one poll and committed only if the next poll
        reads the same value again (a genuine step persists; every observed splice reverts).

        Only full battery banks are guarded: a short read can't be physics-classified, a
        device with no prior committed bank (cold start) has nothing to compare against, and
        a gap of more than ``STALE_BYPASS_SECONDS`` since the last *observed* full bank — a
        genuine polling outage, not a rejection streak — is too stale for per-poll thresholds
        to apply (legitimate multi-field drift over the gap would trip them) — all three fall
        through as a no-op commit so the cache self-heals without manual recovery. The one
        exception is the temp-zero corruption cohort, which is held (never adopted) on every
        path, not just cold start (#294).
        """
        now_ts = now if now is not None else datetime.now(UTC)
        if now_ts.tzinfo is None:
            now_ts = now_ts.replace(tzinfo=UTC)

        cache = self.register_caches[device_address]
        prev = [0] * 60
        new = [0] * 60
        present: set[int] = set()
        incoming_present: set[int] = set()
        for i in range(60):
            reg = IR(BANK_BASE + i)
            cached = cache.get(reg)
            incoming_val = incoming.get(reg)
            prev[i] = cached if cached is not None else 0
            new[i] = incoming_val if incoming_val is not None else prev[i]
            if incoming_val is not None:
                incoming_present.add(i)
                if cached is not None:
                    present.add(i)

        # Short read: a partial bank can't be physics-classified, so it commits directly — EXCEPT the
        # temp-zero corruption cohort (>=2 cell-mass temps at 0), which would seed an unrecoverable
        # poisoned baseline (#294 — the same hole #289 closed for cold start). A short read is not a
        # full observation, so this returns before the _splice_last_seen update below (it must not
        # advance the stale-bypass clock).
        if register_count < 60:
            if is_corruption_cohort(new, incoming_present):
                self._bump(self.splice_reject_count, device_address)
                _logger.warning(
                    "Rejected short battery bank for device 0x%02x — temp-zero corruption cohort; "
                    "keeping last-good. Please report if seen.",
                    device_address,
                )
                return False
            return True

        # Record this observation up front — a rejected bank is still an observation, so the gap
        # computed below measures time since we last *saw* a full bank, not since we last accepted
        # one. This is what separates a real outage from a sustained corruption run (see below).
        prev_seen = self._splice_last_seen.get(device_address)
        self._splice_last_seen[device_address] = now_ts

        if not present:
            # Cold start: no last-good to compare against. Don't adopt the first frame blindly — a
            # transient splice would poison the baseline (#289). Hold it until a second poll
            # corroborates it (incoming_present, not present, since the cache is empty here).
            return self._confirm_cold_start_baseline(device_address, list(new), incoming_present, now_ts)
        # Past cold start — a real baseline exists, so any pending first frame is moot. Clear it so a
        # short read that seeded the cache mid-confirmation can't leave an orphan around.
        self._splice_pending_baseline.pop(device_address, None)

        # Stale-observation bypass: after a genuine polling gap the per-poll thresholds don't hold
        # (legitimate SOC/temp/cap drift over the gap would exceed them), and rejected banks never
        # advance the cache, so without recovery the guard would pin the cache to the stale baseline
        # forever after a network outage. Crucially this keys off the last *observation*, not the
        # last accepted commit: a sustained corruption run (e.g. a multi-poll temp-zero stream)
        # keeps arriving and being rejected each poll, ageing the last *commit* past the window —
        # but prev_seen stays ~one poll old, so this does NOT fire and the corruption stays rejected.
        if prev_seen is not None and (now_ts - prev_seen).total_seconds() > STALE_BYPASS_SECONDS:
            if is_corruption_cohort(new, incoming_present):
                # Don't adopt the corruption cohort even post-gap (#294). Hold last-good and keep the
                # bypass armed for the next healthy frame: restore the observation clock to prev_seen
                # so the gap is still seen next poll — otherwise a healthy recovery frame would be
                # rejected against the stale baseline, re-pinning the very thing the bypass avoids.
                self._splice_last_seen[device_address] = prev_seen
                self._bump(self.splice_reject_count, device_address)
                _logger.warning(
                    "Battery bank for device 0x%02x: stale-baseline bypass blocked — temp-zero "
                    "corruption cohort post-gap; holding last-good for a healthy read. Please report if seen.",
                    device_address,
                )
                return False
            self._splice_escrow.pop(device_address, None)
            self._splice_immut_streak.pop(device_address, None)
            self._splice_reject_streak.pop(device_address, None)
            _logger.info(
                "Battery bank for device 0x%02x: %.0f s since the last observed bank — splice guard "
                "bypassed (stale baseline); adopting as new baseline.",
                device_address,
                (now_ts - prev_seen).total_seconds(),
            )
            return True

        phys, immut = classify_transition(prev, new, present)

        # Split immutable trips by recoverability (#281): the serial block (IR110-114) genuinely
        # can't change, but the scalar immutables (num_cells IR97, bms_firmware_version IR98) can be
        # poisoned by a corrupt cold-start frame — or change legitimately on a BMS firmware upgrade —
        # and a healthy pack reports them *stably*, so a sustained stable disagreement is recoverable.
        serial_immut = [t for t in immut if t[0] in IMMUTABLE_SERIAL]
        scalar_immut = [t for t in immut if t[0] in IMMUTABLE_SCALAR]

        # Hard reject: a serial-block change (wrong pack / re-address) never self-adopts.
        if serial_immut:
            self._splice_escrow.pop(device_address, None)
            self._splice_immut_streak.pop(device_address, None)
            self._splice_reject_streak.pop(device_address, None)
            self._bump(self.splice_reject_count, device_address)
            _logger.warning(
                "Rejected battery bank for device 0x%02x — sub-bus splice (serial-block change); "
                "keeping last-good. Trips: %s. Please report if seen.",
                device_address,
                self._format_splice_trips(serial_immut + phys),
            )
            return False

        # >=2 physics deltas with no recoverable scalar immutable: corruption (the temp-zero cohort,
        # incl. the IR103/104 t_max/t_min pair) OR — rarely — a legitimate sustained step (the
        # near-full-SOC charge knee, #299). When the heal is enabled (opt-in) AND the bank is
        # heal-eligible (every trip a voltage/cap-class surge in absolute range, so it can't be any
        # corruption shape the corpus contains), hand off to the smooth-streak heal: hold now, adopt
        # only after a sustained smooth in-range run. Otherwise terminal reject, as before.
        if len(phys) >= 2 and not scalar_immut:
            self._splice_escrow.pop(device_address, None)
            self._splice_immut_streak.pop(device_address, None)
            if self.splice_reject_heal_seconds is not None and heal_eligible(phys):
                return self._handle_reject_streak(device_address, new, present, phys, now_ts)
            self._splice_reject_streak.pop(device_address, None)
            self._bump(self.splice_reject_count, device_address)
            _logger.warning(
                "Rejected battery bank for device 0x%02x — sub-bus splice (>=2 physics-impossible "
                "deltas); keeping last-good. Trips: %s. Please report if seen.",
                device_address,
                self._format_splice_trips(phys),
            )
            return False

        # Scalar-immutable change (no serial trip): escrow + re-baseline rather than reject (#281).
        # A scalar disagreement isn't the sustained-step path, so any heal streak is interrupted.
        if scalar_immut:
            self._splice_reject_streak.pop(device_address, None)
            return self._handle_scalar_immutable(device_address, scalar_immut, phys, now_ts)

        # No scalar-immutable trip this poll: any in-progress scalar disagreement is interrupted, so
        # the backstop streak resets here — it requires an *uninterrupted* stable signature. Covers
        # both the physics-singleton path below and the clean-transition path (#281 review). The
        # sustained-step heal streak (#299) likewise needs an uninterrupted >=2 run, so a frame that
        # falls to <=1 trip (singleton/clean) breaks and resets it here too.
        self._splice_immut_streak.pop(device_address, None)
        self._splice_reject_streak.pop(device_address, None)

        if len(phys) == 1:
            ir_no, name, _old, new_val = phys[0]
            held = self._splice_escrow.get(device_address)
            if held is not None and held[0] == ir_no and abs(new_val - held[1]) <= THRESHOLD_BY_CLASS[name]:
                # The held value read the same again this poll — a genuine step that persists,
                # not a transient splice (which reverts) — so commit the now-confirmed bank.
                self._splice_escrow.pop(device_address, None)
                _logger.info(
                    "Battery bank for device 0x%02x: escrowed step at IR(%d) confirmed on re-read; committing.",
                    device_address,
                    ir_no,
                )
                return True
            self._splice_escrow[device_address] = (ir_no, new_val)
            self._bump(self.splice_held_count, device_address)
            # A lone out-of-threshold delta is the self-healing escrow path: held one poll, then
            # committed if it persists (genuine step) or dropped if it reverts (transient). It is
            # NOT confirmed corruption — the >=2/immutable REJECT above is — so it logs at INFO to
            # avoid alarming on legitimate load-step sag / recalibration (#256, hass#186).
            _logger.info(
                "Battery bank for device 0x%02x: single out-of-threshold delta (%s) held one poll pending "
                "confirmation; serving last-good meanwhile.",
                device_address,
                self._format_splice_trips(phys),
            )
            return False

        # Clean transition (no trips): a previously-held step that snapped back lands here, so
        # drop any escrow and commit. Log the reversion so the held->resolved story is visible at
        # one level (the hold is INFO too). The scalar-immut streak was already cleared above.
        reverted = self._splice_escrow.pop(device_address, None)
        if reverted is not None:
            _logger.info(
                "Battery bank for device 0x%02x: previously-held delta at IR(%d) reverted on re-read "
                "(transient); committing clean bank.",
                device_address,
                reverted[0],
            )
        return True

    def _confirm_cold_start_baseline(
        self, device_address: int, frame: list[int], incoming_present: set[int], now_ts: datetime
    ) -> bool:
        """Hold a device's first post-empty-cache battery bank until a second poll corroborates it (#289).

        With no last-good to compare against, adopting the first frame blindly lets a transient sub-bus
        splice (#256) poison the baseline — the very state #281/#286 then spend the heal window
        recovering from. Instead the first frame is held (cache untouched, the device serves "unknown")
        and adopted only once the next poll reads it the same — ``classify_transition`` finds no physics
        or immutable trip between the two. A transient splice reads different garbage each poll, so it
        never corroborates; on a disagreement the most-recent frame becomes the new candidate (so a
        splice in the *first* frame is recovered from).

        Two exceptions to "corroboration adopts": a frame in the temp-zero corruption cohort
        (:func:`is_corruption_cohort`) is refused even when corroborated — adopting it would
        hard-reject every healthy frame forever, an unrecoverable physics-only poison. A
        persistently-identical *scalar*-immutable poison (IR97/IR98) does corroborate and is adopted,
        because recovering that one is the #286 heal's job, not this guard's.

        Returns True to adopt (corroborated), False to keep holding last-good ("unknown").
        """
        pending = self._splice_pending_baseline.get(device_address)
        # A pending older than the stale-bypass window straddles a genuine polling gap — don't
        # corroborate across it; treat the incoming frame as a fresh first read.
        if pending is not None and (now_ts - pending[1]).total_seconds() > STALE_BYPASS_SECONDS:
            pending = None
        if pending is not None:
            phys, immut = classify_transition(pending[0], frame, incoming_present)
            if not phys and not immut and is_corruption_cohort(frame, incoming_present):
                # Corroborated, but the frame IS the temp-zero corruption signature (#256/#289 review).
                # Baselining it would be unrecoverable: every later healthy frame then trips >=2 physics
                # and is hard-rejected forever, and the #286 heal only recovers scalar-immutable poison.
                # Keep holding (cache untouched) — a healthy corroborated pair will baseline instead.
                self._bump(self.cold_start_held_count, device_address)
                _logger.warning(
                    "Battery bank for device 0x%02x: cold-start frame corroborated but is the temp-zero "
                    "corruption cohort; refusing to baseline it, holding for a healthy read. Please report if seen.",
                    device_address,
                )
                return False
            if not phys and not immut:
                self._splice_pending_baseline.pop(device_address, None)
                _logger.info(
                    "Battery bank for device 0x%02x: cold-start baseline corroborated on re-read; committing.",
                    device_address,
                )
                return True
            reason = f"cold-start reads disagree ({self._format_splice_trips(phys + immut)})"
        else:
            reason = "first cold-start frame"
        # Hold (or re-hold) the most-recent frame as the pending baseline and wait for corroboration.
        self._splice_pending_baseline[device_address] = (frame, now_ts)
        self._bump(self.cold_start_held_count, device_address)
        _logger.info(
            "Battery bank for device 0x%02x: %s — holding pending a corroborating read; serving unknown meanwhile.",
            device_address,
            reason,
        )
        return False

    def _handle_scalar_immutable(
        self,
        device_address: int,
        scalar_immut: list[tuple[int, str, int, int]],
        phys: list[tuple[int, str, int, int]],
        now_ts: datetime,
    ) -> bool:
        """Hold a scalar-immutable (IR97/IR98) disagreement; heal only after long insistence (#286).

        Supersedes the #281 fast paths (coherent 2-read / 6-poll backstop), which adopted ongoing
        corruption that happened to stay stable for a few polls.

        A constant register (num_cells, bms_firmware_version) changing is treated as corruption
        until proven otherwise: ongoing splice corruption reverts within minutes, while a genuinely
        poisoned cold-start baseline — or a real firmware upgrade — persists indefinitely. So every
        poll holds the *whole* bank at last-good (return False), which also protects any
        co-corrupted physics (e.g. SOC) riding in the same bank; the new value is adopted only once
        the SAME incoming signature has been insisted upon, uninterrupted, for at least
        ``SCALAR_IMMUT_HEAL_POLLS`` polls AND ``self.splice_heal_seconds`` seconds. A changing
        signature or a clean (baseline-matching) poll resets the streak, so corruption — which
        reverts well inside the heal window — never self-heals into the cache.

        Always a *recoverable hold* (INFO + ``splice_held_count``), never a WARNING reject. The hold
        deliberately does not re-stamp the block's ingestion time, so ``block_age`` grows and a
        consumer can see the data is cached/stale and decide what to do. Returns True to adopt
        (heal), False to hold.
        """
        sig = tuple(sorted((ir_no, new_val) for ir_no, _name, _old, new_val in scalar_immut))
        streak = self._splice_immut_streak.get(device_address)

        if streak is not None and streak[0] == sig:
            started, count = streak[1], streak[2] + 1
            elapsed = (now_ts - started).total_seconds()
            if count >= SCALAR_IMMUT_HEAL_POLLS and elapsed >= self.splice_heal_seconds:
                self._splice_escrow.pop(device_address, None)
                self._splice_immut_streak.pop(device_address, None)
                _logger.info(
                    "Battery bank for device 0x%02x: constant register(s) %s held the same value for "
                    "%d consecutive polls (%.0f s) — adopting as new baseline (poisoned baseline or "
                    "firmware change).",
                    device_address,
                    self._fmt_scalar_sig(scalar_immut),
                    count,
                    elapsed,
                )
                return True
            self._splice_immut_streak[device_address] = (sig, started, count)
            new_streak = False
        else:
            # New device, or the signature changed (oscillating garbage): (re)start the streak.
            self._splice_immut_streak[device_address] = (sig, now_ts, 1)
            new_streak = True

        self._splice_escrow.pop(device_address, None)
        self._bump(self.splice_held_count, device_address)
        if new_streak:
            # Log once per insistence run (not every poll) to avoid spamming a long hold; the
            # per-poll signal is splice_held_count + the growing block_age.
            _logger.info(
                "Battery bank for device 0x%02x: constant register(s) %s disagree with baseline — "
                "holding last-good, will adopt only after %.0f s of sustained agreement. Trips: %s.",
                device_address,
                self._fmt_scalar_sig(scalar_immut),
                self.splice_heal_seconds,
                self._format_splice_trips(scalar_immut + phys),
            )
        return False

    def _handle_reject_streak(
        self,
        device_address: int,
        new: list[int],
        present: set[int] | None,
        phys: list[tuple[int, str, int, int]],
        now_ts: datetime,
    ) -> bool:
        """Hold a heal-eligible >=2-physics step; adopt after a sustained smooth in-range run (#299).

        Reached only when the heal is enabled (``splice_reject_heal_seconds`` set) AND the bank is
        heal-eligible (:func:`~givenergy_modbus.model.battery_splice.heal_eligible`: every trip a
        voltage/capacity-class surge in absolute range, so it can't be any corruption shape the
        corpus contains). The terminal >=2-physics reject otherwise has no recovery, so a legitimate
        sustained step — the near-full-SOC charge knee, which trips >=2 voltage rules against the
        frozen baseline — freezes telemetry until it settles (#299).

        The discriminator is *smoothness across consecutive incoming frames*, NOT the value-equality
        the #286 scalar heal uses — a real surge drifts (3644->3631->3622...), so its signature never
        stabilises. A legitimate surge evolves smoothly poll-to-poll (``classify_transition`` between
        consecutive incomings is clean); corruption reverts or jumps. So the streak advances only on
        a smooth continuation and adopts the latest frame after ``SPLICE_REJECT_HEAL_POLLS`` polls
        AND ``splice_reject_heal_seconds``. Until then it's a recoverable hold (INFO +
        ``splice_held_count``), serving last-good with a growing ``block_age``. The frozen baseline is
        used only to compute ``phys`` (the eligibility gate, by the caller), never for the streak.
        Returns True to adopt (heal), False to hold.
        """
        heal_seconds = self.splice_reject_heal_seconds
        assert heal_seconds is not None  # the caller only delegates here when the heal is enabled
        streak = self._splice_reject_streak.get(device_address)
        if streak is not None:
            prev_incoming, started = streak[0], streak[1]
            step_phys, step_immut = classify_transition(prev_incoming, new, present)
            if not step_phys and not step_immut:
                # Smooth continuation of the previous incoming frame — advance the streak.
                count = streak[2] + 1
                elapsed = (now_ts - started).total_seconds()
                if count >= SPLICE_REJECT_HEAL_POLLS and elapsed >= heal_seconds:
                    self._splice_reject_streak.pop(device_address, None)
                    _logger.info(
                        "Battery bank for device 0x%02x: sustained step evolved smoothly and in-range "
                        "for %d consecutive polls (%.0f s) — adopting as new baseline (legitimate "
                        "surge, e.g. near-full-SOC charge knee). Trips: %s.",
                        device_address,
                        count,
                        elapsed,
                        self._format_splice_trips(phys),
                    )
                    return True
                self._splice_reject_streak[device_address] = (new, started, count)
                new_streak = False
            else:
                # Reverted or jumped — not a smooth continuation; restart from this frame.
                self._splice_reject_streak[device_address] = (new, now_ts, 1)
                new_streak = True
        else:
            # First heal-eligible reject for this device — start the streak.
            self._splice_reject_streak[device_address] = (new, now_ts, 1)
            new_streak = True

        self._bump(self.splice_held_count, device_address)
        if new_streak:
            # Log once per insistence run (not every poll), like the #286 scalar hold.
            _logger.info(
                "Battery bank for device 0x%02x: >=2-physics step is heal-eligible (voltage/capacity "
                "surge in range) — holding last-good, will adopt only after %.0f s of smooth in-range "
                "evolution. Trips: %s.",
                device_address,
                heal_seconds,
                self._format_splice_trips(phys),
            )
        return False

    @staticmethod
    def _fmt_scalar_sig(scalar_immut: list[tuple[int, str, int, int]]) -> str:
        """Render scalar-immutable trips compactly for the INFO logs, e.g. ``IR(98) 3005->3010``."""
        return ", ".join(f"IR({ir_no}) {old}->{new}" for ir_no, _name, old, new in scalar_immut)

    @staticmethod
    def _format_splice_trips(trips: list[tuple[int, str, int, int]]) -> str:
        """Render splice-guard trips compactly for the WARNING log (raw register units)."""
        return ", ".join(f"IR({ir}) {name} {old}->{new}" for ir, name, old, new in trips)

    def _stamp_block(
        self,
        device_address: int,
        reg_type: str,
        base_register: int,
        register_count: int,
        received_at: datetime | None,
    ) -> None:
        """Record the ingestion time of a committed register block (#65).

        The key includes ``register_count`` so that a partial response (e.g. IR(0,1)) does
        not mark a full 60-register block as fresh — skip-if-fresh (#196) specifically checks
        for the IR(0,60) key (count=60). See Codex review on PR #208.
        """
        ts = received_at or datetime.now(UTC)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        self.register_block_updated_at[(device_address, reg_type, base_register, register_count)] = ts

    def block_age(
        self,
        device_address: int,
        reg_type: str,
        base_register: int,
        register_count: int,
        *,
        now: datetime | None = None,
    ) -> float | None:
        """Seconds since a register block was last committed, or None if never seen.

        ``reg_type`` is ``"HR"`` or ``"IR"``. ``register_count`` must match the count used
        when the block was stamped — typically 60 for standard GivEnergy IR/HR blocks. This
        prevents a partial response (e.g. IR(0,1)) from being mistaken for a full IR(0,60)
        block by the skip-if-fresh logic in refresh() (#196).

        Used to reason about freshness and staleness in the fan-out skip (#196) and Pattern B
        all-zero rejection (#206).
        """
        ts = self.register_block_updated_at.get((device_address, reg_type, base_register, register_count))
        if ts is None:
            return None
        effective_now = now or datetime.now(UTC)
        if effective_now.tzinfo is None:
            effective_now = effective_now.replace(tzinfo=UTC)
        return (effective_now - ts).total_seconds()

    def register_age(
        self,
        device_address: int,
        register: Register,
        *,
        now: datetime | None = None,
    ) -> float | None:
        """Seconds since the freshest stamped block *containing* ``register`` was committed (#247).

        Unlike ``block_age()``, the caller doesn't need to know block boundaries or the
        stamped count — every stamped window for the device whose [base, base+count) span
        covers the register is considered, and the freshest wins. None if no stamped
        window covers it. Pair with ``RegisterGetter.registers_of()`` to reason about a
        model attribute's freshness.
        """
        effective_now = now or datetime.now(UTC)
        if effective_now.tzinfo is None:
            effective_now = effective_now.replace(tzinfo=UTC)
        best: datetime | None = None
        for (dev, reg_type, base, count), ts in self.register_block_updated_at.items():
            if dev == device_address and reg_type == register.reg_type and base <= register.index < base + count:
                if best is None or ts > best:
                    best = ts
        if best is None:
            return None
        return (effective_now - best).total_seconds()

    def _track_content_change(
        self,
        device_address: int,
        reg_type: str,
        base_register: int,
        register_count: int,
        committed: dict,
        received_at: datetime | None,
    ) -> None:
        """Maintain the (content_hash, unchanged_since) tracker for this block (#91).

        Called from update() whenever _commit_bank() returns True, mirroring _stamp_block().
        Hashes the full committed dict: if the hash matches the stored one the content is
        byte-identical to the previous commit and unchanged_since is left anchored at the first
        commit of the run; otherwise (changed content, or first sight) the hash and timestamp
        are reset. unchanged_since therefore marks when the current content first appeared, and
        content_unchanged_seconds() reads off how long it has held — the duration signal a freeze
        detector needs. O(1) per block; survives unchanged runs of any length.

        This is the staleness *primitive*, not a freeze verdict: replaying the real capture
        corpus showed healthy, actively-polled LV batteries hold byte-identical IR(60,60) content
        for streaks of 23-26 consecutive samples (dongle fan-out re-serves the same cached frame
        to every TCP client, and battery telemetry genuinely doesn't change every poll). A verdict
        needs a duration threshold validated against more than the single freeze capture we have.
        #57's bounds-discard calibration ("discarded bank matches last accepted vs genuinely new")
        reads the stored hash too. See #91.
        """
        ts = received_at or datetime.now(UTC)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        key = (device_address, reg_type, base_register, register_count)
        content_hash = hash(frozenset(committed.items()))
        prev = self._block_unchanged_since.get(key)
        if prev is None or prev[0] != content_hash:
            self._block_unchanged_since[key] = (content_hash, ts)

    def content_unchanged_seconds(
        self,
        device_address: int,
        reg_type: str,
        base_register: int,
        register_count: int,
        *,
        now: datetime | None = None,
    ) -> float | None:
        """Seconds a register block's content has been byte-identical, or None if never seen (#91).

        Reports a raw duration, not a freeze verdict: a high value *may* indicate a frozen BMS
        cache (e.g. a battery whose BMS is in firmware-update bootloader mode), but on the real
        capture corpus healthy LV batteries also hold IR(60,60) content steady for long stretches
        (dongle fan-out + genuinely-static telemetry). Distinguishing a freeze from a live-but-
        static device needs a threshold validated against more freeze captures than currently
        exist, so this method deliberately makes no claim — callers compose it with their own
        policy. See #91.

        ``reg_type`` is ``"HR"`` or ``"IR"``; ``register_count`` must match the committed block.
        """
        entry = self._block_unchanged_since.get((device_address, reg_type, base_register, register_count))
        if entry is None:
            return None
        effective_now = now or datetime.now(UTC)
        if effective_now.tzinfo is None:
            effective_now = effective_now.replace(tzinfo=UTC)
        return (effective_now - entry[1]).total_seconds()

    @property
    def inverter(self) -> SinglePhaseInverter | ThreePhaseInverter:
        """Return the inverter model, dispatching on device type when capabilities are available.

        Tolerates the inverter-address cache not yet existing — a pre-#189 persisted
        capability may still point at 0x31, which detect() doesn't populate (it reads
        identity at 0x11), so this would otherwise KeyError between detect() and the
        first poll. Returns an empty-cache model in that window, matching the
        .ems / .gateway accessors. (#119, #189)
        """
        if self.capabilities:
            cache = self.register_caches.get(self.capabilities.inverter_address, RegisterCache())
            return select_inverter(self.capabilities.device_type, cache)
        return SinglePhaseInverter.from_register_cache(self.register_caches[0x32])

    @property
    def inverter_serial(self) -> str:
        """Single authoritative inverter serial, robust across the whole plant lifecycle (#227).

        Resolves the earliest-available inverter identity by trying, in order:

        1. HR(13-17) in the capability-selected inverter cache (``inverter_address`` — 0x11
           since #189; 0x31 only via a pre-#189 persisted capability);
        2. HR(13-17) in the 0x11 cache — ``detect()``'s ``HR(0,60)`` identity read lands here for
           every model, so this covers the detect→first-refresh window when a stale capability
           still points at 0x31;
        3. the ``inverter_serial_number`` envelope field — populated at ``detect()`` and the only
           home on a persisted/bare plant carrying no register caches.

        A register block is only accepted if it decodes to a valid serial (``is_valid_serial`` —
        the same coherence gate ``_commit_bank`` ingestion uses), so a malformed/partial block in a
        restored or tampered cache falls through to the envelope rather than outranking it.

        Deliberately never reads the 0x32 battery cache, so a bare or pre-detect plant can't
        surface a battery pack's serial as the inverter's. Reads via ``.get()`` so it never
        mutates the (defaultdict) caches. Once consumers move to this accessor, the envelope
        field can be deprecated.
        """
        addresses = [0x11]
        # Prefer the capability-selected register home (0x11 since #189, or a persisted 0x31);
        # 0x32 is the battery pack and never a valid inverter address, so a stale pre-#119
        # 0x32 capability is ignored.
        if self.capabilities is not None and self.capabilities.inverter_address in (0x11, 0x31):
            addresses.insert(0, self.capabilities.inverter_address)
        for addr in dict.fromkeys(addresses):  # de-dup, preserve order
            cache = self.register_caches.get(addr)
            if cache is None:
                continue
            raw = [cache.get(HR(n)) for n in range(13, 18)]  # .get(): never mutate the defaultdict
            if any(v is None for v in raw):
                continue  # fail closed on a partially-present serial block
            serial = Converter.serial(*cast("list[int]", raw))
            # Coherence gate (same as _commit_bank ingestion): a complete block can still
            # decode to garbage — an interior zero register strips to a short string
            # (SA12\x00\x00G047 -> "SA12G047"), and a persisted/tampered cache can hold spaces
            # or other malformed data. is_valid_serial() requires a clean 10-char serial, so
            # such a block falls through to a known-good envelope serial rather than outranking it.
            if serial and is_valid_serial(serial):
                return serial
        return self.inverter_serial_number

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
        """Return HV battery stacks (BCU + per-module BMUs) for HV systems; [] for LV systems.

        Each BMU is decoded from its **own** device-address cache (0x50 + running module index,
        contiguous across stacks), matching the separate-address AIO layout. Single-stack
        allocation is installer-confirmed; the multi-stack stride is not yet wire-confirmed
        (#265). Module caches that haven't been polled (or don't respond) decode to all-None and
        report ``is_valid() == False``.
        """
        if not self.capabilities or not self.capabilities.bcu_stacks:
            return []
        stacks = []
        next_bmu_addr = 0x50
        for offset, num_modules in self.capabilities.bcu_stacks:
            device_addr = 0x70 + offset
            cache = self.register_caches.get(device_addr, RegisterCache())
            bcu = Bcu.from_register_cache(cache)
            bmus = []
            for i in range(num_modules):
                bmu_cache = self.register_caches.get(next_bmu_addr + i, RegisterCache())
                bmus.append(Bmu.from_register_cache(bmu_cache, i))
            next_bmu_addr += num_modules
            stacks.append(HvStack(device_address=device_addr, bcu=bcu, bmus=bmus))
        return stacks

    @property
    def aio_battery_modules(self) -> list[AioBatteryModule]:
        """Return per-module AIO battery models (#192), one per separate-address module cache.

        All-in-One units expose each removable module at its own device address (0x50-0x53),
        each carrying 24 cell voltages, temperatures, and the module's own serial. Empty for
        non-AIO plants and until the module caches have been polled.
        """
        if not self.capabilities or not self.capabilities.aio_battery_module_addresses:
            return []
        modules = []
        for addr in self.capabilities.aio_battery_module_addresses:
            if addr in self.register_caches:
                try:
                    modules.append(AioBatteryModule.from_register_cache(self.register_caches[addr], addr))
                except Exception:
                    _logger.error("Failed to decode AIO battery module at 0x%02x", addr, exc_info=True)
        return modules

    @property
    def lv_bcu(self) -> LvBcu | None:
        """Return the LV BCU stack-level block, or None when absent.

        None when capabilities are unset, the block wasn't detected (firmware-gated —
        see model/lv_bcu.py), or its cache hasn't been populated yet.
        """
        if not self.capabilities or self.capabilities.lv_bcu_address is None:
            return None
        cache = self.register_caches.get(self.capabilities.lv_bcu_address)
        if not cache:
            return None
        try:
            return LvBcu.from_register_cache(cache)
        except Exception:
            _logger.error("Failed to decode LV BCU at 0x%02x", self.capabilities.lv_bcu_address, exc_info=True)
            return None

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

    def add_direct_source(self, caches: dict[int, RegisterCache]) -> None:
        """Store direct-inverter register caches for serial reconciliation (#106 Phase 3).

        Caches are stored separately from ``register_caches`` to avoid the Modbus
        address collision (both the EMS controller and a directly-connected inverter
        live at 0x11). Call this on an EMS plant after collecting data from a second
        Client pointing at one of the EMS-managed inverters; ``inverters`` and
        ``serial_index`` will then return merged views for matching serials.
        """
        self._direct_source_caches.extend(caches.values())

    @property
    def serial_index(self) -> dict[str, UnifiedInverter]:
        """Map each known inverter serial number to its :class:`Inverter` facade.

        Built from :attr:`inverters`, so the same reconciliation logic applies:
        merged entries (direct + EMS rollup) have ``data_source="merged"``,
        blinded EMS-only entries have ``data_source="ems_rollup"``, and direct-only
        entries have ``data_source="direct"``.
        """
        return {inv.serial_number: inv for inv in self.inverters if inv.serial_number}

    @property
    def inverters(self) -> list[UnifiedInverter]:
        """Return one :class:`Inverter` facade per inverter in this plant.

        For an EMS plant without direct sources: yields one :class:`Inverter` per
        non-empty managed-inverter slot in the EMS's IR(2040+) rollup
        (``data_source="ems_rollup"``).

        For an EMS plant with direct sources (injected via :meth:`add_direct_source`):
        reconciles EMS summaries with direct-inverter caches by serial number.
        Matching serials produce merged inverters (``data_source="merged"``); EMS
        slots without a matching direct source stay blinded; direct sources whose
        serial is not in the EMS rollup appear as orphan ``data_source="direct"``
        entries (#106 Phase 3).

        For a non-EMS plant: yields a single :class:`Inverter` wrapping the existing
        :attr:`inverter` (``data_source="direct"``). The legacy :attr:`inverter`
        (singular) accessor remains for back-compat.
        """
        if self.ems is not None:
            if not self._direct_source_caches:
                return [UnifiedInverter.from_summary(s) for s in self.ems.managed_inverters]

            # Decode each direct-source cache into a serial → concrete-inverter map.
            direct_by_serial: dict[str, Any] = {}
            for cache in self._direct_source_caches:
                raw_dtc = cache.get(HR(0))
                if raw_dtc is None:
                    continue
                arm_fw = cache.get(HR(21)) or 0
                model = resolve_model(raw_dtc, arm_fw)
                inv = select_inverter(model, cache)
                sn = getattr(inv, "serial_number", None)
                if sn:
                    direct_by_serial[sn] = inv

            result: list[UnifiedInverter] = []
            ems_serials: set[str] = set()
            for summary in self.ems.managed_inverters:
                sn = summary.serial_number
                ems_serials.add(sn)
                if sn in direct_by_serial:
                    result.append(UnifiedInverter.merge(direct_by_serial[sn], summary))
                else:
                    result.append(UnifiedInverter.from_summary(summary))

            # Orphan: direct-source inverters not present in EMS rollup
            for sn, direct_inv in direct_by_serial.items():
                if sn not in ems_serials:
                    result.append(UnifiedInverter.from_direct(direct_inv))

            return result

        # The single direct inverter owns every battery / HV stack / AIO module in
        # the plant cache (#106 Phase 2, #192). Inject the already-decoded sub-devices
        # so the facade can expose ownership without importing concrete Battery /
        # HvStack / AioBatteryModule types. Splitting across multiple direct inverters
        # is Phase 3.
        return [
            UnifiedInverter.from_direct(
                self.inverter,
                batteries=self.batteries,
                hv_stacks=self.hv_stacks,
                battery_modules=self.aio_battery_modules,
            )
        ]

    @property
    def gateway(self) -> GatewayV1 | GatewayV2 | None:
        """Return GatewayV1 or GatewayV2 model for GATEWAY device type; None otherwise."""
        if not self.capabilities or self.capabilities.device_type != Model.GATEWAY:
            return None
        cache = self.register_caches.get(self.capabilities.inverter_address, RegisterCache())
        return select_gateway(cache)

    @property
    def devices(self) -> list[PlantDevice]:
        """Enumerate every device on this plant as typed :class:`PlantDevice` rows.

        Each row carries a generic :class:`DeviceType` discriminator, a serial
        (where the device exposes a valid one), the plant's model where
        meaningful, and the already-decoded typed model in
        :attr:`PlantDevice.device`. Built by composing the existing accessors —
        :attr:`inverters`, :attr:`ems`, :attr:`gateway`, :attr:`meters` — so the
        EMS-rollup-vs-direct decision is honoured once and a controller (EMS or
        gateway) can never appear as an ``INVERTER`` row.

        Batteries and HV stacks are **owned by their inverter** (#106 Phase 2):
        they ride on the ``INVERTER`` row's ``device.batteries`` /
        ``device.hv_stacks`` rather than as top-level rows. Meters are not
        inverter-owned, so they stay flat rows (the Phase 1 meter-identity
        limitation).
        """
        caps = self.capabilities
        model = caps.device_type if caps else None
        # On EMS/Gateway plants the plant model is the controller's model, not an
        # inverter model — don't let directly-decoded inverters inherit it.
        inverter_model = model if caps and not (caps.is_ems or caps.is_gateway) else None
        rows: list[PlantDevice] = []

        # On a gateway plant the singular ``inverter`` decodes the gateway's own
        # cache as a spurious inverter — suppress that row; the GATEWAY row below
        # represents the device instead.
        inverter_emitted = False
        if not (caps and caps.is_gateway):
            for inverter in self.inverters:
                rows.append(
                    PlantDevice(
                        device_type=DeviceType.INVERTER,
                        device=inverter,
                        serial_number=inverter.serial_number or None,
                        # A blinded (EMS-rollup) inverter's own model is unknown;
                        # only a directly-decoded inverter inherits the plant model.
                        model=None if inverter.is_blinded else inverter_model,
                    )
                )
                inverter_emitted = True

        # AIO per-module battery sub-devices (#192) — enumerable BATTERY_MODULE rows,
        # owned by the inverter (also injected on its ``device.battery_modules``), keyed
        # by the module's own HX-prefixed serial. GivTCP surfaces these as separate
        # per-module devices; mirror that so consumers can name one HA device per module.
        for module in self.aio_battery_modules:
            rows.append(
                PlantDevice(
                    device_type=DeviceType.BATTERY_MODULE,
                    device=module,
                    serial_number=_validated_serial(module),
                )
            )

        if (ems := self.ems) is not None:
            rows.append(PlantDevice(device_type=DeviceType.EMS, device=ems, model=model))

        if (gateway := self.gateway) is not None:
            rows.append(PlantDevice(device_type=DeviceType.GATEWAY, device=gateway, model=model))

        # Batteries / HV stacks nest under their inverter via the injected
        # ``inverter.batteries`` / ``.hv_stacks`` (see :attr:`inverters`). The
        # only case with no inverter row to carry them is a gateway plant, where
        # the inverter is suppressed — emit those as flat rows rather than drop
        # them (orphan guard; proper partner-AIO expansion is a later phase).
        if not inverter_emitted:
            for battery in self.batteries:
                rows.append(
                    PlantDevice(
                        device_type=DeviceType.BATTERY,
                        device=battery,
                        serial_number=_validated_serial(battery),
                    )
                )
            for stack in self.hv_stacks:
                rows.append(
                    PlantDevice(
                        device_type=DeviceType.HV_STACK,
                        device=stack,
                        serial_number=_validated_serial(stack.bcu),
                    )
                )

        for meter in self.meters.values():
            rows.append(
                PlantDevice(
                    device_type=DeviceType.METER,
                    device=meter,
                    serial_number=_validated_serial(meter),
                )
            )

        return rows
