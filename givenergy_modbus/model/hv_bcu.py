"""GivEnergy HV battery BCU (Battery Control Unit) and BMU (Battery Module Unit) models.

BCU slaves: 0x70–0x8F
BMU slaves: 0x50–0x6F

The BMU register layout is offset by 120 * bmu_index within the BCU slave, which
means register addresses depend on which BMU is being read.  Because Pydantic models
require a fixed schema, `Bmu` is constructed by `Bmu.from_register_cache(cache, offset)`
which resolves all addresses before model creation.
"""

from typing import Any

from pydantic import ConfigDict, create_model

from givenergy_modbus.model.register import IR, RegisterGetter
from givenergy_modbus.model.register import Converter as C
from givenergy_modbus.model.register import RegisterDefinition as Def


class BcuRegisterGetter(RegisterGetter):
    """Structured format for HV BCU cluster-level attributes (slaves 0x70–0x8F)."""

    REGISTER_LUT = {
        # Input Registers IR(60)–IR(105)
        "pack_software_version": Def(C.gateway_version, None, IR(60), IR(61), IR(62), IR(63)),
        "number_of_modules": Def(C.uint16, None, IR(64)),
        "cells_per_module": Def(C.uint16, None, IR(65)),
        "cluster_cell_voltage": Def(C.uint16, None, IR(67)),
        "cluster_cell_temperature": Def(C.uint16, None, IR(68)),
        "status": Def(C.uint16, None, IR(70)),
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
    }


_BcuBase = create_model(  # type: ignore[call-overload]
    "Bcu",
    __config__=ConfigDict(frozen=True),
    **BcuRegisterGetter.to_fields(),
)


class Bcu(_BcuBase):  # type: ignore[misc,valid-type]
    """GivEnergy HV Battery Control Unit (BCU) cluster-level data."""

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
# Register stride between BMUs within a BCU slave's address space
_BMU_STRIDE = 120


# Build the Bmu pydantic model schema using dummy offset 0 to infer field types,
# then instantiate with real data in from_register_cache.
def _bmu_fields() -> dict[str, tuple[Any, None]]:
    fields: dict[str, tuple[Any, None]] = {}
    for i in range(1, _BMU_CELLS + 1):
        fields[f"v_cell_{i:02d}"] = (float | None, None)
        fields[f"t_cell_{i:02d}"] = (float | None, None)
    fields["serial_number"] = (str | None, None)
    fields["bmu_index"] = (int | None, None)
    return fields


_BmuBase = create_model(  # type: ignore[call-overload]
    "Bmu",
    __config__=ConfigDict(frozen=True),
    **_bmu_fields(),
)


class Bmu(_BmuBase):  # type: ignore[misc,valid-type]
    """GivEnergy HV Battery Module Unit (BMU) per-module data.

    `bmu_index` is 0-based within the BCU (module 0 uses registers 60–179,
    module 1 uses 180–299, etc.).
    """

    @classmethod
    def from_register_cache(cls, register_cache, bmu_index: int = 0) -> "Bmu":
        """Construct a Bmu from a RegisterCache for the given bmu_index."""
        base = _BMU_STRIDE * bmu_index
        data: dict[str, Any] = {"bmu_index": bmu_index}

        def _get(reg_idx: int) -> int | None:
            return register_cache.get(IR(reg_idx))

        def _milli(v: int | None) -> float | None:
            return v / 1000 if v is not None else None

        def _deci(v: int | None) -> float | None:
            return v / 10 if v is not None else None

        for i in range(_BMU_CELLS):
            data[f"v_cell_{i + 1:02d}"] = _milli(_get(60 + base + i))

        for i in range(_BMU_CELLS):
            data[f"t_cell_{i + 1:02d}"] = _deci(_get(90 + base + i))

        sn_regs = [_get(114 + base + j) for j in range(5)]
        if None not in sn_regs:
            data["serial_number"] = (
                b"".join(v.to_bytes(2, "big") for v in sn_regs)  # type: ignore[union-attr]
                .decode("latin1")
                .replace("\x00", "")
                .upper()
            )
        else:
            data["serial_number"] = None

        return cls.model_validate(data)

    def is_valid(self) -> bool:
        """Try to detect if a BMU is present based on its attributes."""
        return self.serial_number not in (None, "", "          ")  # type: ignore[attr-defined]
