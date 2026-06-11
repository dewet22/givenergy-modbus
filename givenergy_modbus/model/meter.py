"""GivEnergy meter data model."""

from enum import IntEnum
from typing import ClassVar

from pydantic import ConfigDict, create_model

from givenergy_modbus.model.register import IR, MR, RegisterGetter, RegisterMetadataMixin
from givenergy_modbus.model.register import Converter as C
from givenergy_modbus.model.register import RegisterDefinition as Def


class MeterStatus(IntEnum):
    """External meter online status."""

    DISABLED = 0
    ONLINE = 1
    OFFLINE = 2

    @classmethod
    def _missing_(cls, value):
        return cls.DISABLED


class MeterRegisterGetter(RegisterGetter):
    """Structured format for all meter measurement attributes (FC 0x04, device addresses 0x01–0x08)."""

    REGISTER_LUT = {
        # Input Registers IR(60)–IR(88)
        "v_phase_1": Def(C.deci, None, IR(60), min=0.0, max=500.0),
        "v_phase_2": Def(C.deci, None, IR(61), min=0.0, max=500.0),
        "v_phase_3": Def(C.deci, None, IR(62), min=0.0, max=500.0),
        "i_phase_1": Def(C.centi, None, IR(63)),
        "i_phase_2": Def(C.centi, None, IR(64)),
        "i_phase_3": Def(C.centi, None, IR(65)),
        "i_ln": Def(C.centi, None, IR(66)),
        "i_total": Def(C.centi, None, IR(67)),
        "p_active_phase_1": Def(C.int16, None, IR(68)),
        "p_active_phase_2": Def(C.int16, None, IR(69)),
        "p_active_phase_3": Def(C.int16, None, IR(70)),
        "p_active_total": Def(C.int16, None, IR(71)),
        "p_reactive_phase_1": Def(C.int16, None, IR(72)),
        "p_reactive_phase_2": Def(C.int16, None, IR(73)),
        "p_reactive_phase_3": Def(C.int16, None, IR(74)),
        "p_reactive_total": Def(C.int16, None, IR(75)),
        # Apparent power is deci-scaled (0.1 VA), unlike active/reactive at 1 W/var —
        # capture-proven via the displacement-PF cross-check: S >= sqrt(P²+Q²) only
        # holds at x0.1, and the same identity lands the reactive registers exactly
        # at 1 var, contradicting the doc's 0.1 var suggestion. Unsigned: apparent
        # power is a magnitude (the capture shows it positive during export while
        # p_active goes negative), and a signed decode would overflow above 3.27 kVA.
        # See #246.
        "p_apparent_phase_1": Def(C.deci, None, IR(76)),
        "p_apparent_phase_2": Def(C.deci, None, IR(77)),
        "p_apparent_phase_3": Def(C.deci, None, IR(78)),
        "p_apparent_total": Def(C.deci, None, IR(79)),
        "pf_phase_1": Def(C.pf_signed, None, IR(80), min=-1.0, max=1.0),
        "pf_phase_2": Def(C.pf_signed, None, IR(81), min=-1.0, max=1.0),
        "pf_phase_3": Def(C.pf_signed, None, IR(82), min=-1.0, max=1.0),
        "pf_total": Def(C.pf_signed, None, IR(83), min=-1.0, max=1.0),
        "frequency": Def(C.centi, None, IR(84), min=40.0, max=70.0),
        "e_import_active": Def(C.deci, None, IR(85)),
        "e_import_reactive": Def(C.deci, None, IR(86)),
        "e_export_active": Def(C.deci, None, IR(87)),
        "e_export_reactive": Def(C.deci, None, IR(88)),
    }


_MeterBase = create_model(  # type: ignore[call-overload]
    "Meter",
    __config__=ConfigDict(frozen=True, use_enum_values=True),
    **MeterRegisterGetter.to_fields(),
)


class Meter(_MeterBase, RegisterMetadataMixin):  # type: ignore[misc,valid-type]
    """GivEnergy external meter measurement data (FC 0x04, device addresses 0x01–0x08)."""

    REGISTER_GETTER: ClassVar[type[RegisterGetter]] = MeterRegisterGetter

    @classmethod
    def from_register_cache(cls, register_cache) -> "Meter":
        """Construct a Meter from a RegisterCache."""
        return cls.model_validate(MeterRegisterGetter(register_cache).build())

    def is_valid(self) -> bool:
        """Try to detect if a meter exists based on its attributes."""
        return self.v_phase_1 not in (None, 0)  # type: ignore[attr-defined]


class MeterProductRegisterGetter(RegisterGetter):
    """Structured format for meter identification attributes (FC 0x16, device addresses 0x01–0x08)."""

    REGISTER_LUT = {
        # Meter Product Registers MR(60)–MR(68)
        # identifier=True: unit-identifying, so redact_serials() auto-discovers the group
        # (#235; was the hand-fixed #228/H2 gap). factory_code is a factory/model code,
        # shared across units, so deliberately not marked.
        "serial_number": Def(C.string, None, MR(60), MR(61), identifier=True),
        "factory_code": Def(C.string, None, MR(62), MR(63)),
        "meter_type": Def(C.uint16, None, MR(64)),
        "hardware_version": Def(C.uint16, None, MR(65)),
        "software_version": Def(C.uint16, None, MR(66)),
        "modbus_id": Def(C.uint16, None, MR(67)),
        "baud_rate": Def(C.uint16, None, MR(68)),
    }


_MeterProductBase = create_model(  # type: ignore[call-overload]
    "MeterProduct",
    __config__=ConfigDict(frozen=True, use_enum_values=True),
    **MeterProductRegisterGetter.to_fields(),
)


class MeterProduct(_MeterProductBase, RegisterMetadataMixin):  # type: ignore[misc,valid-type]
    """GivEnergy external meter identification data (FC 0x16, device addresses 0x01–0x08)."""

    REGISTER_GETTER: ClassVar[type[RegisterGetter]] = MeterProductRegisterGetter

    @classmethod
    def from_register_cache(cls, register_cache) -> "MeterProduct":
        """Construct a MeterProduct from a RegisterCache."""
        return cls.model_validate(MeterProductRegisterGetter(register_cache).build())

    def is_valid(self) -> bool:
        """Try to detect if a meter product record exists based on its attributes."""
        return bool(self.serial_number and self.serial_number.isalnum())  # type: ignore[attr-defined]
