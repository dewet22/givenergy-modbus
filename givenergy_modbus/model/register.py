# type: ignore  # shut up mypy, this whole file is just a minefield
import datetime
from enum import Enum, auto, unique
from typing import Any


class Type(Enum):
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
    PERCENT = auto()  # same as UINT16, but might be useful for rendering
    POWER_FACTOR = auto()  # zero point at 10^4, scale factor 10^4

    def convert(self, value: int, scaling: float) -> Any:
        """Convert `val` to its true value as determined by the type and scaling definitions."""
        if self == self.UINT32_HIGH:
            # shift MSB half of the 32-bit int left
            return (value << 16) * scaling

        if self == self.INT16:
            # Subtract 2^n if bit n-1 is set:
            if value & (1 << (16 - 1)):
                value -= 1 << 16
            return value * scaling

        if self == self.BOOL:  # TODO is this the correct assumption?
            return bool(value)

        if self == self.TIME:
            # Convert a BCD-encoded int into datetime.time."""
            return datetime.time(hour=int(f'{value:04}'[:2]), minute=int(f'{value:04}'[2:]))

        if self == self.ASCII:
            return value.to_bytes(2, byteorder='big').decode(encoding='ascii')

        if self == self.UINT8:
            return value & 0xFF

        if self == self.DUINT8:
            return (value >> 8), (value & 0xFF)

        if self == self.POWER_FACTOR:
            return (value - 10_000) / 10_000

        if self == self.BITFIELD:
            return value  # scaling makes no sense

        if self == self.HEX:
            return value  # scaling makes no sense

        return value * scaling

    def repr(self, value: Any, scaling: float, unit: str = '') -> str:
        """Return user-friendly representation of scaled `val` as appropriate for the data type."""
        v = self.convert(value, scaling)

        if unit:
            unit = f' {unit}'

        if self == self.TIME:
            # Convert a BCD-encoded int into datetime.time."""
            return v.strftime('%H:%M')

        if self == self.DUINT8:
            return f'{v[0]}, {v[1]}'

        if self == self.BITFIELD:
            return ' '.join([f'{int(n, 16):04b}' for n in list(f'{v:04x}')])

        if self == self.HEX:
            return f'0x{v:04x}'

        if isinstance(v, float):
            return f'{v:0.2f}{unit}'

        return f'{v}{unit}'


class Scaling(Enum):
    """What scaling factor needs to be applied to a register's value."""

    # KILO = 1000
    # HECTO = 100
    # DECA = 10
    UNIT = 1
    DECI = 0.1
    CENTI = 0.01
    MILLI = 0.001


class Unit(Enum):
    """Measurement unit for the register value."""

    NONE = ''
    ENERGY_KWH = 'kWh'
    POWER_W = 'W'
    POWER_KW = 'kW'
    POWER_VA = 'VA'
    FREQUENCY_HZ = 'Hz'
    VOLTAGE_V = 'V'
    CURRENT_A = 'A'
    CURRENT_MA = 'mA'
    TEMPERATURE_C = '°C'
    CHARGE_AH = 'Ah'
    TIME_MS = 'ms'
    TIME_S = 'sec'
    TIME_M = 'min'


@unique
class Register(str, Enum):
    """Mixin to help easier access to register bank structures."""

    def __new__(cls, value: int, data=None):
        """Allows indexing by register index."""
        if data is None:
            data = {}
        obj = str.__new__(cls, f'{cls}:{hex(value)}')
        obj._value_ = value
        obj.type = data.get('type', Type.UINT16)
        obj.scaling = data.get('scaling', Scaling.UNIT)
        obj.unit = data.get('unit', Unit.NONE)
        obj.description = data.get('description', None)
        obj.write_safe = data.get('write_safe', False)
        return obj

    def convert(self, val):
        """Convert val to its true representation as determined by the register type."""
        return self.type.convert(val, self.scaling.value)

    def repr(self, val):
        """Convert val to its true representation as determined by the register type."""
        return self.type.repr(val, self.scaling.value, self.unit.value)


class HoldingRegister(Register):
    """Holding Register definitions."""

    DEVICE_TYPE_CODE = (0, {'type': Type.HEX})  # 0x[01235]xxx where 2=Inv?,5==EMS
    INVERTER_MODULE_H = (1, {'type': Type.UINT32_HIGH})
    INVERTER_MODULE_L = (2, {'type': Type.UINT32_LOW})
    NUM_MPPT_AND_NUM_PHASES = (3, {'type': Type.DUINT8})  # number of MPPTs and phases
    REG004 = 4
    REG005 = 5
    REG006 = 6
    ENABLE_AMMETER = (7, {'type': Type.BOOL})
    BATTERY_SERIAL_NUMBER_1_2 = (8, {'type': Type.ASCII})
    BATTERY_SERIAL_NUMBER_3_4 = (9, {'type': Type.ASCII})
    BATTERY_SERIAL_NUMBER_5_6 = (10, {'type': Type.ASCII})
    BATTERY_SERIAL_NUMBER_7_8 = (11, {'type': Type.ASCII})
    BATTERY_SERIAL_NUMBER_9_10 = (12, {'type': Type.ASCII})
    INVERTER_SERIAL_NUMBER_1_2 = (13, {'type': Type.ASCII})
    INVERTER_SERIAL_NUMBER_3_4 = (14, {'type': Type.ASCII})
    INVERTER_SERIAL_NUMBER_5_6 = (15, {'type': Type.ASCII})
    INVERTER_SERIAL_NUMBER_7_8 = (16, {'type': Type.ASCII})
    INVERTER_SERIAL_NUMBER_9_10 = (17, {'type': Type.ASCII})
    BMS_FIRMWARE_VERSION = 18
    DSP_FIRMWARE_VERSION = 19
    ENABLE_CHARGE_TARGET = (20, {'type': Type.BOOL, 'write_safe': True})
    ARM_FIRMWARE_VERSION = 21
    USB_DEVICE_INSERTED = 22  # (0:none, 1:wifi, 2:disk)
    SELECT_ARM_CHIP = (23, {'type': Type.BOOL})  # False: DSP selected
    VARIABLE_ADDRESS = 24
    VARIABLE_VALUE = (25, {'type': Type.INT16})
    P_GRID_PORT_MAX_OUTPUT = (26, {'unit': Unit.POWER_W})  # Export limit
    BATTERY_POWER_MODE = (27, {'write_safe': True})  # 0:export/max 1:demand/self-consumption
    ENABLE_60HZ_FREQ_MODE = (28, {'type': Type.BOOL})  # 0:50hz
    # battery calibration stages (0:off  1:start/discharge  2:set lower limit  3:charge
    # 4:set upper limit  5:balance  6:set full capacity  7:finish)
    SOC_FORCE_ADJUST = 29
    INVERTER_MODBUS_ADDRESS = (30, {'type': Type.UINT8})  # default 0x11
    CHARGE_SLOT_2_START = (31, {'type': Type.TIME, 'write_safe': True})
    CHARGE_SLOT_2_END = (32, {'type': Type.TIME, 'write_safe': True})
    USER_CODE = 33
    MODBUS_VERSION = (34, {'scaling': Scaling.CENTI})  # inverter:1.40 EMS:3.40
    SYSTEM_TIME_YEAR = (35, {'write_safe': True})
    SYSTEM_TIME_MONTH = (36, {'write_safe': True})
    SYSTEM_TIME_DAY = (37, {'write_safe': True})
    SYSTEM_TIME_HOUR = (38, {'write_safe': True})
    SYSTEM_TIME_MINUTE = (39, {'write_safe': True})
    SYSTEM_TIME_SECOND = (40, {'write_safe': True})
    ENABLE_DRM_RJ45_PORT = (41, {'type': Type.BOOL})
    CT_ADJUST = (42, {'type': Type.BITFIELD})  # bitfield? 1:negative/reverse polarity of blue CT clamp sensor
    CHARGE_AND_DISCHARGE_SOC = (43, {'type': Type.DUINT8})
    DISCHARGE_SLOT_2_START = (44, {'type': Type.TIME, 'write_safe': True})
    DISCHARGE_SLOT_2_END = (45, {'type': Type.TIME, 'write_safe': True})
    BMS_CHIP_VERSION = 46  # different from 18, 101 seems the norm?
    METER_TYPE = 47  # 0:CT/EM418, 1:EM115
    REVERSE_115_METER_DIRECT = (48, {'type': Type.BOOL})
    REVERSE_418_METER_DIRECT = (49, {'type': Type.BOOL})
    # from beta remote control: Inverter Max Output Active Power Percent
    ACTIVE_POWER_RATE = (50, {'type': Type.PERCENT})
    REACTIVE_POWER_RATE = (51, {'type': Type.PERCENT})
    POWER_FACTOR = (52, {'type': Type.POWER_FACTOR})
    INVERTER_STATE = (53, {'type': Type.DUINT8})  # MSB:auto-restart state, LSB:on/off
    BATTERY_TYPE = 54  # 0:lead acid  1:lithium
    BATTERY_NOMINAL_CAPACITY = (55, {'unit': Unit.CHARGE_AH})
    DISCHARGE_SLOT_1_START = (56, {'type': Type.TIME, 'write_safe': True})
    DISCHARGE_SLOT_1_END = (57, {'type': Type.TIME, 'write_safe': True})
    ENABLE_AUTO_JUDGE_BATTERY_TYPE = (58, {'type': Type.BOOL})
    ENABLE_DISCHARGE = (59, {'type': Type.BOOL, 'write_safe': True})
    V_PV_INPUT_START = (60, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    INVERTER_START_TIME = (61, {'unit': Unit.TIME_S})
    INVERTER_RESTART_DELAY_TIME = (62, {'unit': Unit.TIME_S})
    V_AC_LOW_OUT = (63, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC_HIGH_OUT = (64, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    F_AC_LOW_OUT = (65, {'scaling': Scaling.CENTI, 'unit': Unit.FREQUENCY_HZ})
    F_AC_HIGH_OUT = (66, {'scaling': Scaling.CENTI, 'unit': Unit.FREQUENCY_HZ})
    V_AC_LOW_OUT_TIME = (67, {'type': Type.TIME})
    V_AC_HIGH_OUT_TIME = (68, {'type': Type.TIME})
    F_AC_LOW_OUT_TIME = (69, {'type': Type.TIME})
    F_AC_HIGH_OUT_TIME = (70, {'type': Type.TIME})
    V_AC_LOW_IN = (71, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC_HIGH_IN = (72, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    F_AC_LOW_IN = (73, {'scaling': Scaling.CENTI, 'unit': Unit.FREQUENCY_HZ})
    F_AC_HIGH_IN = (74, {'scaling': Scaling.CENTI, 'unit': Unit.FREQUENCY_HZ})
    V_AC_LOW_IN_TIME = (75, {'type': Type.TIME})
    V_AC_HIGH_IN_TIME = (76, {'type': Type.TIME})
    F_AC_LOW_IN_TIME = (77, {'type': Type.TIME})
    F_AC_HIGH_IN_TIME = (78, {'type': Type.TIME})
    V_AC_LOW_C = (79, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC_HIGH_C = (80, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    F_AC_LOW_C = (81, {'scaling': Scaling.CENTI, 'unit': Unit.FREQUENCY_HZ})
    F_AC_HIGH_C = (82, {'scaling': Scaling.CENTI, 'unit': Unit.FREQUENCY_HZ})
    V_10_MIN_PROTECTION = (83, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    ISO1 = 84
    ISO2 = 85
    # protection events: ground fault circuit interrupter, DC injection
    GFCI_1_I = (86, {'unit': Unit.CURRENT_MA})
    GFCI_1_TIME = (87, {'type': Type.TIME})
    GFCI_2_I = (88, {'unit': Unit.CURRENT_MA})
    GFCI_2_TIME = (89, {'type': Type.TIME})
    DCI_1_I = (90, {'unit': Unit.CURRENT_MA})
    DCI_1_TIME = (91, {'type': Type.TIME})
    DCI_2_I = (92, {'unit': Unit.CURRENT_MA})
    DCI_2_TIME = (93, {'type': Type.TIME})
    CHARGE_SLOT_1_START = (94, {'type': Type.TIME, 'write_safe': True})
    CHARGE_SLOT_1_END = (95, {'type': Type.TIME, 'write_safe': True})
    CHARGE_ENABLE = (96, {'type': Type.BOOL, 'write_safe': True})
    V_BATTERY_UNDER_PROTECTION_LIMIT = (97, {'scaling': Scaling.CENTI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_OVER_PROTECTION_LIMIT = (98, {'scaling': Scaling.CENTI, 'unit': Unit.VOLTAGE_V})
    PV1_VOLTAGE_ADJUST = (99, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    PV2_VOLTAGE_ADJUST = (100, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    GRID_R_VOLTAGE_ADJUST = (101, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    GRID_S_VOLTAGE_ADJUST = (102, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    GRID_T_VOLTAGE_ADJUST = (103, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    GRID_POWER_ADJUST = (104, {'unit': Unit.POWER_W})
    BATTERY_VOLTAGE_ADJUST = (105, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    PV1_POWER_ADJUST = (106, {'unit': Unit.POWER_W})
    PV2_POWER_ADJUST = (107, {'unit': Unit.POWER_W})
    BATTERY_LOW_FORCE_CHARGE_TIME = (108, {'unit': Unit.TIME_M})
    ENABLE_BMS_READ = (109, {'type': Type.BOOL})
    BATTERY_SOC_RESERVE = (110, {'type': Type.PERCENT, 'write_safe': True})
    # in beta dashboard: Battery Charge & Discharge Power, but rendered as W (50%=2600W), don't set above this?
    BATTERY_CHARGE_LIMIT = (111, {'type': Type.PERCENT, 'write_safe': True})
    BATTERY_DISCHARGE_LIMIT = (112, {'type': Type.PERCENT, 'write_safe': True})
    ENABLE_BUZZER = (113, {'type': Type.BOOL})
    # in beta dashboard: Battery Cutoff % Limit
    BATTERY_DISCHARGE_MIN_POWER_RESERVE = (114, {'type': Type.PERCENT, 'write_safe': True})
    ISLAND_CHECK_CONTINUE = 115
    CHARGE_TARGET_SOC = (116, {'type': Type.PERCENT, 'write_safe': True})  # when ENABLE_CHARGE_TARGET is enabled
    CHARGE_SOC_STOP_2 = (117, {'type': Type.PERCENT})
    DISCHARGE_SOC_STOP_2 = (118, {'type': Type.PERCENT})
    CHARGE_SOC_STOP_1 = (119, {'type': Type.PERCENT})
    DISCHARGE_SOC_STOP_1 = (120, {'type': Type.PERCENT})
    LOCAL_COMMAND_TEST = (121, {})
    POWER_FACTOR_FUNCTION_MODEL = (122, {})
    FREQUENCY_LOAD_LIMIT_RATE = (123, {})
    ENABLE_LOW_VOLTAGE_FAULT_RIDE_THROUGH = (124, {'type': Type.BOOL})
    ENABLE_FREQUENCY_DERATING = (125, {'type': Type.BOOL})
    ENABLE_ABOVE_6KW_SYSTEM = (126, {'type': Type.BOOL})
    START_SYSTEM_AUTO_TEST = (127, {'type': Type.BOOL})
    ENABLE_SPI = (128, {'type': Type.BOOL})
    PF_CMD_MEMORY_STATE = (129, {})
    # power factor limit line points: LP=load percentage, PF=power factor
    PF_LIMIT_LP1_LP = (130, {'type': Type.PERCENT})
    PF_LIMIT_LP1_PF = (131, {'type': Type.POWER_FACTOR})
    PF_LIMIT_LP2_LP = (132, {'type': Type.PERCENT})
    PF_LIMIT_LP2_PF = (133, {'type': Type.POWER_FACTOR})
    PF_LIMIT_LP3_LP = (134, {'type': Type.PERCENT})
    PF_LIMIT_LP3_PF = (135, {'type': Type.POWER_FACTOR})
    PF_LIMIT_LP4_LP = (136, {'type': Type.PERCENT})
    PF_LIMIT_LP4_PF = (137, {'type': Type.POWER_FACTOR})
    CEI021_V1S = (138, {})
    CEI021_V2S = (139, {})
    CEI021_V1L = (140, {})
    CEI021_V2L = (141, {})
    CEI021_Q_LOCK_IN_POWER = (142, {'type': Type.PERCENT})
    CEI021_Q_LOCK_OUT_POWER = (143, {'type': Type.PERCENT})
    CEI021_LOCK_IN_GRID_VOLTAGE = (144, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    CEI021_LOCK_OUT_GRID_VOLTAGE = (145, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    REG146 = (146, {})
    REG147 = (147, {})
    REG148 = (148, {})
    REG149 = (149, {})
    REG150 = (150, {})
    REG151 = (151, {})
    REG152 = (152, {})
    REG153 = (153, {})
    REG154 = (154, {})
    REG155 = (155, {})
    REG156 = (156, {})
    REG157 = (157, {})
    REG158 = (158, {})
    REG159 = (159, {})
    REG160 = (160, {})
    REG161 = (161, {})
    REG162 = (162, {})
    REG163 = (163, {})
    REG164 = (164, {})
    REG165 = (165, {})
    REG166 = (166, {})
    REG167 = (167, {})
    REG168 = (168, {})
    REG169 = (169, {})
    REG170 = (170, {})
    REG171 = (171, {})
    REG172 = (172, {})
    REG173 = (173, {})
    REG174 = (174, {})
    REG175 = (175, {})
    REG176 = (176, {})
    REG177 = (177, {})
    REG178 = (178, {})
    REG179 = (179, {})
    REG180 = (180, {})
    REG181 = (181, {})
    REG182 = (182, {})
    REG183 = (183, {})
    REG184 = (184, {})
    REG185 = (185, {})
    REG186 = (186, {})
    REG187 = (187, {})
    REG188 = (188, {})
    REG189 = (189, {})
    REG190 = (190, {})
    REG191 = (191, {})
    REG192 = (192, {})
    REG193 = (193, {})
    REG194 = (194, {})
    REG195 = (195, {})
    REG196 = (196, {})
    REG197 = (197, {})
    REG198 = (198, {})
    REG199 = (199, {})
    REG200 = (200, {})
    REG201 = (201, {})


class InputRegister(Register):
    """Definitions of what registers in the Input Bank represent."""

    INVERTER_STATUS = 0  # 0:waiting 1:normal 2:warning 3:fault 4:flash/fw update
    V_PV1 = (1, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_PV2 = (2, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_P_BUS = (3, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_N_BUS = (4, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC1 = (5, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    E_BATTERY_THROUGHPUT_H = (6, {'type': Type.UINT32_HIGH, 'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_BATTERY_THROUGHPUT_L = (7, {'type': Type.UINT32_LOW, 'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    I_PV1 = (8, {'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    I_PV2 = (9, {'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    I_AC1 = (10, {'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    P_PV_TOTAL_GENERATING_CAPACITY_H = (11, {'type': Type.UINT32_HIGH, 'scaling': Scaling.DECI, 'unit': Unit.POWER_KW})
    P_PV_TOTAL_GENERATING_CAPACITY_L = (12, {'type': Type.UINT32_LOW, 'scaling': Scaling.DECI, 'unit': Unit.POWER_KW})
    F_AC1 = (13, {'scaling': Scaling.CENTI, 'unit': Unit.FREQUENCY_HZ})
    CHARGE_STATUS = 14  # 2?
    V_HIGHBRIGH_BUS = 15  # high voltage bus?
    PF_INVERTER_OUTPUT = (16, {'type': Type.POWER_FACTOR})  # should be F_? seems to be hovering between 4800-5400
    E_PV1_DAY = (17, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    P_PV1 = (18, {'unit': Unit.POWER_KW})
    E_PV2_DAY = (19, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    P_PV2 = (20, {'unit': Unit.POWER_KW})
    E_GRID_EXPORT_DAY_H = (21, {'type': Type.UINT32_HIGH, 'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_GRID_EXPORT_DAY_L = (22, {'type': Type.UINT32_LOW, 'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_SOLAR_DIVERTER = (23, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    P_INVERTER_OUTPUT = (24, {'type': Type.INT16, 'unit': Unit.POWER_W})
    E_GRID_OUT_DAY = (25, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_GRID_IN_DAY = (26, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_INVERTER_IN_TOTAL_H = (27, {'type': Type.UINT32_HIGH, 'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_INVERTER_IN_TOTAL_L = (28, {'type': Type.UINT32_LOW, 'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_DISCHARGE_YEAR = (29, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    P_GRID_OUTPUT = (30, {'type': Type.INT16, 'unit': Unit.POWER_W})  # + export / - import? how different from #33
    P_BACKUP = (31, {'unit': Unit.POWER_W})
    E_GRID_IMPORT_TOTAL_H = (32, {'type': Type.UINT32_HIGH, 'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_GRID_IMPORT_TOTAL_L = (33, {'type': Type.UINT32_LOW, 'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    REG034 = 34
    E_INVERTER_CHARGE_DAY = (35, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_BATTERY_CHARGE_DAY = (36, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_BATTERY_DISCHARGE_DAY = (37, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    INVERTER_COUNTDOWN = (38, {'unit': Unit.TIME_S})
    FAULT_CODE_H = (39, {'type': Type.BITFIELD})
    FAULT_CODE_L = (40, {'type': Type.BITFIELD})
    TEMP_INVERTER_HEATSINK = (41, {'scaling': Scaling.DECI, 'unit': Unit.TEMPERATURE_C})
    P_LOAD_DEMAND = (42, {'unit': Unit.POWER_W})
    P_GRID_APPARENT = (43, {'unit': Unit.POWER_VA})
    E_GENERATED_DAY = (44, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_GENERATED_TOTAL_H = (45, {'type': Type.UINT32_HIGH, 'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_GENERATED_TOTAL_L = (46, {'type': Type.UINT32_LOW, 'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    WORK_TIME_TOTAL_H = (47, {'type': Type.UINT32_HIGH, 'unit': Unit.TIME_S})
    WORK_TIME_TOTAL_L = (48, {'type': Type.UINT32_LOW, 'unit': Unit.TIME_S})
    SYSTEM_MODE = 49  # 0:offline, 1:grid-tied
    V_BAT = (50, {'scaling': Scaling.CENTI, 'unit': Unit.VOLTAGE_V})
    I_BAT = (51, {'type': Type.INT16, 'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    P_BAT = (52, {'type': Type.INT16, 'unit': Unit.POWER_W})
    V_EPS_OUTPUT = (53, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    F_EPS_OUTPUT = (54, {'scaling': Scaling.CENTI, 'unit': Unit.FREQUENCY_HZ})
    TEMP_CHARGER = (55, {'scaling': Scaling.DECI, 'unit': Unit.TEMPERATURE_C})
    TEMP_BATTERY = (56, {'scaling': Scaling.DECI, 'unit': Unit.TEMPERATURE_C})
    CHARGER_WARNING_CODE = 57
    I_GRID_PORT = (58, {'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    BATTERY_PERCENT = (59, {'type': Type.PERCENT})
    V_BATTERY_CELL_01 = (60, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_02 = (61, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_03 = (62, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_04 = (63, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_05 = (64, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_06 = (65, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_07 = (66, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_08 = (67, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_09 = (68, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_10 = (69, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_11 = (70, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_12 = (71, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_13 = (72, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_14 = (73, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_15 = (74, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_CELL_16 = (75, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    TEMP_BATTERY_BLOCK_1 = (76, {'scaling': Scaling.DECI, 'unit': Unit.TEMPERATURE_C})
    TEMP_BATTERY_BLOCK_2 = (77, {'scaling': Scaling.DECI, 'unit': Unit.TEMPERATURE_C})
    TEMP_BATTERY_BLOCK_3 = (78, {'scaling': Scaling.DECI, 'unit': Unit.TEMPERATURE_C})
    TEMP_BATTERY_BLOCK_4 = (79, {'scaling': Scaling.DECI, 'unit': Unit.TEMPERATURE_C})
    V_SUM_CELLS = (80, {'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    TEMP_BMS_MOS = (81, {'scaling': Scaling.DECI, 'unit': Unit.TEMPERATURE_C})
    V_BATTERY_OUT_H = (82, {'type': Type.UINT32_HIGH, 'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    V_BATTERY_OUT_L = (83, {'type': Type.UINT32_LOW, 'scaling': Scaling.MILLI, 'unit': Unit.VOLTAGE_V})
    BATTERY_FULL_CAPACITY_H = (84, {'type': Type.UINT32_HIGH, 'scaling': Scaling.CENTI, 'unit': Unit.CHARGE_AH})
    BATTERY_FULL_CAPACITY_L = (85, {'type': Type.UINT32_LOW, 'scaling': Scaling.CENTI, 'unit': Unit.CHARGE_AH})
    BATTERY_DESIGN_CAPACITY_H = (86, {'type': Type.UINT32_HIGH, 'scaling': Scaling.CENTI, 'unit': Unit.CHARGE_AH})
    BATTERY_DESIGN_CAPACITY_L = (87, {'type': Type.UINT32_LOW, 'scaling': Scaling.CENTI, 'unit': Unit.CHARGE_AH})
    BATTERY_REMAINING_CAPACITY_H = (88, {'type': Type.UINT32_HIGH, 'scaling': Scaling.CENTI, 'unit': Unit.CHARGE_AH})
    BATTERY_REMAINING_CAPACITY_L = (89, {'type': Type.UINT32_LOW, 'scaling': Scaling.CENTI, 'unit': Unit.CHARGE_AH})
    BATTERY_STATUS_1_2 = (90, {'type': Type.DUINT8})
    BATTERY_STATUS_3_4 = (91, {'type': Type.DUINT8})
    BATTERY_STATUS_5_6 = (92, {'type': Type.DUINT8})
    BATTERY_STATUS_7 = (93, {'type': Type.DUINT8})
    BATTERY_WARNING_1_2 = (94, {'type': Type.DUINT8})
    REG095 = 95
    BATTERY_CYCLES = 96
    BATTERY_NO_OF_CELLS = 97
    BMS_FIRMWARE_VERSION_2 = 98
    REG099 = 99
    BATTERY_SOC = 100
    BATTERY_DESIGN_CAPACITY_2_H = (101, {'type': Type.UINT32_HIGH, 'scaling': Scaling.CENTI, 'unit': Unit.CHARGE_AH})
    BATTERY_DESIGN_CAPACITY_2_L = (102, {'type': Type.UINT32_LOW, 'scaling': Scaling.CENTI, 'unit': Unit.CHARGE_AH})
    T_BATTERY_MAX = (103, {'scaling': Scaling.DECI, 'unit': Unit.TEMPERATURE_C})
    T_BATTERY_MIN = (104, {'scaling': Scaling.DECI, 'unit': Unit.TEMPERATURE_C})
    REG105 = (105, {})
    REG106 = (106, {})
    REG107 = 107
    REG108 = 108
    REG109 = 109
    BATTERY_SERIAL_NUMBER_1_2 = (110, {'scaling': Type.ASCII})
    BATTERY_SERIAL_NUMBER_3_4 = (111, {'scaling': Type.ASCII})
    BATTERY_SERIAL_NUMBER_5_6 = (112, {'scaling': Type.ASCII})
    BATTERY_SERIAL_NUMBER_7_8 = (113, {'scaling': Type.ASCII})
    BATTERY_SERIAL_NUMBER_9_10 = (114, {'scaling': Type.ASCII})
    USB_INSERTED = (115, {'type': Type.BOOL})  # 0X08 = true; 0X00 = false
    REG116 = 116
    REG117 = 117
    REG118 = 118
    REG119 = 119
    REG120 = 120
    REG121 = 121
    REG122 = 122
    REG123 = 123
    REG124 = 124
    REG125 = 125
    REG126 = 126
    REG127 = 127
    REG128 = 128
    REG129 = 129
    REG130 = 130
    REG131 = 131
    REG132 = 132
    REG133 = 133
    REG134 = 134
    REG135 = 135
    REG136 = 136
    REG137 = 137
    REG138 = 138
    REG139 = 139
    REG140 = 140
    REG141 = 141
    REG142 = 142
    REG143 = 143
    REG144 = 144
    REG145 = 145
    REG146 = 146
    REG147 = 147
    REG148 = 148
    REG149 = 149
    REG150 = 150
    REG151 = 151
    REG152 = 152
    REG153 = 153
    REG154 = 154
    REG155 = 155
    REG156 = 156
    REG157 = 157
    REG158 = 158
    REG159 = 159
    REG160 = 160
    REG161 = 161
    REG162 = 162
    REG163 = 163
    REG164 = 164
    REG165 = 165
    REG166 = 166
    REG167 = 167
    REG168 = 168
    REG169 = 169
    REG170 = 170
    REG171 = 171
    REG172 = 172
    REG173 = 173
    REG174 = 174
    REG175 = 175
    REG176 = 176
    REG177 = 177
    REG178 = 178
    REG179 = 179
    E_BATTERY_DISCHARGE_TOTAL = (180, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_BATTERY_CHARGE_TOTAL = (181, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_BATTERY_DISCHARGE_DAY_2 = (182, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    E_BATTERY_CHARGE_DAY_2 = (183, {'scaling': Scaling.DECI, 'unit': Unit.ENERGY_KWH})
    REG184 = (184, {})
    REG185 = (185, {})
    REG186 = (186, {})
    REG187 = (187, {})
    REG188 = (188, {})
    REG189 = (189, {})
    REG190 = (190, {})
    REG191 = (191, {})
    REG192 = (192, {})
    REG193 = (193, {})
    REG194 = (194, {})
    REG195 = (195, {})
    REG196 = (196, {})
    REG197 = (197, {})
    REG198 = (198, {})
    REG199 = (199, {})
    REG200 = (200, {})
    REMOTE_BMS_RESTART = (201, {'type': Type.BOOL})
    REG202 = (202, {})
    REG203 = (203, {})
    REG204 = (204, {})
    REG205 = (205, {})
    REG206 = (206, {})
    REG207 = (207, {})
    REG208 = (208, {})
    REG209 = (209, {})
    ISO_FAULT_VALUE = (210, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    GFCI_FAULT_VALUE = (211, {'unit': Unit.CURRENT_MA})
    DCI_FAULT_VALUE = (212, {'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    V_PV_FAULT_VALUE = (213, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC_FAULT_VALUE = (214, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    F_AV_FAULT_VALUE = (215, {'scaling': Scaling.CENTI, 'unit': Unit.FREQUENCY_HZ})
    TEMP_FAULT_VALUE = (216, {'scaling': Scaling.DECI, 'unit': Unit.TEMPERATURE_C})
    REG217 = (217, {})
    REG218 = (218, {})
    REG219 = (219, {})
    REG220 = (220, {})
    REG221 = (221, {})
    REG222 = (222, {})
    REG223 = (223, {})
    REG224 = (224, {})
    AUTO_TEST_PROCESS_OR_AUTO_TEST_STEP = (225, {'type': Type.BITFIELD})
    AUTO_TEST_RESULT = (226, {})
    AUTO_TEST_STOP_STEP = (227, {})
    REG228 = (228, {})
    SAFETY_V_F_LIMIT = (229, {'scaling': Scaling.DECI})
    SAFETY_TIME_LIMIT = (230, {'unit': Unit.TIME_MS})
    REAL_V_F_VALUE = (231, {'scaling': Scaling.DECI})
    TEST_VALUE = (232, {'scaling': Scaling.DECI})
    TEST_TREAT_VALUE = (233, {'scaling': Scaling.DECI})
    TEST_TREAT_TIME = (234, {})
    REG235 = (235, {})
    REG236 = (236, {})
    REG237 = (237, {})
    REG238 = (238, {})
    REG239 = (239, {})
    V_AC1_M3 = (240, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC2_M3 = (241, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC3_M3 = (242, {'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    I_AC1_M3 = (243, {'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    I_AC2_M3 = (244, {'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    I_AC3_M3 = (245, {'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    GFCI_M3 = (246, {'scaling': Scaling.DECI, 'unit': Unit.CURRENT_MA})
    REG247 = (247, {})
    REG248 = (248, {})
    REG249 = (249, {})
    REG250 = (250, {})
    REG251 = (251, {})
    REG252 = (252, {})
    REG253 = (253, {})
    REG254 = (254, {})
    REG255 = (255, {})
    REG256 = (256, {})
    REG257 = (257, {})
    V_PV1_LIMIT = (258, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_PV2_LIMIT = (259, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_BUS_LIMIT = (260, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_N_BUS_LIMIT = (261, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC1_LIMIT = (262, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC2_LIMIT = (263, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC3_LIMIT = (264, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    I_PV1_LIMIT = (265, {'type': Type.INT16, 'unit': Unit.CURRENT_MA})
    I_PV2_LIMIT = (266, {'type': Type.INT16, 'unit': Unit.CURRENT_MA})
    I_AC1_LIMIT = (267, {'type': Type.INT16, 'unit': Unit.CURRENT_MA})
    I_AC2_LIMIT = (268, {'type': Type.INT16, 'unit': Unit.CURRENT_MA})
    I_AC3_LIMIT = (269, {'type': Type.INT16, 'unit': Unit.CURRENT_MA})
    P_AC1_LIMIT = (270, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.POWER_W})
    P_AC2_LIMIT = (271, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.POWER_W})
    P_AC3_LIMIT = (272, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.POWER_W})
    DCI_LIMIT = (273, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.CURRENT_MA})
    GFCI_LIMIT = (274, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.CURRENT_MA})
    V_AC1_M3_LIMIT = (275, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC2_M3_LIMIT = (276, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    V_AC3_M3_LIMIT = (277, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.VOLTAGE_V})
    I_AC1_M3_LIMIT = (278, {'type': Type.INT16, 'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    I_AC2_M3_LIMIT = (279, {'type': Type.INT16, 'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    I_AC3_M3_LIMIT = (280, {'type': Type.INT16, 'scaling': Scaling.CENTI, 'unit': Unit.CURRENT_A})
    GFCI_M3_LIMIT = (281, {'type': Type.INT16, 'scaling': Scaling.DECI, 'unit': Unit.CURRENT_MA})
    V_BATTERY_LIMIT = (282, {'type': Type.INT16, 'scaling': Scaling.CENTI, 'unit': Unit.VOLTAGE_V})
    REG283 = (283, {})
    REG284 = (284, {})
    REG285 = (285, {})
    REG286 = (286, {})
    REG287 = (287, {})
    REG288 = (288, {})
    REG289 = (289, {})
    REG290 = (290, {})
    REG291 = (291, {})
    REG292 = (292, {})
    REG293 = (293, {})
    REG294 = (294, {})
    REG295 = (295, {})
    REG296 = (296, {})
    REG297 = (297, {})
    REG298 = (298, {})
    REG299 = (299, {})
    REG300 = (300, {})
    REG301 = (301, {})


class HoldingRegisters(dict[int, int]):
    """In-memory cache of Holding Registers."""

    data_type = HoldingRegister


class InputRegisters(dict[int, int]):
    """In-memory cache of Input Registers."""

    data_type = InputRegister


class RegisterCache:
    """Holds a cache of registers populated after querying a device."""

    def __init__(self):
        """Constructor."""
        self.holding_registers = HoldingRegisters()
        self.input_registers = InputRegisters()

    def __getattr__(self, item: str):
        """Magic attributes that try to look up and convert register values."""
        item = item.upper()

        for values in (self.holding_registers, self.input_registers):
            register: Register = values.data_type
            if item in register.__members__:
                register = register[item]
                if register.value in values:
                    return register.convert(values[register.value])
            if item + '_H' in register.__members__:
                # composite registers
                # fmt: off
                register_h = register[item + "_H"]
                register_l = register[item + "_L"]
                return (
                    register_h.convert(values[register_h.value])
                    + register_l.convert(values[register_l.value])
                )
                # fmt: on

        raise KeyError(item.lower())

    def update_holding_registers(self, holding_registers: dict[int, int]):
        """Update internal holding register cache with given values."""
        self.holding_registers.update(holding_registers)

    def update_input_registers(self, input_registers: dict[int, int]):
        """Update internal input register cache with given values."""
        self.input_registers.update(input_registers)

    def debug(self):
        """Dump the internal state of registers and their value representations."""
        print('#' * 140)
        for i, v in self.holding_registers.items():
            r = HoldingRegister(i)
            print(f'{i:3} {r.name:>35}: {r.repr(v):20}  |  {r.type.name:15}  {r.scaling.name:5}  0x{v:04x}  {v:10}')

        print('#' * 140)
        for i, v in self.input_registers.items():
            r = InputRegister(i)
            print(f'{i:3} {r.name:>35}: {r.repr(v):20}  |  {r.type.name:15}  {r.scaling.name:5}  0x{v:04x}  {v:10}')
