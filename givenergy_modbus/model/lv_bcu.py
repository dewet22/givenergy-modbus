"""GivEnergy LV battery BCU (stack-level BMS) data model.

The v4.1.6 doc's §4.4.1.1 "Low Voltage BCU" block gives four input registers but no
device address. Field probing (#238, #241) located it: the block answers at device
0x31, registers IR(60-63), confirmed identical on two independent LV hybrid plants.
0x31 also mirrors the inverter's live IR(0-59) below the block (as does 0x30), so the
BCU is a register *page* on an inverter-adjacent address rather than a fully separate
device.

The block is firmware-gated: populated (request currents 167/167) on packs running BMS
firmware 3022, all-zero on a unit with packs at 3007/3009. The gate could equally sit
in inverter ARM or dongle firmware — the planes weren't separable across the sampled
plants — so an all-zero block decodes as "absent/not supported", never an error.
Absent units still answer reads at 0x31 (with zeros).
"""

from typing import ClassVar

from pydantic import ConfigDict, create_model

from givenergy_modbus.model.register import IR, RegisterGetter, RegisterMetadataMixin
from givenergy_modbus.model.register import Converter as C
from givenergy_modbus.model.register import RegisterDefinition as Def

# The only address the BCU page has been observed at (#241). Capabilities store the
# address rather than assuming it, in case other models window it elsewhere.
LV_BCU_ADDRESS = 0x31


class LvBcuRegisterGetter(RegisterGetter):
    """Structured format for the LV BCU stack-level block (FC 0x04, device address 0x31)."""

    REGISTER_LUT = {
        # Input Registers IR(60)-IR(63), doc §4.4.1.1. The doc names the status pair
        # `udwBmsStatus1/2` — the `udw` prefix implies uint32 but each is listed as a
        # single register; kept as raw uint16 words until non-zero values are observed.
        "bms_status_1": Def(C.uint16, None, IR(60)),
        "bms_status_2": Def(C.uint16, None, IR(61)),
        # The charge/discharge current envelope the BMS requests from the inverter,
        # 1 A units. Only ever observed static (167/167 across two plants); whether it
        # derates live with SOC/temperature is unconfirmed — see #241.
        "request_charge_current": Def(C.uint16, None, IR(62)),
        "request_discharge_current": Def(C.uint16, None, IR(63)),
    }


_LvBcuBase = create_model(  # type: ignore[call-overload]
    "LvBcu",
    __config__=ConfigDict(frozen=True, use_enum_values=True),
    **LvBcuRegisterGetter.to_fields(),
)


class LvBcu(_LvBcuBase, RegisterMetadataMixin):  # type: ignore[misc,valid-type]
    """GivEnergy LV battery BCU stack-level data (FC 0x04, device address 0x31)."""

    REGISTER_GETTER: ClassVar[type[RegisterGetter]] = LvBcuRegisterGetter

    @classmethod
    def from_register_cache(cls, register_cache) -> "LvBcu":
        """Construct an LvBcu from a RegisterCache."""
        return cls.model_validate(LvBcuRegisterGetter(register_cache).build())

    def is_valid(self) -> bool:
        """Try to detect if the LV BCU block is present based on its attributes.

        All-zero means absent/not supported (firmware-gated — see module docstring),
        so presence requires at least one non-zero word.
        """
        return any(
            getattr(self, f) not in (None, 0)
            for f in ("bms_status_1", "bms_status_2", "request_charge_current", "request_discharge_current")
        )
