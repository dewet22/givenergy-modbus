"""GivEnergy AIO (All-in-One) per-module battery data (#192).

An All-in-One stores each removable battery module in its **own device-address cache**
(0x50-0x53), each a plain ``IR(60-119)`` block — 24 cell voltages, cell temperatures, and
the module's own ``HX``-prefixed hardware serial. This differs from the HV ``Bmu`` stride
layout (modules offset within a single BCU cache); see ``model/hv_bcu.py``. The per-cell
decode is shared via :func:`decode_cells_temps_serial`.
"""

from typing import Any

from pydantic import ConfigDict, create_model

from givenergy_modbus.model.hv_bcu import decode_cells_temps_serial, module_cell_temp_serial_fields


def _aio_module_fields() -> dict[str, tuple[Any, None]]:
    fields = module_cell_temp_serial_fields()
    fields["module_address"] = (int | None, None)
    return fields


_AioBatteryModuleBase = create_model(  # type: ignore[call-overload]
    "AioBatteryModule",
    __config__=ConfigDict(frozen=True),
    **_aio_module_fields(),
)


class AioBatteryModule(_AioBatteryModuleBase):  # type: ignore[misc,valid-type]
    """One AIO battery module: 24 cell voltages + temperatures + the module serial.

    Decoded from the module's own device-address cache (``base=0``), keyed by its Modbus
    ``module_address`` (0x50-0x53).
    """

    @classmethod
    def from_register_cache(cls, register_cache, module_address: int) -> "AioBatteryModule":
        """Construct an AioBatteryModule from its own register cache (no stride)."""
        data = decode_cells_temps_serial(register_cache, base=0)
        data["module_address"] = module_address
        return cls.model_validate(data)

    def is_valid(self) -> bool:
        """True if the module reports a non-blank serial (i.e. a module is present)."""
        return self.serial_number not in (None, "", "          ")  # type: ignore[attr-defined]
