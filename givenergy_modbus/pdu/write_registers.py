import logging
from abc import ABC

from givenergy_modbus.codec import PayloadDecoder
from givenergy_modbus.exceptions import InvalidPduState
from givenergy_modbus.pdu.transparent import TransparentMessage, TransparentRequest, TransparentResponse

_logger = logging.getLogger(__name__)

# Canonical list of registers that are safe to write to.
WRITE_SAFE_REGISTERS = {
    20,  # ENABLE_CHARGE_TARGET
    27,  # BATTERY_POWER_MODE
    29,  # SOC_FORCE_ADJUST
    31,  # CHARGE_SLOT_2_START
    32,  # CHARGE_SLOT_2_END
    35,  # SYSTEM_TIME_YEAR
    36,  # SYSTEM_TIME_MONTH
    37,  # SYSTEM_TIME_DAY
    38,  # SYSTEM_TIME_HOUR
    39,  # SYSTEM_TIME_MINUTE
    40,  # SYSTEM_TIME_SECOND
    44,  # DISCHARGE_SLOT_2_START
    45,  # DISCHARGE_SLOT_2_END
    50,  # ACTIVE_POWER_RATE
    56,  # DISCHARGE_SLOT_1_START
    57,  # DISCHARGE_SLOT_1_END
    59,  # ENABLE_DISCHARGE
    94,  # CHARGE_SLOT_1_START
    95,  # CHARGE_SLOT_1_END
    96,  # ENABLE_CHARGE
    110,  # BATTERY_SOC_RESERVE
    111,  # BATTERY_CHARGE_LIMIT
    112,  # BATTERY_DISCHARGE_LIMIT
    114,  # BATTERY_DISCHARGE_MIN_POWER_RESERVE
    116,  # CHARGE_TARGET_SOC
    163,  # REBOOT
    246,  # CHARGE_SLOT_3_START
    247,  # CHARGE_SLOT_3_END
    249,  # CHARGE_SLOT_4_START
    250,  # CHARGE_SLOT_4_END
    252,  # CHARGE_SLOT_5_START
    253,  # CHARGE_SLOT_5_END
    255,  # CHARGE_SLOT_6_START
    256,  # CHARGE_SLOT_6_END
    258,  # CHARGE_SLOT_7_START
    259,  # CHARGE_SLOT_7_END
    261,  # CHARGE_SLOT_8_START
    262,  # CHARGE_SLOT_8_END
    264,  # CHARGE_SLOT_9_START
    265,  # CHARGE_SLOT_9_END
    267,  # CHARGE_SLOT_10_START
    268,  # CHARGE_SLOT_10_END
    276,  # DISCHARGE_SLOT_3_START
    277,  # DISCHARGE_SLOT_3_END
    279,  # DISCHARGE_SLOT_4_START
    280,  # DISCHARGE_SLOT_4_END
    282,  # DISCHARGE_SLOT_5_START
    283,  # DISCHARGE_SLOT_5_END
    285,  # DISCHARGE_SLOT_6_START
    286,  # DISCHARGE_SLOT_6_END
    288,  # DISCHARGE_SLOT_7_START
    289,  # DISCHARGE_SLOT_7_END
    291,  # DISCHARGE_SLOT_8_START
    292,  # DISCHARGE_SLOT_8_END
    294,  # DISCHARGE_SLOT_9_START
    295,  # DISCHARGE_SLOT_9_END
    297,  # DISCHARGE_SLOT_10_START
    298,  # DISCHARGE_SLOT_10_END
    166,  # ENABLE_RTC
    311,  # EXPORT_PRIORITY (AC-coupled; confirmed writable via hass#52 portal observations)
    313,  # BATTERY_CHARGE_LIMIT_AC
    314,  # BATTERY_DISCHARGE_LIMIT_AC
    317,  # ENABLE_EPS (AC-coupled; confirmed writable via hass#52 portal observations)
    318,  # BATTERY_PAUSE_MODE
    319,  # BATTERY_PAUSE_SLOT_START
    320,  # BATTERY_PAUSE_SLOT_END
    1112,  # AC_CHARGE_ENABLE
    1122,  # FORCE_DISCHARGE_ENABLE
    1123,  # FORCE_CHARGE_ENABLE
    2040,  # EMS_PLANT_ENABLE
    # EMS plant-level scheduling (HR 2044-2071). Slot start/end pairs, per-slot SoC
    # targets, and export power limit. Decoded in model/ems.py; written via the
    # set_ems_* commands. See givenergy-modbus#130.
    2044,  # EMS_DISCHARGE_SLOT_1_START
    2045,  # EMS_DISCHARGE_SLOT_1_END
    2046,  # EMS_DISCHARGE_TARGET_SOC_1
    2047,  # EMS_DISCHARGE_SLOT_2_START
    2048,  # EMS_DISCHARGE_SLOT_2_END
    2049,  # EMS_DISCHARGE_TARGET_SOC_2
    2050,  # EMS_DISCHARGE_SLOT_3_START
    2051,  # EMS_DISCHARGE_SLOT_3_END
    2052,  # EMS_DISCHARGE_TARGET_SOC_3
    2053,  # EMS_CHARGE_SLOT_1_START
    2054,  # EMS_CHARGE_SLOT_1_END
    2055,  # EMS_CHARGE_TARGET_SOC_1
    2056,  # EMS_CHARGE_SLOT_2_START
    2057,  # EMS_CHARGE_SLOT_2_END
    2058,  # EMS_CHARGE_TARGET_SOC_2
    2059,  # EMS_CHARGE_SLOT_3_START
    2060,  # EMS_CHARGE_SLOT_3_END
    2061,  # EMS_CHARGE_TARGET_SOC_3
    2062,  # EXPORT_SLOT_1_START
    2063,  # EXPORT_SLOT_1_END
    2064,  # EMS_EXPORT_TARGET_SOC_1
    2065,  # EXPORT_SLOT_2_START
    2066,  # EXPORT_SLOT_2_END
    2067,  # EMS_EXPORT_TARGET_SOC_2
    2068,  # EXPORT_SLOT_3_START
    2069,  # EXPORT_SLOT_3_END
    2070,  # EMS_EXPORT_TARGET_SOC_3
    2071,  # EMS_EXPORT_POWER_LIMIT
    # ------------------------------------------------------------------------
    # App-confirmed writable registers. Source: GivEnergy Android app "Direct
    # Control" → Control tab (2026-06-02), the writable-register surface GE
    # exposes to end users now that the cloud portal is being retired. The app
    # listing each of these as a user-editable control is authoritative evidence
    # they are safe to write. See givenergy-modbus#48.
    104,  # ENABLE_BATTERY_SELF_HEATING — hardware/batch-gated: write may be rejected per-unit
    172,  # ENABLE_MANUAL_BATTERY_HEATER — likely hardware-gated like 104
    199,  # ENABLE_INVERTER_PARALLEL_MODE (was mis-modelled as self-consumption logic)
    299,  # DISCHARGE_TARGET_SOC_10 (app: "DC Discharge 10 Lower SOC % Limit")
    331,  # FORCE_OFF_GRID — non-damaging, but a SUSTAINED islanding state (not a
    #        momentary reboot): a stuck write leaves a site off-grid with no
    #        auto-recovery. Bounded boolean; admit, but treat with care at call sites.
    # SMART_LOAD_SLOT_1..10 start/end (bounded timeslot values, same class as the
    # charge/discharge slots). app: "Smart Load Start/End Time 1..10".
    554,  # SMART_LOAD_SLOT_1_START
    555,  # SMART_LOAD_SLOT_1_END
    556,  # SMART_LOAD_SLOT_2_START
    557,  # SMART_LOAD_SLOT_2_END
    558,  # SMART_LOAD_SLOT_3_START
    559,  # SMART_LOAD_SLOT_3_END
    560,  # SMART_LOAD_SLOT_4_START
    561,  # SMART_LOAD_SLOT_4_END
    562,  # SMART_LOAD_SLOT_5_START
    563,  # SMART_LOAD_SLOT_5_END
    564,  # SMART_LOAD_SLOT_6_START
    565,  # SMART_LOAD_SLOT_6_END
    566,  # SMART_LOAD_SLOT_7_START
    567,  # SMART_LOAD_SLOT_7_END
    568,  # SMART_LOAD_SLOT_8_START
    569,  # SMART_LOAD_SLOT_8_END
    570,  # SMART_LOAD_SLOT_9_START
    571,  # SMART_LOAD_SLOT_9_END
    572,  # SMART_LOAD_SLOT_10_START
    573,  # SMART_LOAD_SLOT_10_END
    1005,  # REAL_TIME_CONTROL (three-phase mirror of HR166)
    1078,  # BATTERY_RESERVE_PERCENT (app: "Battery Reserve %")
    1108,  # DISCHARGE_POWER_RATE (three-phase)
    1109,  # DISCHARGE_DOWN_TO_PERCENT (three-phase)
    1110,  # CHARGE_POWER_RATE (three-phase)
    1111,  # CHARGE_UP_TO_PERCENT (three-phase)
    1113,  # AC_CHARGE_1_START (three-phase)
    1114,  # AC_CHARGE_1_END (three-phase)
    1115,  # AC_CHARGE_2_START (three-phase)
    1116,  # AC_CHARGE_2_END (three-phase)
    1118,  # DC_DISCHARGE_1_START (three-phase)
    1119,  # DC_DISCHARGE_1_END (three-phase)
    1120,  # DC_DISCHARGE_2_START (three-phase)
    1121,  # DC_DISCHARGE_2_END (three-phase)
    5010,  # RESTART_HARDWARE — disruptive but non-damaging, same class as 163 REBOOT
    5014,  # ENABLE_CALCULATED_LOAD
    # Held back (app-writable but not admitted yet):
    #  - HR479 "DC Wind CVT Voltage" is a raw voltage setpoint (unbounded 16-bit)
    #    with no range guard or set_* wrapper; admit only with a validating command.
}


class WriteHoldingRegister(TransparentMessage, ABC):
    """Request & Response PDUs for function #6/Write Holding Register."""

    transparent_function_code = 6

    register: int
    value: int

    def __init__(self, register: int, value: int, *args, **kwargs):
        if len(args) == 2:
            kwargs["register"] = args[0]
            kwargs["value"] = args[1]
        # WriteHoldingRegister defaults to 0x11 (the inverter's setup address) rather than the
        # 0x32 inherited from TransparentMessage. Only fill the default if neither alias was
        # supplied; the base __init__ handles slave_address→device_address mapping and warning.
        if "device_address" not in kwargs and "slave_address" not in kwargs:
            kwargs["device_address"] = 0x11
        super().__init__(**kwargs)
        if not isinstance(register, int):
            raise ValueError(f"Register type {type(register)} is unacceptable")
        self.register = register
        if not isinstance(value, int):
            raise ValueError(f"Register value {type(value)} is unacceptable")
        self.value = value

    def __str__(self) -> str:
        if self.register is not None and self.value is not None:
            return (
                f"{self.function_code}:{self.transparent_function_code}/{self.__class__.__name__}"
                f"({'ERROR ' if self.error else ''}{self.register} -> "
                f"{self.value}/0x{self.value:04x})"
            )
        else:
            return super().__str__()

    def __eq__(self, o: object) -> bool:
        return (
            isinstance(o, type(self))
            and self.has_same_shape(o)
            and o.register == self.register
            and o.value == self.value
            and o.error == self.error
        )

    def _encode_function_data(self):
        super()._encode_function_data()
        self._builder.add_16bit_uint(self.register)
        self._builder.add_16bit_uint(self.value)
        self._update_check_code()

    @classmethod
    def decode_transparent_function(cls, decoder: PayloadDecoder, **attrs) -> "WriteHoldingRegister":
        attrs["register"] = decoder.decode_16bit_uint()
        attrs["value"] = decoder.decode_16bit_uint()
        attrs["check"] = decoder.decode_16bit_uint()
        return cls(**attrs)

    def _extra_shape_hash_keys(self) -> tuple:
        return super()._extra_shape_hash_keys() + (self.register,)

    def ensure_valid_state(self):
        """Sanity check our internal state."""
        super().ensure_valid_state()
        if self.register is None:
            raise InvalidPduState("Register must be set", self)
        if self.value is None:
            raise InvalidPduState("Register value must be set", self)
        elif self.value < 0 or self.value > 0xFFFF:
            raise InvalidPduState(f"Value {self.value}/0x{self.value:04x} must be an unsigned 16-bit int", self)


class WriteHoldingRegisterRequest(WriteHoldingRegister, TransparentRequest):
    """Concrete PDU implementation for handling function #6/Write Holding Register request messages."""

    def ensure_valid_state(self):
        """Sanity check our internal state."""
        super().ensure_valid_state()
        if self.register not in WRITE_SAFE_REGISTERS:
            raise InvalidPduState(f"HR({self.register}) is not safe to write to", self)

    def expected_response(self):
        return WriteHoldingRegisterResponse(
            register=self.register, value=self.value, device_address=self.device_address
        )


class WriteHoldingRegisterResponse(WriteHoldingRegister, TransparentResponse):
    """Concrete PDU implementation for handling function #6/Write Holding Register response messages."""

    def ensure_valid_state(self):
        """Sanity check our internal state."""
        super().ensure_valid_state()
        if self.register not in WRITE_SAFE_REGISTERS and not self.error:
            _logger.warning(f"{self} is not safe for writing")


__all__ = ()
