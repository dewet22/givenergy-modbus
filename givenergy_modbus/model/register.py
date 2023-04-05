import logging
from datetime import time
from enum import Enum, auto, unique
from typing import Any, Callable, Optional

from givenergy_modbus.exceptions import ExceptionBase

_logger = logging.getLogger(__name__)


class RegisterError(ExceptionBase):
    """Base for register errors."""


class RegisterValueError(RegisterError):
    """Raised when a register value cannot be parsed/converted based on the register type definition."""

    def __init__(self, register: 'Register', val: int, e: ValueError):
        self.register = register
        self.val = val
        super().__init__(f'{str(register)}/{register.name}:{e}:0x{val:04x}')


class RegisterNotSane(RegisterError):
    """Raised when a register value is likely corrupt due to being outside the realm of physical possibility."""

    def __init__(self, register: 'Register', val: int):
        self.register = register
        self.val = val
        super().__init__(f'{str(register)}/{register.name}:{register.repr(val)}/0x{val:04x}')


class DataType(Enum):
    """Type of data register represents. Encoding is always big-endian."""

    BOOL = auto()
    BITFIELD = auto()
    HEX = auto()
    UINT8 = auto()
    DUINT8 = auto()  # double-uint8
    UINT16 = auto()
    INT16 = auto()
    UINT32_HIGH = auto()  # higher (MSB) address half
    UINT32_LOW = auto()  # lower (LSB) address half
    ASCII = auto()  # 2 ASCII characters
    TIME = auto()  # BCD-encoded time. 430 = 04:30
    POWER_FACTOR = auto()  # zero point at 10^4, scale factor 10^4

    def convert(self, value: int, scaling: int) -> Any:  # noqa: C901
        """Convert `val` to its true value as determined by the type and scaling definitions."""
        if self == self.UINT32_HIGH:
            # shift MSB half of the 32-bit int left
            if scaling != 1:
                return (value << 16) / scaling
            return value << 16

        if self == self.INT16:
            # Subtract 2^n if bit n-1 is set:
            if value & (1 << (16 - 1)):
                value -= 1 << 16
            if scaling != 1:
                return value / scaling
            return value

        if self == self.BOOL:
            return value != 0

        if self == self.TIME:
            # Convert a BCD-encoded int into datetime.time."""
            if value < 0:
                raise ValueError(value)
            hour = int(f'{value:04}'[:2])
            minute = int(f'{value:04}'[2:])
            if hour > 24 or minute > 60:
                raise ValueError(f'{value:04}')
            if hour == 24:
                hour = 0
            if minute == 60:
                minute = 0
            return time(hour, minute)

        if self == self.ASCII:
            return value.to_bytes(2, byteorder='big').decode(encoding='latin1')

        if self == self.UINT8:
            return value & 0xFF

        if self == self.DUINT8:
            return (value >> 8), (value & 0xFF)

        if self == self.POWER_FACTOR:
            return (value - 10_000) / 10_000

        if self == self.BITFIELD:
            return value  # scaling makes no sense

        if self == self.HEX:
            return f'{value:04x}'  # scaling makes no sense

        if scaling != 1:
            return value / scaling
        return value

    def repr(self, raw_val: Any, scaling: int, unit: str = '') -> str:
        """Return user-friendly representation of scaled `val` as appropriate for the data type."""
        v = self.convert(raw_val, scaling)

        if self == self.TIME:
            # Convert a BCD-encoded int into datetime.time."""
            return v.strftime('%H:%M')

        if self == self.DUINT8:
            return f'{v[0]}, {v[1]}'

        if self == self.BITFIELD:
            return ' '.join([f'{int(n, 16):04b}' for n in list(f'{v:04x}')])

        if self == self.HEX:
            return f'0x{raw_val:04x}'

        if isinstance(v, float):
            return f'{v:0.2f}{unit}'

        return f'{v}{unit}'


class ScalingFactor(Enum):
    """Scaling factor needs to be applied to a raw register value.

    Specified as a divisor instead, to improve rounding precision in python.
    """

    UNITY = 1
    DECI = 10
    CENTI = 100
    MILLI = 1000


class Unit(str, Enum):
    """Measurement unit for the register value."""

    sanity_check: Callable

    NONE = ''
    CHARGE_AH = 'Ah'
    CURRENT_A = 'A', lambda x: abs(x) < 200
    CURRENT_MA = 'mA', lambda x: abs(x) < 2000
    ENERGY_KWH = 'kWh', lambda x: x >= 0
    FREQUENCY_HZ = 'Hz', lambda x: 0 <= x < 100
    PERCENT = '%', lambda x: 0 <= x < 256
    POWER_KW = 'kW', lambda x: abs(x) < 20
    POWER_VA = 'VA', lambda x: abs(x) < 20000
    POWER_W = 'W', lambda x: abs(x) < 20000
    TEMPERATURE_C = '°C', lambda x: abs(x) < 200
    TIME_M = 'min'
    TIME_MS = 'ms'
    TIME_S = 'sec'
    VOLTAGE_V = 'V', lambda x: abs(x) < 2000

    def __new__(cls, value: int, sanity_check: Callable[[float], bool] = lambda x: True):
        """Allows indexing by register index."""
        obj = str.__new__(cls, str(value))
        obj._value_ = value
        setattr(obj, 'sanity_check', sanity_check)  # the way to make mypy happy
        return obj


@unique
class Register(str, Enum):
    """Mixin to help easier access to register bank structures."""

    data_type: DataType
    scaling_factor: ScalingFactor
    physical_unit: Unit
    write_safe: bool

    def __new__(cls, value: int, data=None):
        """Allows indexing by register index."""
        if data is None:
            data = {}
        obj = str.__new__(cls, f'{cls.__name__}({value})')
        obj._value_ = value
        obj.data_type = data.get('type', DataType.UINT16)
        obj.scaling_factor = data.get('scaling', ScalingFactor.UNITY)
        obj.physical_unit = data.get('unit', Unit.NONE)
        obj.write_safe = data.get('write_safe', False)
        return obj

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.value})'

    def __repr__(self) -> str:
        return self.__str__()

    @classmethod
    def _missing_(cls, value: object) -> Optional[Enum]:
        if isinstance(value, str):
            return cls._member_map_.get(value, None)
        return cls._missing_(value)

    def convert(self, raw_val: int):
        """Convert val to its true representation as determined by the register type."""
        try:
            val = self.data_type.convert(raw_val, self.scaling_factor.value)
        except ValueError as e:
            raise RegisterValueError(self, raw_val, e)
        if not self.physical_unit.sanity_check(val):
            raise RegisterNotSane(self, raw_val)
        return val

    def repr(self, raw_val):
        """Convert val to its true human-readable representation as determined by the register type."""
        return self.data_type.repr(raw_val, self.scaling_factor.value, self.physical_unit.value)


T_ASCII = DataType.ASCII
T_BITFIELD = DataType.BITFIELD
T_BOOL = DataType.BOOL
T_BYTE = DataType.UINT8
T_DOUBLE_BYTE = DataType.DUINT8
T_HEX = DataType.HEX
T_INT = DataType.INT16
T_POWER_FACTOR = DataType.POWER_FACTOR
T_QUAD_H = DataType.UINT32_HIGH
T_QUAD_L = DataType.UINT32_LOW
T_TIME = DataType.TIME

U_AMP = Unit.CURRENT_A
U_AMPERE_HOUR = Unit.CHARGE_AH
U_DEG_C = Unit.TEMPERATURE_C
U_HZ = Unit.FREQUENCY_HZ
U_KWH = Unit.ENERGY_KWH
U_MILLIAMP = Unit.CURRENT_MA
U_MILLISECONDS = Unit.TIME_MS
U_MINUTES = Unit.TIME_M
U_PERCENT = Unit.PERCENT
U_SECONDS = Unit.TIME_S
U_VA = Unit.POWER_VA
U_VOLT = Unit.VOLTAGE_V
U_WATT = Unit.POWER_W

S_1 = ScalingFactor.UNITY
S_10 = ScalingFactor.DECI
S_100 = ScalingFactor.CENTI
S_1000 = ScalingFactor.MILLI


class HoldingRegister(Register):
    """Holding Register definitions."""

    DEVICE_TYPE_CODE = (0, {'type': T_HEX})  # 0x[01235]xxx where 2=Inv?, 5==EMS
    INVERTER_MODULE_H = (1, {'type': T_QUAD_H})
    INVERTER_MODULE_L = (2, {'type': T_QUAD_L})
    NUM_MPPT_AND_NUM_PHASES = (3, {'type': T_DOUBLE_BYTE})  # number of MPPTs and phases
    HOLDING_REG004 = 4
    HOLDING_REG005 = 5
    HOLDING_REG006 = 6
    ENABLE_AMMETER = 7, {'type': T_BOOL}
    INVERTER_BATTERY_SERIAL_NUMBER_1_2 = (8, {'type': T_ASCII})
    INVERTER_BATTERY_SERIAL_NUMBER_3_4 = (9, {'type': T_ASCII})
    INVERTER_BATTERY_SERIAL_NUMBER_5_6 = (10, {'type': T_ASCII})
    INVERTER_BATTERY_SERIAL_NUMBER_7_8 = (11, {'type': T_ASCII})
    INVERTER_BATTERY_SERIAL_NUMBER_9_10 = (12, {'type': T_ASCII})
    INVERTER_SERIAL_NUMBER_1_2 = (13, {'type': T_ASCII})
    INVERTER_SERIAL_NUMBER_3_4 = (14, {'type': T_ASCII})
    INVERTER_SERIAL_NUMBER_5_6 = (15, {'type': T_ASCII})
    INVERTER_SERIAL_NUMBER_7_8 = (16, {'type': T_ASCII})
    INVERTER_SERIAL_NUMBER_9_10 = (17, {'type': T_ASCII})
    INVERTER_BATTERY_BMS_FIRMWARE_VERSION = 18
    DSP_FIRMWARE_VERSION = 19
    ENABLE_CHARGE_TARGET = (20, {'type': T_BOOL, 'write_safe': True})
    ARM_FIRMWARE_VERSION = 21
    USB_DEVICE_INSERTED = 22  # (0:none, 1:wifi, 2:disk)
    SELECT_ARM_CHIP = (23, {'type': T_BOOL})  # False: DSP selected
    VARIABLE_ADDRESS = 24
    VARIABLE_VALUE = (25, {'type': T_INT})
    GRID_PORT_MAX_POWER_OUTPUT = (26, {'unit': U_WATT})  # Export limit
    BATTERY_POWER_MODE = (27, {'write_safe': True})  # 0:export/max 1:demand/self-consumption
    ENABLE_60HZ_FREQ_MODE = (28, {'type': T_BOOL})  # 0:50hz
    # battery calibration stages (0:off  1:start/discharge  2:set lower limit  3:charge
    # 4:set upper limit  5:balance  6:set full capacity  7:finish)
    SOC_FORCE_ADJUST = 29
    INVERTER_MODBUS_ADDRESS = (30, {'type': T_BYTE})  # default 0x11
    CHARGE_SLOT_2_START = (31, {'type': T_TIME, 'write_safe': True})
    CHARGE_SLOT_2_END = (32, {'type': T_TIME, 'write_safe': True})
    USER_CODE = 33
    MODBUS_VERSION = (34, {'scaling': S_100})  # inverter:1.40 EMS:3.40
    SYSTEM_TIME_YEAR = (35, {'write_safe': True})
    SYSTEM_TIME_MONTH = (36, {'write_safe': True})
    SYSTEM_TIME_DAY = (37, {'write_safe': True})
    SYSTEM_TIME_HOUR = (38, {'write_safe': True})
    SYSTEM_TIME_MINUTE = (39, {'write_safe': True})
    SYSTEM_TIME_SECOND = (40, {'write_safe': True})
    ENABLE_DRM_RJ45_PORT = (41, {'type': T_BOOL})
    CT_ADJUST = (42, {'type': T_BITFIELD})  # bitfield? 1:negative/reverse polarity of blue CT clamp sensor
    CHARGE_AND_DISCHARGE_SOC = (43, {'type': T_DOUBLE_BYTE})
    DISCHARGE_SLOT_2_START = (44, {'type': T_TIME, 'write_safe': True})
    DISCHARGE_SLOT_2_END = (45, {'type': T_TIME, 'write_safe': True})
    BMS_CHIP_VERSION = 46  # different from 18, 101 seems the norm?
    METER_TYPE = 47  # 0:CT/EM418, 1:EM115
    REVERSE_115_METER_DIRECT = (48, {'type': T_BOOL})
    REVERSE_418_METER_DIRECT = (49, {'type': T_BOOL})
    # from beta remote control: Inverter Max Output Active Power Percent
    ACTIVE_POWER_RATE = (50, {'unit': U_PERCENT})
    REACTIVE_POWER_RATE = (51, {'unit': U_PERCENT})
    POWER_FACTOR = (52, {'type': T_POWER_FACTOR})
    INVERTER_STATE = (53, {'type': T_DOUBLE_BYTE})  # MSB:auto-restart state, LSB:on/off
    BATTERY_TYPE = 54  # 0:lead acid  1:lithium
    BATTERY_NOMINAL_CAPACITY = (55, {'unit': U_AMPERE_HOUR})
    DISCHARGE_SLOT_1_START = (56, {'type': T_TIME, 'write_safe': True})
    DISCHARGE_SLOT_1_END = (57, {'type': T_TIME, 'write_safe': True})
    ENABLE_AUTO_JUDGE_BATTERY_TYPE = (58, {'type': T_BOOL})
    ENABLE_DISCHARGE = (59, {'type': T_BOOL, 'write_safe': True})
    V_PV_INPUT_START = (60, {'scaling': S_10, 'unit': U_VOLT})
    INVERTER_START_TIME = (61, {'unit': U_SECONDS})
    INVERTER_RESTART_DELAY_TIME = (62, {'unit': U_SECONDS})
    V_AC_LOW_OUT = (63, {'scaling': S_10, 'unit': U_VOLT})
    V_AC_HIGH_OUT = (64, {'scaling': S_10, 'unit': U_VOLT})
    F_AC_LOW_OUT = (65, {'scaling': S_100, 'unit': U_HZ})
    F_AC_HIGH_OUT = (66, {'scaling': S_100, 'unit': U_HZ})
    V_AC_LOW_OUT_TIME = 67
    V_AC_HIGH_OUT_TIME = 68
    F_AC_LOW_OUT_TIME = 69
    F_AC_HIGH_OUT_TIME = 70
    V_AC_LOW_IN = (71, {'scaling': S_10, 'unit': U_VOLT})
    V_AC_HIGH_IN = (72, {'scaling': S_10, 'unit': U_VOLT})
    F_AC_LOW_IN = (73, {'scaling': S_100, 'unit': U_HZ})
    F_AC_HIGH_IN = (74, {'scaling': S_100, 'unit': U_HZ})
    V_AC_LOW_IN_TIME = 75
    V_AC_HIGH_IN_TIME = 76
    F_AC_LOW_IN_TIME = 77
    F_AC_HIGH_IN_TIME = 78
    V_AC_LOW_C = (79, {'scaling': S_10, 'unit': U_VOLT})
    V_AC_HIGH_C = (80, {'scaling': S_10, 'unit': U_VOLT})
    F_AC_LOW_C = (81, {'scaling': S_100, 'unit': U_HZ})
    F_AC_HIGH_C = (82, {'scaling': S_100, 'unit': U_HZ})
    V_10_MIN_PROTECTION = (83, {'scaling': S_10, 'unit': U_VOLT})
    ISO1 = 84
    ISO2 = 85
    # protection events: ground fault circuit interrupter, DC injection
    GFCI_1_I = (86, {'unit': U_MILLIAMP})
    GFCI_1_TIME = 87
    GFCI_2_I = (88, {'unit': U_MILLIAMP})
    GFCI_2_TIME = 89
    DCI_1_I = (90, {'unit': U_MILLIAMP})
    DCI_1_TIME = 91
    DCI_2_I = (92, {'unit': U_MILLIAMP})
    DCI_2_TIME = 93
    CHARGE_SLOT_1_START = (94, {'type': T_TIME, 'write_safe': True})
    CHARGE_SLOT_1_END = (95, {'type': T_TIME, 'write_safe': True})
    ENABLE_CHARGE = (96, {'type': T_BOOL, 'write_safe': True})
    V_BATTERY_UNDER_PROTECTION_LIMIT = (97, {'scaling': S_100, 'unit': U_VOLT})
    V_BATTERY_OVER_PROTECTION_LIMIT = (98, {'scaling': S_100, 'unit': U_VOLT})
    PV1_VOLTAGE_ADJUST = (99, {'scaling': S_10, 'unit': U_VOLT})
    PV2_VOLTAGE_ADJUST = (100, {'scaling': S_10, 'unit': U_VOLT})
    GRID_R_VOLTAGE_ADJUST = (101, {'scaling': S_10, 'unit': U_VOLT})
    GRID_S_VOLTAGE_ADJUST = (102, {'scaling': S_10, 'unit': U_VOLT})
    GRID_T_VOLTAGE_ADJUST = (103, {'scaling': S_10, 'unit': U_VOLT})
    GRID_POWER_ADJUST = (104, {'unit': U_WATT})
    BATTERY_VOLTAGE_ADJUST = (105, {'scaling': S_10, 'unit': U_VOLT})
    PV1_POWER_ADJUST = (106, {'unit': U_WATT})
    PV2_POWER_ADJUST = (107, {'unit': U_WATT})
    BATTERY_LOW_FORCE_CHARGE_TIME = (108, {'unit': U_MINUTES})
    ENABLE_BMS_READ = (109, {'type': T_BOOL})
    BATTERY_SOC_RESERVE = (110, {'unit': U_PERCENT, 'write_safe': True})
    # in beta dashboard: Battery Charge & Discharge Power, but rendered as W (50%=2600W), don't set above this?
    BATTERY_CHARGE_LIMIT = (111, {'unit': U_PERCENT, 'write_safe': True})
    BATTERY_DISCHARGE_LIMIT = (112, {'unit': U_PERCENT, 'write_safe': True})
    ENABLE_BUZZER = (113, {'type': T_BOOL})
    # in beta dashboard: Battery Cutoff % Limit
    BATTERY_DISCHARGE_MIN_POWER_RESERVE = (114, {'unit': U_PERCENT, 'write_safe': True})
    ISLAND_CHECK_CONTINUE = 115
    CHARGE_TARGET_SOC = (116, {'unit': U_PERCENT, 'write_safe': True})  # when ENABLE_CHARGE_TARGET is enabled
    CHARGE_SOC_STOP_2 = (117, {'unit': U_PERCENT})
    DISCHARGE_SOC_STOP_2 = (118, {'unit': U_PERCENT})
    CHARGE_SOC_STOP_1 = (119, {'unit': U_PERCENT})
    DISCHARGE_SOC_STOP_1 = (120, {'unit': U_PERCENT})
    LOCAL_COMMAND_TEST = (121, {'type': T_BOOL})
    POWER_FACTOR_FUNCTION_MODEL = 122
    FREQUENCY_LOAD_LIMIT_RATE = 123
    ENABLE_LOW_VOLTAGE_FAULT_RIDE_THROUGH = (124, {'type': T_BOOL})
    ENABLE_FREQUENCY_DERATING = (125, {'type': T_BOOL})
    ENABLE_ABOVE_6KW_SYSTEM = (126, {'type': T_BOOL})
    START_SYSTEM_AUTO_TEST = (127, {'type': T_BOOL})
    ENABLE_SPI = (128, {'type': T_BOOL})
    PF_CMD_MEMORY_STATE = (129, {'type': T_BOOL})
    # power factor limit line points: LP=load percentage, PF=power factor
    PF_LIMIT_LP1_LP = (130, {'unit': U_PERCENT})
    PF_LIMIT_LP1_PF = (131, {'type': T_POWER_FACTOR})
    PF_LIMIT_LP2_LP = (132, {'unit': U_PERCENT})
    PF_LIMIT_LP2_PF = (133, {'type': T_POWER_FACTOR})
    PF_LIMIT_LP3_LP = (134, {'unit': U_PERCENT})
    PF_LIMIT_LP3_PF = (135, {'type': T_POWER_FACTOR})
    PF_LIMIT_LP4_LP = (136, {'unit': U_PERCENT})
    PF_LIMIT_LP4_PF = (137, {'type': T_POWER_FACTOR})
    CEI021_V1S = 138
    CEI021_V2S = 139
    CEI021_V1L = 140
    CEI021_V2L = 141
    CEI021_Q_LOCK_IN_POWER = (142, {'unit': U_PERCENT})
    CEI021_Q_LOCK_OUT_POWER = (143, {'unit': U_PERCENT})
    CEI021_LOCK_IN_GRID_VOLTAGE = (144, {'scaling': S_10, 'unit': U_VOLT})
    CEI021_LOCK_OUT_GRID_VOLTAGE = (145, {'scaling': S_10, 'unit': U_VOLT})
    HOLDING_REG146 = 146
    HOLDING_REG147 = 147
    HOLDING_REG148 = 148
    HOLDING_REG149 = 149
    HOLDING_REG150 = 150
    HOLDING_REG151 = 151
    HOLDING_REG152 = 152
    HOLDING_REG153 = 153
    HOLDING_REG154 = 154
    HOLDING_REG155 = 155
    HOLDING_REG156 = 156
    HOLDING_REG157 = 157
    HOLDING_REG158 = 158
    HOLDING_REG159 = 159
    HOLDING_REG160 = 160
    HOLDING_REG161 = 161
    HOLDING_REG162 = 162
    INVERTER_REBOOT = (163, {'unit': U_PERCENT, 'write_safe': True})  # 100= reboot
    HOLDING_REG164 = 164
    HOLDING_REG165 = 165
    HOLDING_REG166 = 166
    HOLDING_REG167 = 167
    HOLDING_REG168 = 168
    HOLDING_REG169 = 169
    HOLDING_REG170 = 170
    HOLDING_REG171 = 171
    HOLDING_REG172 = 172
    HOLDING_REG173 = 173
    HOLDING_REG174 = 174
    HOLDING_REG175 = 175
    HOLDING_REG176 = 176
    HOLDING_REG177 = 177
    HOLDING_REG178 = 178
    HOLDING_REG179 = 179
    HOLDING_REG180 = 180
    HOLDING_REG181 = 181
    HOLDING_REG182 = 182
    HOLDING_REG183 = 183
    HOLDING_REG184 = 184
    HOLDING_REG185 = 185
    HOLDING_REG186 = 186
    HOLDING_REG187 = 187
    HOLDING_REG188 = 188
    HOLDING_REG189 = 189
    HOLDING_REG190 = 190
    HOLDING_REG191 = 191
    HOLDING_REG192 = 192
    HOLDING_REG193 = 193
    HOLDING_REG194 = 194
    HOLDING_REG195 = 195
    HOLDING_REG196 = 196
    HOLDING_REG197 = 197
    HOLDING_REG198 = 198
    HOLDING_REG199 = 199
    HOLDING_REG200 = 200
    HOLDING_REG201 = 201


class InputRegister(Register):
    """Definitions of Input Registers, shared by Inverter and Battery devices."""

    INVERTER_STATUS = 0  # 0:waiting 1:normal 2:warning 3:fault 4:flash/fw update
    V_PV1 = (1, {'scaling': S_10, 'unit': U_VOLT})
    V_PV2 = (2, {'scaling': S_10, 'unit': U_VOLT})
    V_P_BUS = (3, {'scaling': S_10, 'unit': U_VOLT})
    V_N_BUS = (4, {'scaling': S_10, 'unit': U_VOLT})
    V_AC1 = (5, {'scaling': S_10, 'unit': U_VOLT})
    E_BATTERY_THROUGHPUT_TOTAL_H = (6, {'type': T_QUAD_H, 'scaling': S_10, 'unit': U_KWH})
    E_BATTERY_THROUGHPUT_TOTAL_L = (7, {'type': T_QUAD_L, 'scaling': S_10, 'unit': U_KWH})
    I_PV1 = (8, {'scaling': S_10, 'unit': U_AMP})
    I_PV2 = (9, {'scaling': S_10, 'unit': U_AMP})
    I_AC1 = (10, {'scaling': S_100, 'unit': U_AMP})
    E_PV_TOTAL_H = (11, {'type': T_QUAD_H, 'scaling': S_10, 'unit': U_KWH})
    E_PV_TOTAL_L = (12, {'type': T_QUAD_L, 'scaling': S_10, 'unit': U_KWH})
    F_AC1 = (13, {'scaling': S_100, 'unit': U_HZ})
    CHARGE_STATUS = 14  # 2? 5-discharge?
    V_HIGHBRIGH_BUS = 15  # high voltage bus?
    PF_INVERTER_OUT = (16, {'type': T_POWER_FACTOR})  # should be F_? seems to be hovering between 4800-5400
    E_PV1_DAY = (17, {'scaling': S_10, 'unit': U_KWH})
    P_PV1 = (18, {'unit': U_WATT})
    E_PV2_DAY = (19, {'scaling': S_10, 'unit': U_KWH})
    P_PV2 = (20, {'unit': U_WATT})
    E_GRID_OUT_TOTAL_H = (21, {'type': T_QUAD_H, 'scaling': S_10, 'unit': U_KWH})
    E_GRID_OUT_TOTAL_L = (22, {'type': T_QUAD_L, 'scaling': S_10, 'unit': U_KWH})
    E_SOLAR_DIVERTER = (23, {'scaling': S_10, 'unit': U_KWH})
    P_INVERTER_OUT = (24, {'type': T_INT, 'unit': U_WATT})
    E_GRID_OUT_DAY = (25, {'scaling': S_10, 'unit': U_KWH})
    E_GRID_IN_DAY = (26, {'scaling': S_10, 'unit': U_KWH})
    E_INVERTER_IN_TOTAL_H = (27, {'type': T_QUAD_H, 'scaling': S_10, 'unit': U_KWH})
    E_INVERTER_IN_TOTAL_L = (28, {'type': T_QUAD_L, 'scaling': S_10, 'unit': U_KWH})
    E_DISCHARGE_YEAR = (29, {'scaling': S_10, 'unit': U_KWH})
    P_GRID_OUT = (30, {'type': T_INT, 'unit': U_WATT})
    P_EPS_BACKUP = (31, {'unit': U_WATT})
    E_GRID_IN_TOTAL_H = (32, {'type': T_QUAD_H, 'scaling': S_10, 'unit': U_KWH})
    E_GRID_IN_TOTAL_L = (33, {'type': T_QUAD_L, 'scaling': S_10, 'unit': U_KWH})
    INPUT_REG034 = 34
    E_INVERTER_IN_DAY = (35, {'scaling': S_10, 'unit': U_KWH})
    E_BATTERY_CHARGE_DAY = (36, {'scaling': S_10, 'unit': U_KWH})
    E_BATTERY_DISCHARGE_DAY = (37, {'scaling': S_10, 'unit': U_KWH})
    INVERTER_COUNTDOWN = (38, {'unit': U_SECONDS})
    FAULT_CODE_H = (39, {'type': T_BITFIELD})
    FAULT_CODE_L = (40, {'type': T_BITFIELD})
    TEMP_INVERTER_HEATSINK = (41, {'scaling': S_10, 'unit': U_DEG_C})
    P_LOAD_DEMAND = (42, {'unit': U_WATT})
    P_GRID_APPARENT = (43, {'unit': U_VA})
    E_INVERTER_OUT_DAY = (44, {'scaling': S_10, 'unit': U_KWH})
    E_INVERTER_OUT_TOTAL_H = (45, {'type': T_QUAD_H, 'scaling': S_10, 'unit': U_KWH})
    E_INVERTER_OUT_TOTAL_L = (46, {'type': T_QUAD_L, 'scaling': S_10, 'unit': U_KWH})
    WORK_TIME_TOTAL_H = (47, {'type': T_QUAD_H, 'unit': U_SECONDS})
    WORK_TIME_TOTAL_L = (48, {'type': T_QUAD_L, 'unit': U_SECONDS})
    SYSTEM_MODE = 49  # 0:offline, 1:grid-tied
    V_BATTERY = (50, {'scaling': S_100, 'unit': U_VOLT})
    I_BATTERY = (51, {'type': T_INT, 'scaling': S_100, 'unit': U_AMP})
    P_BATTERY = (52, {'type': T_INT, 'unit': U_WATT})
    V_EPS_BACKUP = (53, {'scaling': S_10, 'unit': U_VOLT})
    F_EPS_BACKUP = (54, {'scaling': S_100, 'unit': U_HZ})
    TEMP_CHARGER = (55, {'scaling': S_10, 'unit': U_DEG_C})
    TEMP_BATTERY = (56, {'scaling': S_10, 'unit': U_DEG_C})
    CHARGER_WARNING_CODE = 57
    I_GRID_PORT = (58, {'scaling': S_100, 'unit': U_AMP})
    BATTERY_PERCENT = (59, {'unit': U_PERCENT})

    # Used by Batteries / BMS
    V_CELL_01 = 60, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_02 = 61, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_03 = 62, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_04 = 63, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_05 = 64, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_06 = 65, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_07 = 66, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_08 = 67, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_09 = 68, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_10 = 69, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_11 = 70, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_12 = 71, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_13 = 72, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_14 = 73, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_15 = 74, {'scaling': S_1000, 'unit': U_VOLT}
    V_CELL_16 = 75, {'scaling': S_1000, 'unit': U_VOLT}
    TEMP_CELLS_1 = 76, {'scaling': S_10, 'unit': U_DEG_C}
    TEMP_CELLS_2 = 77, {'scaling': S_10, 'unit': U_DEG_C}
    TEMP_CELLS_3 = 78, {'scaling': S_10, 'unit': U_DEG_C}
    TEMP_CELLS_4 = 79, {'scaling': S_10, 'unit': U_DEG_C}
    V_CELLS_SUM = 80, {'scaling': S_1000, 'unit': U_VOLT}
    TEMP_BMS_MOS = 81, {'scaling': S_10, 'unit': U_DEG_C}
    V_BATTERY_OUT_H = 82, {'type': T_QUAD_H, 'scaling': S_1000, 'unit': U_VOLT}
    V_BATTERY_OUT_L = 83, {'type': T_QUAD_L, 'scaling': S_1000, 'unit': U_VOLT}
    FULL_CAPACITY_H = 84, {'type': T_QUAD_H, 'scaling': S_100, 'unit': U_AMPERE_HOUR}
    FULL_CAPACITY_L = 85, {'type': T_QUAD_L, 'scaling': S_100, 'unit': U_AMPERE_HOUR}
    DESIGN_CAPACITY_H = 86, {'type': T_QUAD_H, 'scaling': S_100, 'unit': U_AMPERE_HOUR}
    DESIGN_CAPACITY_L = 87, {'type': T_QUAD_L, 'scaling': S_100, 'unit': U_AMPERE_HOUR}
    REMAINING_CAPACITY_H = 88, {'type': T_QUAD_H, 'scaling': S_100, 'unit': U_AMPERE_HOUR}
    REMAINING_CAPACITY_L = 89, {'type': T_QUAD_L, 'scaling': S_100, 'unit': U_AMPERE_HOUR}
    STATUS_1_2 = 90, {'type': T_DOUBLE_BYTE}
    STATUS_3_4 = 91, {'type': T_DOUBLE_BYTE}
    STATUS_5_6 = 92, {'type': T_DOUBLE_BYTE}
    STATUS_7 = 93, {'type': T_DOUBLE_BYTE}
    WARNING_1_2 = 94, {'type': T_DOUBLE_BYTE}
    INPUT_REG095 = 95
    NUM_CYCLES = 96
    NUM_CELLS = 97
    BMS_FIRMWARE_VERSION = 98
    INPUT_REG099 = 99
    SOC = 100
    DESIGN_CAPACITY_2_H = 101, {'type': T_QUAD_H, 'scaling': S_100, 'unit': U_AMPERE_HOUR}
    DESIGN_CAPACITY_2_L = 102, {'type': T_QUAD_L, 'scaling': S_100, 'unit': U_AMPERE_HOUR}
    TEMP_MAX = 103, {'scaling': S_10, 'unit': U_DEG_C}
    TEMP_MIN = 104, {'scaling': S_10, 'unit': U_DEG_C}
    E_DISCHARGE_TOTAL = 105, {'scaling': S_10, 'unit': U_KWH}
    E_CHARGE_TOTAL = 106, {'scaling': S_10, 'unit': U_KWH}
    INPUT_REG107 = 107
    INPUT_REG108 = 108
    INPUT_REG109 = 109
    BATTERY_SERIAL_NUMBER_1_2 = 110, {'type': T_ASCII}
    BATTERY_SERIAL_NUMBER_3_4 = 111, {'type': T_ASCII}
    BATTERY_SERIAL_NUMBER_5_6 = 112, {'type': T_ASCII}
    BATTERY_SERIAL_NUMBER_7_8 = 113, {'type': T_ASCII}
    BATTERY_SERIAL_NUMBER_9_10 = 114, {'type': T_ASCII}
    USB_INSERTED = 115, {'type': T_BITFIELD}  # 0X08 = true; 0X00 = false
    INPUT_REG116 = 116
    INPUT_REG117 = 117
    INPUT_REG118 = 118
    INPUT_REG119 = 119

    INPUT_REG120 = 120
    INPUT_REG121 = 121
    INPUT_REG122 = 122
    INPUT_REG123 = 123
    INPUT_REG124 = 124
    INPUT_REG125 = 125
    INPUT_REG126 = 126
    INPUT_REG127 = 127
    INPUT_REG128 = 128
    INPUT_REG129 = 129
    INPUT_REG130 = 130
    INPUT_REG131 = 131
    INPUT_REG132 = 132
    INPUT_REG133 = 133
    INPUT_REG134 = 134
    INPUT_REG135 = 135
    INPUT_REG136 = 136
    INPUT_REG137 = 137
    INPUT_REG138 = 138
    INPUT_REG139 = 139
    INPUT_REG140 = 140
    INPUT_REG141 = 141
    INPUT_REG142 = 142
    INPUT_REG143 = 143
    INPUT_REG144 = 144
    INPUT_REG145 = 145
    INPUT_REG146 = 146
    INPUT_REG147 = 147
    INPUT_REG148 = 148
    INPUT_REG149 = 149
    INPUT_REG150 = 150
    INPUT_REG151 = 151
    INPUT_REG152 = 152
    INPUT_REG153 = 153
    INPUT_REG154 = 154
    INPUT_REG155 = 155
    INPUT_REG156 = 156
    INPUT_REG157 = 157
    INPUT_REG158 = 158
    INPUT_REG159 = 159
    INPUT_REG160 = 160
    INPUT_REG161 = 161
    INPUT_REG162 = 162
    INPUT_REG163 = 163
    INPUT_REG164 = 164
    INPUT_REG165 = 165
    INPUT_REG166 = 166
    INPUT_REG167 = 167
    INPUT_REG168 = 168
    INPUT_REG169 = 169
    INPUT_REG170 = 170
    INPUT_REG171 = 171
    INPUT_REG172 = 172
    INPUT_REG173 = 173
    INPUT_REG174 = 174
    INPUT_REG175 = 175
    INPUT_REG176 = 176
    INPUT_REG177 = 177
    INPUT_REG178 = 178
    INPUT_REG179 = 179

    E_BATTERY_DISCHARGE_TOTAL = (180, {'scaling': S_10, 'unit': U_KWH})
    E_BATTERY_CHARGE_TOTAL = (181, {'scaling': S_10, 'unit': U_KWH})
    E_BATTERY_DISCHARGE_DAY_2 = (182, {'scaling': S_10, 'unit': U_KWH})
    E_BATTERY_CHARGE_DAY_2 = (183, {'scaling': S_10, 'unit': U_KWH})
    INPUT_REG184 = 184
    INPUT_REG185 = 185
    INPUT_REG186 = 186
    INPUT_REG187 = 187
    INPUT_REG188 = 188
    INPUT_REG189 = 189
    INPUT_REG190 = 190
    INPUT_REG191 = 191
    INPUT_REG192 = 192
    INPUT_REG193 = 193
    INPUT_REG194 = 194
    INPUT_REG195 = 195
    INPUT_REG196 = 196
    INPUT_REG197 = 197
    INPUT_REG198 = 198
    INPUT_REG199 = 199
    INPUT_REG200 = 200
    REMOTE_BMS_RESTART = (201, {'type': T_BOOL})
    INPUT_REG202 = 202
    INPUT_REG203 = 203
    INPUT_REG204 = 204
    INPUT_REG205 = 205
    INPUT_REG206 = 206
    INPUT_REG207 = 207
    INPUT_REG208 = 208
    INPUT_REG209 = 209
    ISO_FAULT_VALUE = (210, {'scaling': S_10, 'unit': U_VOLT})
    GFCI_FAULT_VALUE = (211, {'unit': U_MILLIAMP})
    DCI_FAULT_VALUE = (212, {'scaling': S_100, 'unit': U_AMP})
    V_PV_FAULT_VALUE = (213, {'scaling': S_10, 'unit': U_VOLT})
    V_AC_FAULT_VALUE = (214, {'scaling': S_10, 'unit': U_VOLT})
    F_AC_FAULT_VALUE = (215, {'scaling': S_100, 'unit': U_HZ})
    TEMP_FAULT_VALUE = (216, {'scaling': S_10, 'unit': U_DEG_C})
    INPUT_REG217 = 217
    INPUT_REG218 = 218
    INPUT_REG219 = 219
    INPUT_REG220 = 220
    INPUT_REG221 = 221
    INPUT_REG222 = 222
    INPUT_REG223 = 223
    INPUT_REG224 = 224
    AUTO_TEST_PROCESS_OR_AUTO_TEST_STEP = (225, {'type': T_BITFIELD})
    AUTO_TEST_RESULT = 226
    AUTO_TEST_STOP_STEP = 227
    INPUT_REG228 = 228
    SAFETY_V_F_LIMIT = (229, {'scaling': S_10, 'unit': U_VOLT})
    SAFETY_TIME_LIMIT = (230, {'unit': U_MILLISECONDS})
    REAL_V_F_VALUE = (231, {'scaling': S_10, 'unit': U_VOLT})
    TEST_VALUE = (232, {'scaling': S_10, 'unit': U_VOLT})
    TEST_TREAT_VALUE = (233, {'scaling': S_10, 'unit': U_VOLT})
    TEST_TREAT_TIME = (234, {'unit': U_MILLISECONDS})
    INPUT_REG235 = 235
    INPUT_REG236 = 236
    INPUT_REG237 = 237
    INPUT_REG238 = 238
    INPUT_REG239 = 239
    # V_AC1_M3 = (240, {'scaling': S_10, 'unit': U_VOLT})
    # V_AC2_M3 = (241, {'scaling': S_10, 'unit': U_VOLT})
    # V_AC3_M3 = (242, {'scaling': S_10, 'unit': U_VOLT})
    # I_AC1_M3 = (243, {'scaling': S_100, 'unit': U_AMP})
    # I_AC2_M3 = (244, {'scaling': S_100, 'unit': U_AMP})
    # I_AC3_M3 = (245, {'scaling': S_100, 'unit': U_AMP})
    # GFCI_M3 = (246, {'scaling': S_10, 'unit': U_MILLIAMP})
    # INPUT_REG247 = 247
    # INPUT_REG248 = 248
    # INPUT_REG249 = 249
    # INPUT_REG250 = 250
    # INPUT_REG251 = 251
    # INPUT_REG252 = 252
    # INPUT_REG253 = 253
    # INPUT_REG254 = 254
    # INPUT_REG255 = 255
    # INPUT_REG256 = 256
    # INPUT_REG257 = 257
    # V_PV1_LIMIT = (258, {'type': T_INT, 'scaling': S_10, 'unit': U_VOLT})
    # V_PV2_LIMIT = (259, {'type': T_INT, 'scaling': S_10, 'unit': U_VOLT})
    # V_BUS_LIMIT = (260, {'type': T_INT, 'scaling': S_10, 'unit': U_VOLT})
    # V_N_BUS_LIMIT = (261, {'type': T_INT, 'scaling': S_10, 'unit': U_VOLT})
    # V_AC1_LIMIT = (262, {'type': T_INT, 'scaling': S_10, 'unit': U_VOLT})
    # V_AC2_LIMIT = (263, {'type': T_INT, 'scaling': S_10, 'unit': U_VOLT})
    # V_AC3_LIMIT = (264, {'type': T_INT, 'scaling': S_10, 'unit': U_VOLT})
    # I_PV1_LIMIT = (265, {'type': T_INT, 'unit': U_MILLIAMP})
    # I_PV2_LIMIT = (266, {'type': T_INT, 'unit': U_MILLIAMP})
    # I_AC1_LIMIT = (267, {'type': T_INT, 'unit': U_MILLIAMP})
    # I_AC2_LIMIT = (268, {'type': T_INT, 'unit': U_MILLIAMP})
    # I_AC3_LIMIT = (269, {'type': T_INT, 'unit': U_MILLIAMP})
    # P_AC1_LIMIT = (270, {'type': T_INT, 'scaling': S_10, 'unit': U_WATT})
    # P_AC2_LIMIT = (271, {'type': T_INT, 'scaling': S_10, 'unit': U_WATT})
    # P_AC3_LIMIT = (272, {'type': T_INT, 'scaling': S_10, 'unit': U_WATT})
    # DCI_LIMIT = (273, {'type': T_INT, 'scaling': S_10, 'unit': U_MILLIAMP})
    # GFCI_LIMIT = (274, {'type': T_INT, 'scaling': S_10, 'unit': U_MILLIAMP})
    # V_AC1_M3_LIMIT = (275, {'type': T_INT, 'scaling': S_10, 'unit': U_VOLT})
    # V_AC2_M3_LIMIT = (276, {'type': T_INT, 'scaling': S_10, 'unit': U_VOLT})
    # V_AC3_M3_LIMIT = (277, {'type': T_INT, 'scaling': S_10, 'unit': U_VOLT})
    # I_AC1_M3_LIMIT = (278, {'type': T_INT, 'scaling': S_100, 'unit': U_AMP})
    # I_AC2_M3_LIMIT = (279, {'type': T_INT, 'scaling': S_100, 'unit': U_AMP})
    # I_AC3_M3_LIMIT = (280, {'type': T_INT, 'scaling': S_100, 'unit': U_AMP})
    # GFCI_M3_LIMIT = (281, {'type': T_INT, 'scaling': S_10, 'unit': U_MILLIAMP})
    # V_BATTERY_LIMIT = (282, {'type': T_INT, 'scaling': S_100, 'unit': U_VOLT})
    # INPUT_REG283 = 283
    # INPUT_REG284 = 284
    # INPUT_REG285 = 285
    # INPUT_REG286 = 286
    # INPUT_REG287 = 287
    # INPUT_REG288 = 288
    # INPUT_REG289 = 289
    # INPUT_REG290 = 290
    # INPUT_REG291 = 291
    # INPUT_REG292 = 292
    # INPUT_REG293 = 293
    # INPUT_REG294 = 294
    # INPUT_REG295 = 295
    # INPUT_REG296 = 296
    # INPUT_REG297 = 297
    # INPUT_REG298 = 298
    # INPUT_REG299 = 299
    # INPUT_REG300 = 300
    # INPUT_REG301 = 301
