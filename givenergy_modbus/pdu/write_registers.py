import logging
from abc import ABC

from givenergy_modbus.codec import PayloadDecoder
from givenergy_modbus.exceptions import InvalidPduState
from givenergy_modbus.pdu.transparent import TransparentMessage, TransparentRequest, TransparentResponse

_logger = logging.getLogger(__name__)

# Canonical list of registers that are safe to write to.
WRITE_SAFE_REGISTERS = {
    # --- Charge/discharge enable and target ---
    20,  # enable AC charge upper % limit (app name; app: "Enable AC Charge Upper % Limit")
    96,  # enable charge
    59,  # enable discharge
    116,  # AC charge upper % limit (app: "AC Charge Upper % Limit")
    110,  # battery SOC reserve / discharge floor
    111,  # battery charge power limit
    112,  # battery discharge power limit
    114,  # battery discharge min power reserve
    # --- Charge slots 1–10 ---
    94,  # charge slot 1 start
    95,  # charge slot 1 end
    31,  # charge slot 2 start
    32,  # charge slot 2 end
    246,  # charge slot 3 start
    247,  # charge slot 3 end
    249,  # charge slot 4 start
    250,  # charge slot 4 end
    252,  # charge slot 5 start
    253,  # charge slot 5 end
    255,  # charge slot 6 start
    256,  # charge slot 6 end
    258,  # charge slot 7 start
    259,  # charge slot 7 end
    261,  # charge slot 8 start
    262,  # charge slot 8 end
    264,  # charge slot 9 start
    265,  # charge slot 9 end
    267,  # charge slot 10 start
    268,  # charge slot 10 end
    # --- Discharge slots 1–10 ---
    56,  # discharge slot 1 start
    57,  # discharge slot 1 end
    44,  # discharge slot 2 start
    45,  # discharge slot 2 end
    276,  # discharge slot 3 start
    277,  # discharge slot 3 end
    279,  # discharge slot 4 start
    280,  # discharge slot 4 end
    282,  # discharge slot 5 start
    283,  # discharge slot 5 end
    285,  # discharge slot 6 start
    286,  # discharge slot 6 end
    288,  # discharge slot 7 start
    289,  # discharge slot 7 end
    291,  # discharge slot 8 start
    292,  # discharge slot 8 end
    294,  # discharge slot 9 start
    295,  # discharge slot 9 end
    297,  # discharge slot 10 start
    298,  # discharge slot 10 end
    # --- Battery mode and scheduling ---
    27,  # enable eco mode (app: "Enable Eco Mode")
    29,  # SOC force-adjust
    50,  # active power rate
    163,  # restart inverter (app: "Restart Inverter")
    166,  # real-time control (app: "Real-Time Control")
    # --- System time ---
    35,  # system time: year
    36,  # system time: month
    37,  # system time: day
    38,  # system time: hour
    39,  # system time: minute
    40,  # system time: second
    # --- AC-coupled config (AC/HYBRID_GEN1 with AC config block) ---
    311,  # export power priority (app: "Export Power Priority"; confirmed via hass#52)
    313,  # inverter charge power percentage (app: "Inverter Charge Power Percentage")
    314,  # inverter discharge power percentage (app: "Inverter Discharge Power Percentage")
    317,  # enable EPS (app: "Enable EPS"; confirmed via hass#52)
    318,  # pause battery (app: "Pause Battery")
    319,  # pause battery start time
    320,  # pause battery end time
    # --- Three-phase ---
    1112,  # enable AC charge (three-phase)
    1122,  # enable force discharge (three-phase)
    1123,  # enable force charge (three-phase)
    # --- EMS plant-level scheduling (HR 2040–2071) ---
    # Slot start/end pairs, per-slot SoC targets, and export power limit.
    # Decoded in model/ems.py; written via the set_ems_* commands. See #130.
    2040,  # enable plant EMS control (app: "Enable Plant EMS Control")
    2044,  # EMS discharge slot 1 start
    2045,  # EMS discharge slot 1 end
    2046,  # EMS discharge SOC % limit 1
    2047,  # EMS discharge slot 2 start
    2048,  # EMS discharge slot 2 end
    2049,  # EMS discharge SOC % limit 2
    2050,  # EMS discharge slot 3 start
    2051,  # EMS discharge slot 3 end
    2052,  # EMS discharge SOC % limit 3
    2053,  # EMS charge slot 1 start
    2054,  # EMS charge slot 1 end
    2055,  # EMS charge SOC % limit 1
    2056,  # EMS charge slot 2 start
    2057,  # EMS charge slot 2 end
    2058,  # EMS charge SOC % limit 2
    2059,  # EMS charge slot 3 start
    2060,  # EMS charge slot 3 end
    2061,  # EMS charge SOC % limit 3
    2062,  # EMS export slot 1 start
    2063,  # EMS export slot 1 end
    2064,  # EMS export SOC % limit 1
    2065,  # EMS export slot 2 start
    2066,  # EMS export slot 2 end
    2067,  # EMS export SOC % limit 2
    2068,  # EMS export slot 3 start
    2069,  # EMS export slot 3 end
    2070,  # EMS export SOC % limit 3
    2071,  # EMS export power limit (installer/DNO — not user-writable via app)
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

# Installer-tier registers: grid-safety, factory-config, and destructive operations.
# Disjoint from WRITE_SAFE_REGISTERS — only accessible via Client.installer_command().
# Gate 1 (client): installer_command() validates against WRITE_SAFE_REGISTERS | INSTALLER_WRITE_REGISTERS.
# Gate 2 (PDU): ensure_valid_state() on an installer-flagged WriteHoldingRegisterRequest
#               checks this set instead of WRITE_SAFE_REGISTERS.
# Source: GivEnergy Android app 4.0.7 "Direct Control" installer-login register surface.
INSTALLER_WRITE_REGISTERS: frozenset[int] = frozenset(
    {
        # --- AC grid protection: voltage/frequency limits (two-level trip + hold) ---
        63,  # AC Undervoltage Limit 1
        64,  # AC Overvoltage Limit 1
        65,  # AC Underfrequency Limit 1
        66,  # AC Overfrequency Limit 1
        67,  # AC Undervoltage 1 Protection Time
        68,  # AC Overvoltage 1 Protection Time
        69,  # AC Underfrequency 1 Protection Time
        70,  # AC Overfrequency 1 Protection Time
        71,  # AC Undervoltage Limit 2
        72,  # AC Overvoltage Limit 2
        73,  # AC Underfrequency Limit 2
        74,  # AC Overfrequency Limit 2
        75,  # AC Undervoltage 2 Protection Time
        76,  # AC Overvoltage 2 Protection Time
        77,  # AC Underfrequency 2 Protection Time
        78,  # AC Overfrequency 2 Protection Time
        79,  # AC Undervoltage Limit
        80,  # AC Overvoltage Limit
        81,  # AC Underfrequency Limit
        82,  # AC Overfrequency Limit
        83,  # AC Voltage Protection 10 Minute Average
        # --- Grid import limits ---
        101,  # Grid Import Limit
        102,  # Grid Import Limit Enabled (boolean)
        115,  # Anti-Islanding Detection (boolean)
        # --- Battery commissioning ---
        174,  # Wake Battery
        201,  # Restart Battery
        308,  # Battery Nominal Power
        309,  # Battery Nominal Current
        310,  # Battery Max Charge % (app range 20–100)
        # --- Plant / inverter operating config ---
        300,  # Enable Plant Mode (boolean)
        302,  # Plant Meters
        303,  # Overfrequency Load Drop Recovery Delay
        305,  # MPPT Operating Mode
        306,  # Connection Loading Slope
        307,  # EPS Nominal Voltage
        312,  # Underfrequency Add Load Delay
        315,  # EN50549 Zero-Current Static Lower Voltage Limit
        316,  # EN50549 Zero-Current Static Upper Voltage Limit
        321,  # Overfrequency Derating Start Point
        322,  # Enable Tariff Pricing Battery Logic (boolean)
        323,  # Import Price Battery Discharge Threshold
        324,  # Import Price Battery Charge Threshold
        325,  # Export Price Battery Discharge Threshold
        326,  # Underfrequency Derating Start Point
        327,  # Underfrequency Loading Slope
        328,  # Overfrequency Derating Stop Point
        329,  # Enable BMS OCV Calibration (boolean)
        330,  # Gateway Power Off Setting
        332,  # Enable Micro Grid (boolean)
        347,  # Disable LEDs (boolean)
        348,  # LCD Screen Idle Timeout
        349,  # Lead Acid Battery Calibration Upper Limit
        350,  # Lead Acid Battery Calibration Lower Limit
        351,  # Inverter Operating Mode
        # --- EV charger ---
        333,  # EV Charger Enable (boolean)
        334,  # EV Charger Import Limit
        335,  # EV Charger Reconnection Wait Time
        336,  # EV Charger SOC Limit
        # --- Fan and gateway ---
        337,  # Enable Fan (boolean)
        338,  # Fan Speed
        339,  # Enable Gateway (boolean)
        340,  # BMS Communication Mode
        341,  # N-PE Relay Toggle
        342,  # AFCI Setting
        # --- Generator ---
        343,  # Enable Generator (boolean)
        344,  # Generator Start SOC (0–100 %)
        345,  # Generator Stop SOC (0–100 %)
        346,  # Generator Charge Power
        # --- Smart load non-slot controls ---
        540,  # Enable Smart Load (boolean)
        541,  # Smart Load Control SOC (app range 50–100 %)
        542,  # Enable General Load (boolean)
        543,  # General Load Control SOC (app range 50–100 %)
        544,  # Generator Control SOC (app range 10–90 %)
        545,  # Generator Voltage Min
        546,  # Generator Voltage Max
        547,  # Generator Frequency Min
        548,  # Generator Frequency Max
        552,  # Smart Load Export Power
        553,  # Smart Load Delay Time
        # --- Three-phase grid/power quality ---
        1048,  # Q Lock Out Power
        1063,  # Export Power Rate / backflow limit (three-phase; 0.1% of rated, 0~1000)
        1077,  # PV Input Mode
        1081,  # QU Curve Volt High Point 1
        1082,  # QU Curve Volt High Point 2
        1083,  # QU Curve Volt Low Point 1
        1084,  # QU Curve Volt Low Point 2
        1085,  # Voltage Reactive Power Percentage
        1086,  # QU Curve Maximum Inductive Reactive Power
        1087,  # QU Curve Maximum Capacitive Reactive Power
        1102,  # Export Limit (three-phase)
        1103,  # Enable Export Limit (three-phase; boolean)
        1125,  # Enable LoRa (three-phase)
        1126,  # Meter CT Direction
        1127,  # Load Shedding Voltage Upper Limit
        1128,  # Load Shedding Voltage Lower Limit
        1129,  # Load Shedding Minimum Active Power %
        1130,  # Import Limit (three-phase)
        1131,  # Enable Import Limit (three-phase; boolean)
        1144,  # Enable Meter Wiring Detection (boolean)
        1149,  # Meter Wiring Detection State
        1156,  # Safety Function Control Word
        1158,  # Active Power Per Thousand Ratio
        1159,  # High Active Power High Point
        1160,  # High Active Power Low Point
        1161,  # Low Active Power High Point
        1162,  # Low Active Power Low Point
        1163,  # Qp Lock In Voltage
        1164,  # Qp Lock Out Voltage
        1165,  # Minimum Power Factor Setting
        # --- Plant / dual-grid ---
        4001,  # Dual Grid Supply Operational Mode
        # --- Special commands (non-destructive) ---
        5002,  # Send Wake Up Signal
        5005,  # Enable PV Meter Preset
        5006,  # Enable AC Meter Preset
        5007,  # Enable N-PE
        5008,  # Enable CT Auto Configuration
        5009,  # Enable Auto Address Configuration
        5011,  # Grid Power Limit
        5012,  # AC Over Current Limit
        # --- Peak shaving / export-import control (EMS installer) ---
        20000,  # Enable Grid Export Limit
        20001,  # Grid Export Limit
        20002,  # Enable Peak Shaving
        20003,  # Peak Shaving Threshold
        20020,  # Enable Import Limit
        20021,  # Import Limit Threshold
        20050,  # Peak Shaving Power
        20051,  # Valley Filling Power
        # -----------------------------------------------------------------------
        # DESTRUCTIVE — these registers trigger irreversible actions.
        # The corresponding set_* helpers require confirm=True.
        # -----------------------------------------------------------------------
        162,  # Reset Energy Totals — clears all lifetime energy counters
        1016,  # Three Phase Factory Reset Without Meter Reset
        5003,  # Enable Black Start — activates EPS black-start mode
        5004,  # Restore Factory Defaults — wipes all installer config
    }
)


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
        # bool subclasses int, so it would pass the isinstance check below and silently write
        # 0/1 — a bool reaching a numeric register (e.g. ACTIVE_POWER_RATE) is a caller bug.
        # Boolean command helpers pass int(enabled) explicitly (audit L1).
        if isinstance(value, bool) or not isinstance(value, int):
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

    # Non-wire class-level default: installer=False is the normal path.
    # Only set as an instance attribute when True so that wire-decoded instances
    # (built via decode_transparent_function without the kwarg) leave installer
    # absent from __dict__, which keeps the existing __dict__ equality tests intact.
    installer: bool = False

    def __init__(self, register: int, value: int, installer: bool = False, **kwargs):
        super().__init__(register, value, **kwargs)
        if installer:
            self.installer = installer

    def ensure_valid_state(self):
        """Sanity check our internal state."""
        super().ensure_valid_state()
        if self.installer:
            if self.register not in INSTALLER_WRITE_REGISTERS:
                raise InvalidPduState(f"HR({self.register}) is not in the installer register set", self)
        elif self.register not in WRITE_SAFE_REGISTERS:
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
        known = WRITE_SAFE_REGISTERS | INSTALLER_WRITE_REGISTERS
        if self.register not in known and not self.error:
            _logger.warning(f"{self} is not safe for writing")


__all__ = ("INSTALLER_WRITE_REGISTERS",)
