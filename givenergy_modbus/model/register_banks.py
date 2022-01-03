from enum import Enum, unique

from .register import Scaling, Type, Unit


@unique
class RegisterBank(str, Enum):
    """Mixin to help easier access to register bank structures."""

    def __new__(cls, value: int, data=None):
        """Allows indexing by register index."""
        if data is None:
            data = {}
        obj = str.__new__(cls, f'{cls}:{hex(value)}')
        obj._value_ = value
        obj.type = data.get('type', Type.WORD)  # type: ignore  # shut up mypy
        obj.scaling = data.get('scaling', Scaling.UNIT)  # type: ignore  # shut up mypy
        obj.unit = data.get('unit', None)  # type: ignore  # shut up mypy
        obj.description = data.get('description', None)  # type: ignore  # shut up mypy
        obj.write_safe = data.get('write_safe', False)  # type: ignore  # shut up mypy
        return obj

    def render(self, val):
        """Convert val to its true representation as determined by the register type."""
        return self.type.render(val, self.scaling.value)


# f mt: off
class HoldingRegister(RegisterBank):
    """Definitions of what registers in the Holding Bank represent."""

    DEVICE_TYPE_CODE = (0, {'description': "Device Type Code"})
    INVERTER_MODULE_H = (1, {'type': Type.DWORD_HIGH})
    INVERTER_MODULE_L = (2, {'type': Type.DWORD_LOW})
    INPUT_TRACKER_NUM_AND_OUTPUT_PHASE_NUM = 3
    REG004 = 4
    REG005 = 5
    REG006 = 6
    REG007 = 7
    BATTERY_SERIAL_NUMBER_5 = (8, {'type': Type.ASCII})
    BATTERY_SERIAL_NUMBER_4 = (9, {'type': Type.ASCII})
    BATTERY_SERIAL_NUMBER_3 = (10, {'type': Type.ASCII})
    BATTERY_SERIAL_NUMBER_2 = (11, {'type': Type.ASCII})
    BATTERY_SERIAL_NUMBER_1 = (12, {'type': Type.ASCII})
    INVERTER_SERIAL_NUMBER_5 = (13, {'type': Type.ASCII})
    INVERTER_SERIAL_NUMBER_4 = (14, {'type': Type.ASCII})
    INVERTER_SERIAL_NUMBER_3 = (15, {'type': Type.ASCII})
    INVERTER_SERIAL_NUMBER_2 = (16, {'type': Type.ASCII})
    INVERTER_SERIAL_NUMBER_1 = (17, {'type': Type.ASCII})
    BATTERY_FIRMWARE_VERSION = 18
    DSP_FIRMWARE_VERSION = 19
    WINTER_MODE = (20, {'type': Type.BOOL, 'write_safe': True})
    ARM_FIRMWARE_VERSION = 21
    WIFI_OR_U_DISK = 22  # 2 = wifi?
    SELECT_DSP_OR_ARM = 23
    SET_VARIABLE_ADDRESS = 24
    SET_VARIABLE_VALUE = 25
    GRID_PORT_MAX_OUTPUT_POWER = 26
    BATTERY_POWER_MODE = (27, {'write_safe': True})  # 1 - grid-tie?
    FRE_MODE = 28  # bool?
    SOC_FORCE_ADJUST = 29
    COMMUNICATE_ADDRESS = 30
    CHARGE_SLOT_2_START = (31, {'write_safe': True})
    CHARGE_SLOT_2_END = (32, {'write_safe': True})
    USER_CODE = 33
    MODBUS_VERSION = (34, {'scaling': Scaling.CENTI})
    SYSTEM_TIME_YEAR = (35, {'write_safe': True})
    SYSTEM_TIME_MONTH = (36, {'write_safe': True})
    SYSTEM_TIME_DAY = (37, {'write_safe': True})
    SYSTEM_TIME_HOUR = (38, {'write_safe': True})
    SYSTEM_TIME_MINUTE = (39, {'write_safe': True})
    SYSTEM_TIME_SECOND = (40, {'write_safe': True})
    DRM_ENABLE = (41, {'type': Type.BOOL})
    CT_ADJUST = 42
    CHARGE_AND_DISCHARGE_SOC = 43
    DISCHARGE_SLOT_2_START = (44, {'write_safe': True})
    DISCHARGE_SLOT_2_END = (45, {'write_safe': True})
    BMS_VERSION = 46
    B_METER_TYPE = 47
    B_115_METER_DIRECT = 48
    B_418_METER_DIRECT = 49
    ACTIVE_P_RATE = 50
    REACTIVE_P_RATE = 51
    POWER_FACTOR = 52
    INVERTER_STATE = 53  # 1 = normal?
    BATTERY_TYPE = 54  # 1 = lithium?
    BATTERY_NOMINAL_CAPACITY = 55
    DISCHARGE_SLOT_1_START = (56, {'write_safe': True})
    DISCHARGE_SLOT_1_END = (57, {'write_safe': True})
    AUTO_JUDGE_BATTERY_TYPE_ENABLE = 58  # bool?
    DISCHARGE_ENABLE = (59, {'type': Type.BOOL, 'write_safe': True})
    INPUT_START_VOLTAGE = 60
    START_TIME = 61
    RESTART_DELAY_TIME = 62
    V_AC_LOW_OUT = (63, {'scaling': Scaling.DECI})
    V_AC_HIGH_OUT = (64, {'scaling': Scaling.DECI})
    F_AC_LOW_OUT = (65, {'scaling': Scaling.CENTI})
    F_AC_HIGH_OUT = (66, {'scaling': Scaling.CENTI})
    V_AC_LOW_OUT_TIME = 67
    V_AC_HIGH_OUT_TIME = 68
    F_AC_LOW_OUT_TIME = 69
    F_AC_HIGH_OUT_TIME = 70
    V_AC_LOW_IN = (71, {'scaling': Scaling.DECI})
    V_AC_HIGH_IN = (72, {'scaling': Scaling.DECI})
    F_AC_LOW_IN = (73, {'scaling': Scaling.CENTI})
    F_AC_HIGH_IN = (74, {'scaling': Scaling.CENTI})
    V_AC_LOW_IN_TIME = 75
    V_AC_HIGH_IN_TIME = 76
    F_AC_LOW_TIME_IN = 77
    F_AC_HIGH_TIME_IN = 78
    V_AC_LOW_C = (79, {'scaling': Scaling.DECI})
    V_AC_HIGH_C = (80, {'scaling': Scaling.DECI})
    F_AC_LOW_C = (81, {'scaling': Scaling.CENTI})
    F_AC_HIGH_C = (82, {'scaling': Scaling.CENTI, 'unit': Unit.FREQUENCY_HZ})
    U_10_MIN = 83
    ISO1 = 84
    ISO2 = 85
    GFCI_I_1 = 86
    GFCI_TIME_1 = 87
    GFCI_I_2 = 88
    GFCI_TIME_2 = 89
    DCI_I_1 = 90
    DCI_TIME_1 = 91
    DCI_I_2 = 92
    DCI_TIME_2 = 93
    CHARGE_SLOT_1_START = (94, {'write_safe': True})
    CHARGE_SLOT_1_END = (95, {'write_safe': True})
    BATTERY_SMART_CHARGE = (96, {'type': Type.BOOL, 'write_safe': True})
    DISCHARGE_LOW_LIMIT = 97
    CHARGER_HIGH_LIMIT = 98
    PV1_VOLT_ADJUST = 99
    PV2_VOLT_ADJUST = 100
    GRID_R_VOLT_ADJUST = 101
    GRID_S_VOLT_ADJUST = 102
    GRID_T_VOLT_ADJUST = 103
    GRID_POWER_ADJUST = 104
    BATTERY_VOLT_ADJUST = 105
    PV1_POWER_ADJUST = 106
    PV2_POWER_ADJUST = 107
    BATTERY_LOW_FORCE_CHARGE_TIME = 108
    BMS_TYPE = 109
    SHALLOW_CHARGE = (110, {'write_safe': True})
    BATTERY_CHARGE_LIMIT = (111, {'write_safe': True})
    BATTERY_DISCHARGE_LIMIT = (112, {'write_safe': True})
    BUZZER_SW = 113
    BATTERY_POWER_RESERVE = (114, {'write_safe': True})
    ISLAND_CHECK_CONTINUE = 115
    TARGET_SOC = (116, {'write_safe': True})
    CHG_SOC_STOP2 = 117
    DISCHARGE_SOC_STOP2 = 118
    CHG_SOC_STOP = 119
    DISCHARGE_SOC_STOP = 120


class InputRegister(RegisterBank):
    """Definitions of what registers in the Input Bank represent."""

    INVERTER_STATUS = 0  # 0 waiting (no PV, no bat)? 1 charging?
    V_PV1 = (1, {'scaling': Scaling.DECI})
    V_PV2 = (2, {'scaling': Scaling.DECI})
    P_BUS_INSIDE_VOLTAGE = (3, {'scaling': Scaling.DECI})
    N_BUS_INSIDE_VOLTAGE = (4, {'scaling': Scaling.DECI})
    V_SINGLE_PHASE_GRID = (5, {'scaling': Scaling.DECI})
    E_BATTERY_THROUGHPUT_H = (6, {'type': Type.DWORD_HIGH, 'scaling': Scaling.DECI})
    E_BATTERY_THROUGHPUT_L = (7, {'type': Type.DWORD_LOW, 'scaling': Scaling.DECI})
    I_PV1_INPUT = (8, {'scaling': Scaling.CENTI})
    I_PV2_INPUT = (9, {'scaling': Scaling.CENTI})
    I_GRID_OUTPUT_SINGLE_PHASE = (10, {'scaling': Scaling.CENTI})
    PV_TOTAL_GENERATING_CAPACITY_H = (11, {'type': Type.DWORD_HIGH, 'scaling': Scaling.DECI})
    PV_TOTAL_GENERATING_CAPACITY_L = (12, {'type': Type.DWORD_LOW, 'scaling': Scaling.DECI})
    F_GRID_THREE_SINGLE_PHASE = (13, {'scaling': Scaling.CENTI})
    CHARGE_STATUS = 14
    V_HIGHBRIGH_BUS = 15  # high voltage bus?
    PF_INVERTER_OUTPUT_NOW = 16
    E_PV1_DAY = (17, {'scaling': Scaling.DECI})
    P_PV1_INPUT = 18
    E_PV2_DAY = (19, {'scaling': Scaling.DECI})
    P_PV2_INPUT = 20
    E_GRID_OUT_TOTAL_H = (21, {'type': Type.DWORD_HIGH, 'scaling': Scaling.DECI})
    E_GRID_OUT_TOTAL_L = (22, {'type': Type.DWORD_LOW, 'scaling': Scaling.DECI})
    PV_MATE = (23, {'scaling': Scaling.DECI})
    P_GRID_THREE_SINGLE_PHASE_OUTPUT_L = (24, {'type': Type.SWORD})
    E_GRID_OUT_DAY = (25, {'scaling': Scaling.DECI})
    E_GRID_IN_DAY = (26, {'scaling': Scaling.DECI})
    E_INVERTER_IN_TOTAL_H = (27, {'type': Type.DWORD_HIGH, 'scaling': Scaling.DECI})
    E_INVERTER_IN_TOTAL_L = (28, {'type': Type.DWORD_LOW, 'scaling': Scaling.DECI})
    E_DISCHARGE_YEAR_L = (29, {'scaling': Scaling.DECI})
    P_GRID_OUTPUT = (30, {'type': Type.SWORD})
    P_BACKUP = 31
    P_GRID_IN_TOTAL_H = (32, {'type': Type.DWORD_HIGH, 'scaling': Scaling.DECI})
    P_GRID_IN_TOTAL_L = (33, {'type': Type.DWORD_LOW, 'scaling': Scaling.DECI})
    REG034 = 34
    E_TOTAL_LOAD_DAY = (35, {'scaling': Scaling.DECI})
    E_BATTERY_CHARGE_DAY = (36, {'scaling': Scaling.DECI})
    E_BATTERY_DISCHARGE_DAY = (37, {'scaling': Scaling.DECI})
    P_COUNTDOWN = 38
    FAULT_CODE_H = (39, {'type': Type.DWORD_HIGH})
    FAULT_CODE_L = (40, {'type': Type.DWORD_LOW})
    TEMP_INV = (41, {'scaling': Scaling.DECI})
    P_LOAD_TOTAL = 42
    P_GRID_APPARENT = 43
    E_GENERATED_DAY = (44, {'scaling': Scaling.DECI})
    E_GENERATED_H = (45, {'type': Type.DWORD_HIGH, 'scaling': Scaling.DECI})
    E_GENERATED_L = (46, {'type': Type.DWORD_LOW, 'scaling': Scaling.DECI})
    WORK_TIME_TOTAL_H = (47, {'type': Type.DWORD_HIGH})
    WORK_TIME_TOTAL_L = (48, {'type': Type.DWORD_LOW})
    SYSTEM_MODE = 49  # 1 = grid-tie?
    V_BAT = (50, {'scaling': Scaling.DECI})
    I_BAT = (51, {'type': Type.SWORD, 'scaling': Scaling.CENTI})
    P_BAT = (52, {'type': Type.SWORD})
    V_OUTPUT = (53, {'scaling': Scaling.DECI})
    F_OUTPUT = (54, {'scaling': Scaling.CENTI})
    TEMP_CHARGER = (55, {'scaling': Scaling.DECI})
    TEMP_BAT = (56, {'scaling': Scaling.DECI})
    CHARGER_WARNING_CODE = 57
    P_GRID_PORT = (58, {'scaling': Scaling.CENTI})
    BATTERY_PERCENT = 59
    V_BATTERY_CELL01 = (60, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL02 = (61, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL03 = (62, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL04 = (63, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL05 = (64, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL06 = (65, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL07 = (66, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL08 = (67, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL09 = (68, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL10 = (69, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL11 = (70, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL12 = (71, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL13 = (72, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL14 = (73, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL15 = (74, {'scaling': Scaling.MILLI})
    V_BATTERY_CELL16 = (75, {'scaling': Scaling.MILLI})
    REG076 = 76
    REG077 = 77
    REG078 = 78
    REG079 = 79
    REG080 = 80
    REG081 = 81
    REG082 = 82
    REG083 = 83
    REG084 = 84
    REG085 = 85
    REG086 = 86
    REG087 = 87
    REG088 = 88
    REG089 = 89
    REG090 = 90
    REG091 = 91
    REG092 = 92
    REG093 = 93
    REG094 = 94
    REG095 = 95
    REG096 = 96
    REG097 = 97
    REG098 = 98
    REG099 = 99
    REG100 = 100
    REG101 = 101
    REG102 = 102
    REG103 = 103
    REG104 = 104
    E_BATTERY_DISCHARGE_AC_TOTAL = (105, {'scaling': Scaling.DECI})
    E_BATTERY_CHARGE_AC_TOTAL = (106, {'scaling': Scaling.DECI})
    REG107 = 107
    REG108 = 108
    REG109 = 109
    BATTERY_SERIAL_NUMBER_5 = (110, {'scaling': Type.ASCII})
    BATTERY_SERIAL_NUMBER_4 = (111, {'scaling': Type.ASCII})
    BATTERY_SERIAL_NUMBER_3 = (112, {'scaling': Type.ASCII})
    BATTERY_SERIAL_NUMBER_2 = (113, {'scaling': Type.ASCII})
    BATTERY_SERIAL_NUMBER_1 = (114, {'scaling': Type.ASCII})
    REG115 = 115
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
    E_BATTERY_DISCHARGE_TOTAL = (180, {'scaling': Scaling.DECI})
    E_BATTERY_CHARGE_TOTAL = (181, {'scaling': Scaling.DECI})


# f mt: on
