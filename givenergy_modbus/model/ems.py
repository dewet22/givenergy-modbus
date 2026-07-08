"""GivEnergy EMS (Energy Management System) data model."""

from enum import IntEnum
from typing import ClassVar

from pydantic import ConfigDict, computed_field, create_model

from givenergy_modbus.client.commands import _EmsCommands
from givenergy_modbus.model.devices import InverterSummary
from givenergy_modbus.model.inverter import Status
from givenergy_modbus.model.meter import MeterStatus
from givenergy_modbus.model.register import HR, IR, RegisterGetter, RegisterMetadataMixin
from givenergy_modbus.model.register import Converter as C
from givenergy_modbus.model.register import RegisterDefinition as Def

# Maximum number of managed inverters an EMS firmware reports. The EMS
# register block at IR(2045+) packs status / power / SoC / temp / serial
# fields for slots 1..MAX_MANAGED_INVERTERS; slots beyond ``inverter_count``
# are unpopulated and skipped by ``Ems.managed_inverters``.
MAX_MANAGED_INVERTERS = 4


class EmsInverterStatus(IntEnum):
    """SUSPECTED labels for the EMS per-slot inverter status code (IR(2045), 3-bit).

    These are a best-effort interpretation, exposed via ``inverter_N_suspected_status``
    so the raw code (``inverter_N_status``, hex) becomes human-inspectable and users can
    confirm or correct it (#108). Only ``ABSENT`` (0) and ``ONLINE`` (2) are verified —
    against the committed EMS capture, where empty slots read 0 and present, idle
    inverters read 2. The other 3-bit codes (1, 3–7) have never been observed; they
    decode to ``None`` here rather than being guessed. If your inverter shows an
    unexpected suspected status (or ``None``), that feedback is exactly what closes #108.
    """

    ABSENT = 0
    ONLINE = 2


def _ems_inverter_suspected_status(code: int | None) -> "EmsInverterStatus | None":
    """Map a raw 3-bit EMS inverter status code to a SUSPECTED label, or None if unknown.

    Lenient by design: only verified codes (0, 2) resolve; unobserved codes return None
    rather than raising, so an unexpected firmware value can't break the whole decode.
    """
    if code is None:
        return None
    try:
        return EmsInverterStatus(code)
    except ValueError:
        return None


class EmsRegisterGetter(RegisterGetter):
    """Structured format for EMS plant-level attributes (device address 0x11)."""

    REGISTER_LUT = {
        #
        # Holding Registers 2040–2075 — Plant configuration
        #
        "plant_status": Def(C.uint16, Status, HR(2040)),
        "expected_inverter_count": Def(C.uint16, None, HR(2041)),
        "expected_meter_count": Def(C.uint16, None, HR(2042)),
        "expected_car_charger_count": Def(C.uint16, None, HR(2043)),
        "discharge_slot_1": Def(C.timeslot, None, HR(2044), HR(2045)),
        "discharge_target_1": Def(C.uint16, None, HR(2046)),
        "discharge_slot_2": Def(C.timeslot, None, HR(2047), HR(2048)),
        "discharge_target_2": Def(C.uint16, None, HR(2049)),
        "discharge_slot_3": Def(C.timeslot, None, HR(2050), HR(2051)),
        "discharge_target_3": Def(C.uint16, None, HR(2052)),
        "charge_slot_1": Def(C.timeslot, None, HR(2053), HR(2054)),
        "charge_target_1": Def(C.uint16, None, HR(2055)),
        "charge_slot_2": Def(C.timeslot, None, HR(2056), HR(2057)),
        "charge_target_2": Def(C.uint16, None, HR(2058)),
        "charge_slot_3": Def(C.timeslot, None, HR(2059), HR(2060)),
        "charge_target_3": Def(C.uint16, None, HR(2061)),
        "export_slot_1": Def(C.timeslot, None, HR(2062), HR(2063)),
        "export_target_1": Def(C.uint16, None, HR(2064)),
        "export_slot_2": Def(C.timeslot, None, HR(2065), HR(2066)),
        "export_target_2": Def(C.uint16, None, HR(2067)),
        "export_slot_3": Def(C.timeslot, None, HR(2068), HR(2069)),
        "export_target_3": Def(C.uint16, None, HR(2070)),
        "export_power_limit": Def(C.uint16, None, HR(2071)),
        "car_charge_mode": Def(C.uint16, None, HR(2072)),
        "car_charge_boost": Def(C.uint16, None, HR(2073)),
        "plant_charge_compensation": Def(C.uint16, None, HR(2074)),
        "plant_discharge_compensation": Def(C.uint16, None, HR(2075)),
        #
        # Input Registers 2040–2094 — Plant runtime data
        #
        "ems_status": Def(C.uint16, Status, IR(2040)),
        "meter_count": Def(C.uint16, None, IR(2041)),
        "meter_types": Def(C.uint16, None, IR(2042)),
        # IR(2043) packs 8 meter statuses as 2-bit fields, LSB-first (slot N occupies
        # bits [(2N-2):(2N-1)] counting from LSB). C.bitfield uses MSB-first indices
        # (0=bit15), so slot N maps to bitfield indices [16-2N : 17-2N].
        "meter_1_status": Def((C.bitfield, 14, 15), MeterStatus, IR(2043)),
        "meter_2_status": Def((C.bitfield, 12, 13), MeterStatus, IR(2043)),
        "meter_3_status": Def((C.bitfield, 10, 11), MeterStatus, IR(2043)),
        "meter_4_status": Def((C.bitfield, 8, 9), MeterStatus, IR(2043)),
        "meter_5_status": Def((C.bitfield, 6, 7), MeterStatus, IR(2043)),
        "meter_6_status": Def((C.bitfield, 4, 5), MeterStatus, IR(2043)),
        "meter_7_status": Def((C.bitfield, 2, 3), MeterStatus, IR(2043)),
        "meter_8_status": Def((C.bitfield, 0, 1), MeterStatus, IR(2043)),
        "inverter_count": Def(C.uint16, None, IR(2044)),
        # IR(2045) packs up to 4 inverter statuses as 3-bit fields, LSB-first (slot N
        # occupies bits [(3N-3):(3N-1)] from LSB). MSB-first indices: [16-3N : 18-3N].
        # The per-slot status CODE is exposed as a hex string (the house idiom for raw,
        # uninterpreted codes — cf. device_type_code / fault_code), NOT mapped through the
        # inverter Status enum: that enum's values don't match this field's encoding
        # (a present, idle inverter reads code 2 here, which Status would mislabel as
        # WARNING). The only values verified against the committed EMS capture are
        # 0 = empty slot and 2 = present/idle; the full code→meaning mapping isn't exposed
        # by the GivEnergy app (which abstracts the EMS to one PCS object) and remains
        # undocumented. Use `inverter_count` for how many inverters are present (#108).
        "inverter_1_status": Def((C.bitfield, 13, 15), (C.hex, 1), IR(2045)),
        "inverter_2_status": Def((C.bitfield, 10, 12), (C.hex, 1), IR(2045)),
        "inverter_3_status": Def((C.bitfield, 7, 9), (C.hex, 1), IR(2045)),
        "inverter_4_status": Def((C.bitfield, 4, 6), (C.hex, 1), IR(2045)),
        # SUSPECTED human-readable interpretation of the same per-slot code, for user
        # inspection/feedback (#108). Only 0=ABSENT and 2=ONLINE are verified; other
        # codes decode to None pending real-world confirmation. The raw code stays
        # authoritative on inverter_N_status above.
        "inverter_1_suspected_status": Def((C.bitfield, 13, 15), _ems_inverter_suspected_status, IR(2045)),
        "inverter_2_suspected_status": Def((C.bitfield, 10, 12), _ems_inverter_suspected_status, IR(2045)),
        "inverter_3_suspected_status": Def((C.bitfield, 7, 9), _ems_inverter_suspected_status, IR(2045)),
        "inverter_4_suspected_status": Def((C.bitfield, 4, 6), _ems_inverter_suspected_status, IR(2045)),
        "meter_1_power": Def(C.int16, None, IR(2046)),
        "meter_2_power": Def(C.int16, None, IR(2047)),
        "meter_3_power": Def(C.int16, None, IR(2048)),
        "meter_4_power": Def(C.int16, None, IR(2049)),
        "meter_5_power": Def(C.int16, None, IR(2050)),
        "meter_6_power": Def(C.int16, None, IR(2051)),
        "meter_7_power": Def(C.int16, None, IR(2052)),
        "meter_8_power": Def(C.int16, None, IR(2053)),
        "inverter_1_power": Def(C.int16, None, IR(2054)),
        "inverter_2_power": Def(C.int16, None, IR(2055)),
        "inverter_3_power": Def(C.int16, None, IR(2056)),
        "inverter_4_power": Def(C.int16, None, IR(2057)),
        "inverter_1_soc": Def(C.uint16, None, IR(2058)),
        "inverter_2_soc": Def(C.uint16, None, IR(2059)),
        "inverter_3_soc": Def(C.uint16, None, IR(2060)),
        "inverter_4_soc": Def(C.uint16, None, IR(2061)),
        "inverter_1_temp": Def(C.int16, C.deci, IR(2062), min=-60.0, max=150.0),
        "inverter_2_temp": Def(C.int16, C.deci, IR(2063), min=-60.0, max=150.0),
        "inverter_3_temp": Def(C.int16, C.deci, IR(2064), min=-60.0, max=150.0),
        "inverter_4_temp": Def(C.int16, C.deci, IR(2065), min=-60.0, max=150.0),
        "inverter_1_serial_number": Def(C.serial, None, IR(2066), IR(2067), IR(2068), IR(2069), IR(2070)),
        "inverter_2_serial_number": Def(C.serial, None, IR(2071), IR(2072), IR(2073), IR(2074), IR(2075)),
        "inverter_3_serial_number": Def(C.serial, None, IR(2076), IR(2077), IR(2078), IR(2079), IR(2080)),
        "inverter_4_serial_number": Def(C.serial, None, IR(2081), IR(2082), IR(2083), IR(2084), IR(2085)),
        "e_active_generation_total": Def(C.uint16, None, IR(18)),
        "calc_load_power": Def(C.uint16, None, IR(2086)),
        "measured_load_power": Def(C.uint16, None, IR(2087)),
        "total_generation_load_power": Def(C.uint16, None, IR(2088)),
        "grid_meter_power": Def(C.int16, None, IR(2089)),
        "total_battery_power": Def(C.int16, None, IR(2090)),
        "remaining_battery_wh": Def(C.uint16, None, IR(2091)),
        "other_battery_power": Def(C.int16, None, IR(2094)),
    }


_EmsBase = create_model(  # type: ignore[call-overload]
    "Ems",
    __config__=ConfigDict(frozen=True, use_enum_values=True),
    **EmsRegisterGetter.to_fields(),
)


class Ems(_EmsBase, _EmsCommands, RegisterMetadataMixin):  # type: ignore[misc,valid-type]
    """GivEnergy EMS plant-level data (device address 0x11).

    Composes the `_EmsCommands` mixin so EMS-targeted writes (`set_ems_plant`,
    `set_ems_charge_slot`, `set_export_slot`, etc.) are exposed as instance
    methods on the EMS object. `manifest.WRITE_SAFE_EMS` covers the EMS HR
    block (2040, 2044–2071); the inverter-level allowlist intentionally does
    not apply here — EMS is a peer device, not an inverter.
    """

    REGISTER_GETTER: ClassVar[type[RegisterGetter]] = EmsRegisterGetter

    @classmethod
    def from_register_cache(cls, register_cache) -> "Ems":
        """Construct an Ems from a RegisterCache."""
        return cls.model_validate(EmsRegisterGetter(register_cache).build())

    def is_valid(self) -> bool:
        """Try to detect if an EMS is present based on its attributes."""
        return self.ems_status is not None  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def plant_enabled(self) -> bool | None:
        """Whether plant-level EMS ("Flexi EMS") control is enabled.

        Boolean read-back of HR(2040), the register ``set_ems_plant()`` writes —
        so this reflects the master-enable toggle's on/off state, suitable for
        backing a switch entity. ``plant_status`` decodes the *same* register as
        a coarse :class:`Status` enum; this is the dedicated boolean view (any
        non-zero value = enabled). ``None`` if HR(2040) hasn't been read yet.
        """
        raw = self.plant_status  # type: ignore[attr-defined]
        return None if raw is None else bool(raw)

    @property
    def managed_inverters(self) -> list[InverterSummary]:
        """Return :class:`InverterSummary` for each non-empty managed-inverter slot.

        The EMS rollup at IR(2045+) carries status / power / SoC / temp
        / serial for up to :data:`MAX_MANAGED_INVERTERS` (4) slots. An
        empty slot is identified by a missing or whitespace-only serial
        number — mirroring the ``is_valid()`` pattern used for Meter
        and Battery elsewhere.

        Slots are returned in order (1..N), filtered to the populated
        ones. Per-slot serial presence is the authoritative signal of
        whether a slot is wired; ``inverter_count`` is not consulted,
        since the serial test catches the same case more directly and
        gracefully handles the (rare) firmware where ``inverter_count``
        disagrees with the per-slot data.
        """
        summaries: list[InverterSummary] = []
        for slot in range(1, MAX_MANAGED_INVERTERS + 1):
            raw_serial = getattr(self, f"inverter_{slot}_serial_number", None)
            if not raw_serial:
                continue
            # Strip padding before storing — the EMS pads short / empty slots with
            # null bytes and spaces, and the *stored* value will later be compared
            # against directly-reported inverter serials during reconciliation.
            # Validity check and the stored value must use the same form.
            serial = raw_serial.strip("\x00 ")
            if not serial:
                continue
            summaries.append(
                InverterSummary(
                    serial_number=serial,
                    status=getattr(self, f"inverter_{slot}_status", None),
                    p_inverter_out=getattr(self, f"inverter_{slot}_power", None),
                    battery_soc=getattr(self, f"inverter_{slot}_soc", None),
                    t_inverter_heatsink=getattr(self, f"inverter_{slot}_temp", None),
                )
            )
        return summaries
