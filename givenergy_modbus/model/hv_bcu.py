"""GivEnergy HV battery BCU (Battery Control Unit) and BMU (Battery Module Unit) models.

BCU device addresses: 0x70–0x8F
BMU device addresses: 0x50–0x6F

`HvStack` bundles a BCU and its BMUs for one physical battery stack.

Each BMU answers at its **own device address** (0x50+) with a plain ``IR(60-119)`` block —
24 cell voltages, temperatures and the module serial — the same separate-address layout as
`AioBatteryModule` (see `model/aio_battery.py`), decoded at ``base = 0`` via
:func:`decode_cells_temps_serial`. (Installer-confirmed; the earlier stride-within-the-BCU-cache
decode read the BCU's own cluster registers as cell data — see #265. Not yet wire-confirmed.)
"""

import warnings
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar

from pydantic import ConfigDict, create_model

from givenergy_modbus.model.register import IR, RegisterGetter, RegisterMetadataMixin
from givenergy_modbus.model.register import Converter as C
from givenergy_modbus.model.register import RegisterDefinition as Def


class BcuStatus(IntEnum):
    """HV BCU operating status (IR(70)).

    Codes per the GivEnergy Installer app v1.154.3 BCU_STATUS enum. Raw int stays
    accessible via ``status``; the typed label is exposed as ``status_label``, which
    decodes unknown codes to ``None`` rather than raising.
    """

    BMS_INITIALISING = 0
    PRECHARGING = 1
    STANDBY = 2
    CHARGING = 3
    DISCHARGING = 4
    ERROR = 5
    UPDATING = 6
    POWERED_OFF = 7
    PRODUCTION = 8


def _bcu_status_from(code: int | None) -> BcuStatus | None:
    """Lenient BcuStatus decode — returns None for unknown codes."""
    if code is None:
        return None
    try:
        return BcuStatus(code)
    except ValueError:
        return None


class BcuRegisterGetter(RegisterGetter):
    """Structured format for HV BCU cluster-level attributes (device addresses 0x70–0x8F)."""

    REGISTER_LUT = {
        # Input Registers IR(60)–IR(105)
        "pack_software_version": Def(C.gateway_version, None, IR(60), IR(61), IR(62), IR(63)),
        "number_of_modules": Def(C.uint16, None, IR(64)),
        "cells_per_module": Def(C.uint16, None, IR(65)),
        "cluster_cell_voltage": Def(C.uint16, None, IR(67)),
        "cluster_cell_temperature": Def(C.uint16, None, IR(68)),
        "status": Def(C.uint16, None, IR(70)),
        "status_label": Def(C.uint16, _bcu_status_from, IR(70)),
        "battery_voltage": Def(C.deci, None, IR(73), min=0.0, max=1000.0),
        "load_voltage": Def(C.deci, None, IR(74), min=0.0, max=1000.0),
        "battery_current": Def(C.int16, C.deci, IR(76), min=-500.0, max=500.0),
        "battery_power": Def(C.milli, None, IR(79)),
        "battery_soc_max": Def((C.duint8, 0), None, IR(80), min=0, max=100),
        "battery_soc_min": Def((C.duint8, 1), None, IR(80), min=0, max=100),
        "battery_soh": Def(C.uint16, None, IR(81), min=0, max=100),
        "charge_energy_total": Def(C.uint32, C.deci, IR(82), IR(83)),
        "discharge_energy_total": Def(C.uint32, C.deci, IR(84), IR(85)),
        "charge_capacity_total": Def(C.uint32, None, IR(86), IR(87)),
        "discharge_capacity_total": Def(C.uint32, None, IR(88), IR(89)),
        "charge_energy_today": Def(C.uint32, C.deci, IR(90), IR(91)),
        "discharge_energy_today": Def(C.uint32, C.deci, IR(92), IR(93)),
        "charge_capacity_today": Def(C.uint32, None, IR(94), IR(95)),
        "discharge_capacity_today": Def(C.uint32, None, IR(96), IR(97)),
        # nominal capacity in Ah (deci); kWh conversion is left to callers
        "battery_nominal_capacity_ah": Def(C.deci, None, IR(98)),
        "remaining_battery_capacity_ah": Def(C.deci, None, IR(99)),
        "number_of_cycles": Def(C.deci, None, IR(100)),
        "min_discharge_voltage": Def(C.deci, None, IR(102)),
        "max_charge_voltage": Def(C.deci, None, IR(103)),
        "min_discharge_current": Def(C.deci, None, IR(104)),
        "max_charge_current": Def(C.deci, None, IR(105)),
        # Diagnostic tail (IR(107)–IR(119)): inside the polled IR(60–119) window but
        # previously dropped. Names per the GivEnergy Installer app v1.154.3
        # HV_BCU_INPUT_REGISTER. Exposed as raw read-back: the bit-level semantics of
        # the warning/protection/fault words are not yet enum-confirmed, so consumers
        # can detect a non-zero condition without the library implying a decode it
        # cannot yet substantiate (cf. the HR(300–359) read-back precedent).
        "fan_fault_code": Def(C.uint16, None, IR(107)),
        "self_check_status": Def(C.uint16, None, IR(113)),
        "pack_warning_status": Def(C.uint32, None, IR(114), IR(115)),
        "pack_protection_status": Def(C.uint32, None, IR(116), IR(117)),
        "pack_fault_status": Def(C.uint32, None, IR(118), IR(119)),
        # BCU unit serial, in the second block IR(120-179) (otherwise unmodelled).
        # Wire-evidenced on a real 6-module 3ph HV stack (#375 count-to-zero sweep):
        # a GE-serial string (HB…, same manufacture batch as the stack's HY… modules)
        # at IR(138-142) on the BCU device. The C.serial tag also registers it in the
        # canonical serial groups, so capture/export redaction covers it.
        "serial_number": Def(C.serial, None, IR(138), IR(139), IR(140), IR(141), IR(142)),
    }


_BcuBase = create_model(  # type: ignore[call-overload]
    "Bcu",
    __config__=ConfigDict(frozen=True),
    **BcuRegisterGetter.to_fields(),
)


class Bcu(_BcuBase, RegisterMetadataMixin):  # type: ignore[misc,valid-type]
    """GivEnergy HV Battery Control Unit (BCU) cluster-level data."""

    REGISTER_GETTER: ClassVar[type[RegisterGetter]] = BcuRegisterGetter

    @classmethod
    def from_register_cache(cls, register_cache) -> "Bcu":
        """Construct a Bcu from a RegisterCache."""
        return cls.model_validate(BcuRegisterGetter(register_cache).build())

    def is_valid(self) -> bool:
        """Try to detect if an HV BCU is present based on its attributes."""
        v = self.pack_software_version  # type: ignore[attr-defined]
        return v not in (None, "", "          ") and not all(c == "0" for c in (v or ""))


# ---------------------------------------------------------------------------
# BMU — per-module, register addresses depend on bmu_index within the BCU
# ---------------------------------------------------------------------------

# Cell count per BMU (all known HV stacks use 24 cells per module)
_BMU_CELLS = 24
# Base register addresses (relative to a module's ``base`` offset) for the per-cell block.
# Shared by the field schema, the decode, and the register LUT so they can't drift (#273).
_V_CELL_BASE = 60  # IR(60+base .. 83+base) — 24 cell voltages, milli (÷1000)
_T_CELL_BASE = 90  # IR(90+base .. 113+base) — 24 cell temps, deci (÷10)
_SERIAL_BASE = 114  # IR(114+base .. 118+base) — 5-register module serial
_SERIAL_LEN = 5


def module_cell_temp_serial_fields() -> dict[str, tuple[Any, None]]:
    """Pydantic field schema for a battery module's per-cell data (voltages, temps, serial).

    Shared by `Bmu` (HV stride layout) and `AioBatteryModule` (AIO separate-address layout) —
    both expose the same 24-cell voltage/temperature + serial shape.
    """
    fields: dict[str, tuple[Any, None]] = {}
    for i in range(1, _BMU_CELLS + 1):
        fields[f"v_cell_{i:02d}"] = (float | None, None)
        fields[f"t_cell_{i:02d}"] = (float | None, None)
    fields["serial_number"] = (str | None, None)
    return fields


def cell_temp_serial_register_lut(base: int = 0) -> dict[str, Def]:
    """field→register LUT matching :func:`decode_cells_temps_serial` for the given ``base``.

    Both `BmuRegisterGetter` (#265) and `AioBatteryModuleRegisterGetter` (#192) use ``base = 0``
    — one cache per module device address. Converters mirror the decode: voltages milli (÷1000),
    temperatures deci (÷10), serial the 5-register string decode. Drives ``registers_of()`` /
    ``precision_of()`` for staleness gating (#273); the min/max on voltages mirror
    `BatteryRegisterGetter` and are inert under the imperative decode.
    """
    lut: dict[str, Def] = {}
    for i in range(_BMU_CELLS):
        lut[f"v_cell_{i + 1:02d}"] = Def(C.milli, None, IR(_V_CELL_BASE + base + i), min=1.0, max=5.0)
        lut[f"t_cell_{i + 1:02d}"] = Def(C.deci, None, IR(_T_CELL_BASE + base + i))
    lut["serial_number"] = Def(C.serial, None, *(IR(_SERIAL_BASE + base + j) for j in range(_SERIAL_LEN)))
    return lut


def decode_cells_temps_serial(register_cache, base: int = 0) -> dict[str, Any]:
    """Decode a battery module's cells, temperatures and serial from a cache, offset by ``base``.

    Reads 24 cell voltages (IR 60-83), temperatures (IR 90-113) and the module serial
    (IR 114-118). Shared decode for the separate-address module layout: both `Bmu` (HV, #265)
    and `AioBatteryModule` (#192) pass ``base = 0`` — one cache per module device address.
    Voltages are milli (÷1000), temperatures deci (÷10). A missing register decodes as None;
    an incomplete serial group yields ``serial_number = None``.
    """
    data: dict[str, Any] = {}

    def _get(reg_idx: int) -> int | None:
        return register_cache.get(IR(reg_idx))

    for i in range(_BMU_CELLS):
        v = _get(_V_CELL_BASE + base + i)
        data[f"v_cell_{i + 1:02d}"] = v / 1000 if v is not None else None
    for i in range(_BMU_CELLS):
        t = _get(_T_CELL_BASE + base + i)
        data[f"t_cell_{i + 1:02d}"] = t / 10 if t is not None else None
    sn_regs = [_get(_SERIAL_BASE + base + j) for j in range(_SERIAL_LEN)]
    if None not in sn_regs:
        data["serial_number"] = (
            b"".join(v.to_bytes(2, "big") for v in sn_regs)  # type: ignore[union-attr]
            .decode("latin1")
            .replace("\x00", "")
            .upper()
        )
    else:
        data["serial_number"] = None
    return data


class BmuRegisterGetter(RegisterGetter):
    """field→register metadata for HV BMU per-module data (#265).

    Same separate-address layout as AIO modules — each BMU decodes its own ``IR(60-119)``
    cache at ``base = 0``; this LUT drives ``registers_of()`` / ``precision_of()`` for
    staleness gating, matching `AioBatteryModuleRegisterGetter`.
    """

    REGISTER_LUT = cell_temp_serial_register_lut(base=0)


# Pydantic model schema: the shared per-cell fields plus the module's 0-based index.
def _bmu_fields() -> dict[str, tuple[Any, None]]:
    fields = module_cell_temp_serial_fields()
    fields["bmu_index"] = (int | None, None)
    return fields


_BmuBase = create_model(  # type: ignore[call-overload]
    "Bmu",
    __config__=ConfigDict(frozen=True),
    **_bmu_fields(),
)


class Bmu(_BmuBase, RegisterMetadataMixin):  # type: ignore[misc,valid-type]
    """GivEnergy HV Battery Module Unit (BMU) per-module data.

    Decoded from the module's **own** register cache (``base = 0``), keyed by its 0-based
    ``bmu_index`` within the stack (module *k* answers at device address 0x50 + k). The earlier
    stride-within-the-BCU-cache layout addressed the wrong device, reading the BCU's cluster
    registers as cell data — see #265. Installer-derived; not yet wire-confirmed.
    """

    REGISTER_GETTER: ClassVar[type[RegisterGetter]] = BmuRegisterGetter

    @classmethod
    def from_register_cache(cls, register_cache, bmu_index: int = 0) -> "Bmu":
        """Construct a Bmu from its own register cache (no stride)."""
        data = decode_cells_temps_serial(register_cache, base=0)
        data["bmu_index"] = bmu_index
        return cls.model_validate(data)

    def is_valid(self) -> bool:
        """True if the module reports a non-blank serial (i.e. a module is present)."""
        return self.serial_number not in (None, "", "          ")  # type: ignore[attr-defined]


@dataclass(init=False)
class HvStack:
    """One HV battery stack: a BCU and the BMUs it manages."""

    device_address: int
    bcu: Bcu
    bmus: list[Bmu] = field(default_factory=list)

    def __init__(
        self,
        device_address: int | None = None,
        bcu: Bcu | None = None,
        bmus: list[Bmu] | None = None,
        *,
        slave_address: int | None = None,
    ) -> None:
        # Positional order matches the original @dataclass signature (slave_address, bcu, bmus)
        # so legacy positional callers like HvStack(0x70, bcu_obj) keep working.
        if slave_address is not None:
            if device_address is not None:
                raise TypeError("pass either device_address= or slave_address=, not both")
            warnings.warn(
                "HvStack.slave_address is deprecated; use device_address",
                DeprecationWarning,
                stacklevel=2,
            )
            device_address = slave_address
        if device_address is None:
            raise TypeError("HvStack.__init__ missing required argument: device_address")
        if bcu is None:
            raise TypeError("HvStack.__init__ missing required argument: bcu")
        self.device_address = device_address
        self.bcu = bcu
        self.bmus = bmus if bmus is not None else []

    @property
    def slave_address(self) -> int:
        """Deprecated alias for `device_address`."""
        warnings.warn(
            "HvStack.slave_address is deprecated; use device_address",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.device_address

    @slave_address.setter
    def slave_address(self, value: int) -> None:
        warnings.warn(
            "HvStack.slave_address is deprecated; use device_address",
            DeprecationWarning,
            stacklevel=2,
        )
        self.device_address = value
