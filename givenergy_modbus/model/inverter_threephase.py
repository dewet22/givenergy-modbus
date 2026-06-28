"""GivEnergy three-phase inverter data model."""

import warnings
from typing import ClassVar

from pydantic import ConfigDict, computed_field, create_model

from givenergy_modbus.client.commands import _InverterCommands, _ThreePhaseCommands
from givenergy_modbus.model.battery import BatteryMaintenance
from givenergy_modbus.model.inverter import (
    _DTC_RATED_POWER,
    AC_COUPLED_MODELS,
    BatteryType,
    Model,
    PowerFactorFunctionModel,
    SinglePhaseInverter,
    SinglePhaseInverterRegisterGetter,
    SlotMap,
    Status,
    _battery_max_power,
)
from givenergy_modbus.model.register import HR, IR, RegisterGetter, RegisterMetadataMixin
from givenergy_modbus.model.register import Converter as C
from givenergy_modbus.model.register import RegisterDefinition as Def


def _inverter_fault_code2(val: int, word: int) -> list[str] | None:
    """Decode a 16-bit fault register for three-phase inverters.

    `word` selects one of 8 fault tables (words 0-7), each covering 16 bits.
    Three-phase inverters expose fault words at IR(1300)-IR(1307); the
    parallel-operation word at IR(1308) is documented in some firmware but
    not surfaced by the model LUT (no `inverter_fault_codes_8` field), so the
    decoder only ships tables for the wired-up range.

    The lists below are LSB-indexed: position i corresponds to GE bit i (value
    bit i = 1 << i). Cross-validated against the GivEnergy Installer app
    v1.154.3 THREE_PHASE_HYBRID_FAULT_CODE_WORD_0..7 enums; all named GE bits
    confirmed present. Entries absent from the GE enum are kept as-is from the
    original britkat-sourced table and are not verified against hardware.
    """
    if val is None:
        return None
    _WORDS: list[list[str | None]] = [
        [  # word 0
            "Battery Voltage High",
            None,
            "Bus 2 Voltage high ISR",
            "Bus Voltage high ISR",
            "Inverter OCP fault TZ",
            "Frequency unstable",
            "Buck Boost Fault ISR",
            "BDC OCP Fault",
            "Grid Zero cross loss",
            None,
            None,
            None,
            "Grid Phase 1 voltage fault",
            "Grid Phase 2 voltage fault",
            "Grid Phase 3 voltage fault",
            "Grid frequency out of range",
        ],
        [  # word 1
            "Gateway Comm fault",
            "GFCI Damage",
            "Grid phase 1 voltage low",
            "Grid phase 1 voltage high",
            "Grid phase 2 voltage low",
            "Grid phase 2 voltage high",
            "Grid phase 3 voltage low",
            "Grid phase 3 voltage high",
            "Inverter OCP Fault ISR",
            None,
            None,
            None,
            "Inverter Phase 1 Current OCP (RMS)",
            "Inverter Phase 2 Current OCP (RMS)",
            "Inverter Phase 3 Current OCP (RMS)",
            "No Grid connection",
        ],
        [  # word 2
            "Grid Frequency Low",
            "Grid frequency High",
            "Grid voltage imbalance",
            "AC PLL fault",
            "Overload fault",
            "Backflow timeout",
            None,
            "Grid connected v/f out of range",
            "EPS phase 1 voltage loss",
            "EPS phase 2 voltage loss",
            "EPS phase 3 voltage loss",
            "EPS bus voltage low",
            "EPS overload",
            "EPS voltage high",
            "DCV high",
            "Battery OCP",
        ],
        [  # word 3
            "Battery reversed",
            "Battery open",
            "Battery voltage low",
            None,
            "Bus2 voltage abnormal",
            "Buck boost soft start fail",
            "Battery voltage high",
            None,
            "BMS Error",
            "BMS comm fault",
            None,
            None,
            None,
            "Battery sleep",
            "Lead acid NTC open",
            "BMS power forbid",
        ],
        [  # word 4
            None,
            None,
            None,
            None,
            None,
            "PV1 voltage low",
            "PV2 voltage low",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ],
        [  # word 5
            "DCI high",
            "PV isolation low",
            "NTC open",
            "Bus voltage high",
            "PV voltage high",
            "Boost over temperature",
            "Buck Boost over temperature",
            "Inverter over temperature",
            "EPS output short circuit",
            "Auto test fault",
            "Init Model fault",
            "Relay fault",
            "Bus voltage unbalance",
            "DSP firmware unmatched",
            "PV1 short circuit",
            "PV2 short circuit",
        ],
        [  # word 6
            "PV voltage high",
            "External device faulty",
            "Acom fault",
            "Bcom fault",
            "Master force inverter fault",
            "Master force SP fault",
            "GFCI High",
            "Virtual Load over temp",
            "Internal com fault3",
            "Grid consistent",
            "EPS connected grid",
            "Internal over temperature",
            "Fan fault",
            "Hardware unmatch",
            None,
            None,
        ],
        [  # word 7
            "CT clamp L/N reversed",
            "Pairing timeout",
            "Meter comms loss",
            None,
            None,
            None,
            "Battery over temperature",
            "Battery over load",
            "Battery full",
            "Battery needs Charge",
            "BMS Warning",
            "Battery weak",
            "Battery low power",
            "NTC open",
            "Fan warning",
            None,
        ],
    ]
    if word < 0 or word >= len(_WORDS):
        return None
    return [f for i, f in enumerate(_WORDS[word]) if (val >> i) & 1 and f is not None]


# Field names dropped from the three-phase merge: derived @computed_field properties, plus the
# single-phase-only HR(101-104) names that the R/S/T overrides below replace by address.
_DROP_ON_THREE_PHASE = (
    "p_battery",
    "e_battery_throughput",
    "grid_import_limit",
    "grid_import_limit_enabled",
    "enable_lora",
    "enable_battery_self_heating",
)

# Registers that are three-phase specific or that shadow single-phase registers at higher addresses.
# When merged with InverterRegisterGetter.REGISTER_LUT these entries win (dict update semantics).
_THREE_PHASE_LUT = {
    # HR(101-104): on three-phase hardware these are the per-line-phase grid voltage
    # adjustments + grid power adjustment (installer app GRID_R/S/T_VOLTAGE_ADJUSTMENT,
    # GRID_POWER_ADJUSTMENT). The single-phase getter reuses the same addresses for
    # grid_import_limit / _enabled / enable_lora / enable_battery_self_heating, so these
    # overrides restore the three-phase meaning. Scales unconfirmed → raw read-back.
    "grid_r_voltage_adjustment": Def(C.uint16, None, HR(101)),
    "grid_s_voltage_adjustment": Def(C.uint16, None, HR(102)),
    "grid_t_voltage_adjustment": Def(C.uint16, None, HR(103)),
    "grid_power_adjustment": Def(C.uint16, None, HR(104)),
    #
    # Holding Registers 1000–1124 — Three-Phase configuration
    #
    "system_enable": Def(C.bool, None, HR(1000)),
    "set_command_save": Def(C.bool, None, HR(1001)),
    "active_rate": Def(C.uint16, None, HR(1002)),
    "reactive_rate": Def(C.uint16, None, HR(1003)),
    "set_power_factor": Def(C.uint16, None, HR(1004)),
    "real_time_control": Def(C.bool, None, HR(1005)),
    "grid_connect_time": Def(C.uint16, None, HR(1007)),
    "grid_reconnect_time": Def(C.uint16, None, HR(1008)),
    "grid_connect_slope": Def(C.deci, None, HR(1009)),
    "com_baud_rate": Def(C.uint16, None, HR(1010)),
    "grid_reconnect_slope": Def(C.uint16, None, HR(1011)),
    # HR(1012) packs inverter rated power (nibble 0) and battery type (nibble 1) — encoding
    # unverified; inverter_max_power is already a computed_field; battery_type is at HR(1080).
    # HR(1013) nibble 1 → InverterType (SINGLE_PHASE_LV/HV, THREE_PHASE_LV/HV) — unclear whether
    # the full register or only a nibble holds the value; needs a register capture to confirm.
    # See open questions in fork-merge-plan.md.
    "meter_fail_enable": Def(C.uint16, None, HR(1017)),
    "v_grid_low_limit_trip": Def(C.deci, None, HR(1018), min=0.0, max=500.0),
    "v_grid_high_limit_trip": Def(C.deci, None, HR(1019), min=0.0, max=500.0),
    "f_grid_low_limit_trip": Def(C.centi, None, HR(1020), min=40.0, max=70.0),
    "f_grid_high_limit_trip": Def(C.centi, None, HR(1021), min=40.0, max=70.0),
    "v_grid_low_limit_reconnect": Def(C.deci, None, HR(1022), min=0.0, max=500.0),
    "v_grid_high_limit_reconnect": Def(C.deci, None, HR(1023), min=0.0, max=500.0),
    "f_grid_low_limit_reconnect": Def(C.centi, None, HR(1024), min=40.0, max=70.0),
    "f_grid_high_limit_reconnect": Def(C.centi, None, HR(1025), min=40.0, max=70.0),
    "v_grid_low_limit_grid": Def(C.deci, None, HR(1026), min=0.0, max=500.0),
    "v_grid_high_limit_grid": Def(C.deci, None, HR(1027), min=0.0, max=500.0),
    "f_grid_low_limit_grid": Def(C.centi, None, HR(1028), min=40.0, max=70.0),
    "f_grid_high_limit_grid": Def(C.centi, None, HR(1029), min=40.0, max=70.0),
    # HR(1030-1033) — CEE grid limits
    "v_grid_low_limit_cee": Def(C.deci, None, HR(1030), min=0.0, max=500.0),
    "v_grid_high_limit_cee": Def(C.deci, None, HR(1031), min=0.0, max=500.0),
    "f_grid_low_limit_cee": Def(C.centi, None, HR(1032), min=40.0, max=70.0),
    "f_grid_high_limit_cee": Def(C.centi, None, HR(1033), min=40.0, max=70.0),
    # HR(1034-1041) — time-based grid voltage/frequency limits
    "time_grid_low_voltage_limit_trip": Def(C.centi, None, HR(1034)),
    "time_grid_high_voltage_limit_trip": Def(C.centi, None, HR(1035)),
    "time_grid_low_voltage_limit_reconnect": Def(C.centi, None, HR(1036)),
    "time_grid_high_voltage_limit_reconnect": Def(C.centi, None, HR(1037)),
    "time_grid_low_freq_limit_trip": Def(C.centi, None, HR(1038)),
    "time_grid_high_freq_limit_trip": Def(C.centi, None, HR(1039)),
    "time_grid_low_freq_limit_reconnect": Def(C.centi, None, HR(1040)),
    "time_grid_high_freq_limit_reconnect": Def(C.centi, None, HR(1041)),
    "v_10min_protect": Def(C.deci, None, HR(1042), min=0.0, max=500.0),
    "pf_model": Def(C.uint16, PowerFactorFunctionModel, HR(1043)),
    "f_over_derate_start": Def(C.centi, None, HR(1045), min=40.0, max=70.0),
    "f_over_derate_slope": Def(C.uint16, None, HR(1046)),
    # HR(1047-1061) — reactive power / derating detail
    "q_lockin_power": Def(C.uint16, None, HR(1047)),
    "q_lock_out_power": Def(C.uint16, None, HR(1048)),
    "pf_lock_in_voltage": Def(C.deci, None, HR(1049), min=0.0, max=500.0),
    "pf_lock_out_voltage": Def(C.deci, None, HR(1050), min=0.0, max=500.0),
    "f_under_derate_slope": Def(C.milli, None, HR(1051)),
    "v_reactive_delay_time": Def(C.milli, None, HR(1052)),
    "time_over_freq_delay_time": Def(C.centi, None, HR(1053)),
    "pf_limit_load_1": Def(C.uint16, None, HR(1054)),
    "pf_limit_pf_1": Def(C.uint16, None, HR(1055)),
    "pf_limit_load_2": Def(C.uint16, None, HR(1056)),
    "pf_limit_pf_2": Def(C.uint16, None, HR(1057)),
    "pf_limit_load_3": Def(C.uint16, None, HR(1058)),
    "pf_limit_pf_3": Def(C.uint16, None, HR(1059)),
    "pf_limit_load_4": Def(C.uint16, None, HR(1060)),
    "pf_limit_pf_4": Def(C.uint16, None, HR(1061)),
    "f_under_derate_start": Def(C.centi, None, HR(1064), min=40.0, max=70.0),
    "f_under_derate_end": Def(C.centi, None, HR(1065), min=40.0, max=70.0),
    "f_over_derate_end": Def(C.centi, None, HR(1066), min=40.0, max=70.0),
    "time_under_freq_derate_delay": Def(C.centi, None, HR(1067)),
    # HR(1068) unused
    "f_over_derate_stop": Def(C.centi, None, HR(1069), min=40.0, max=70.0),
    "f_over_derate_recovery_delay": Def(C.centi, None, HR(1070)),
    "zero_current_low_voltage": Def(C.deci, None, HR(1071), min=0.0, max=500.0),
    "zero_current_high_voltage": Def(C.deci, None, HR(1072), min=0.0, max=500.0),
    "f_power_on_recovery": Def(C.centi, None, HR(1073), min=40.0, max=70.0),
    "f_under_derate_stop": Def(C.centi, None, HR(1074), min=40.0, max=70.0),
    "f_under_derate_recovery_delay": Def(C.centi, None, HR(1075)),
    "pv_input_mode": Def(C.uint16, None, HR(1077)),
    "p_export_limit": Def(C.deci, None, HR(1063), max=6500),
    "battery_reserve_soc": Def(C.uint16, None, HR(1078)),
    "ac_power_derate_delay": Def(C.centi, None, HR(1079)),
    # battery_type at HR(1080) shadows the single-phase HR(54)
    "battery_type": Def(C.uint16, BatteryType, HR(1080)),
    # HR(1081-1087): QU (volt-VAr) curve points and reactive-power limits. Newly decoded
    # from the GivEnergy app v4.0.7; raw uint16, scale unconfirmed on live hardware.
    "qu_curve_volt_high_point_1": Def(C.uint16, None, HR(1081)),
    "qu_curve_volt_high_point_2": Def(C.uint16, None, HR(1082)),
    "qu_curve_volt_low_point_1": Def(C.uint16, None, HR(1083)),
    "qu_curve_volt_low_point_2": Def(C.uint16, None, HR(1084)),
    "voltage_reactive_power_percentage": Def(C.uint16, None, HR(1085)),
    "qu_curve_max_inductive_reactive_power": Def(C.uint16, None, HR(1086)),
    "qu_curve_max_capacitive_reactive_power": Def(C.uint16, None, HR(1087)),
    "max_charge_current": Def(C.uint16, None, HR(1088)),
    "v_battery_lv": Def(C.deci, None, HR(1089), min=0.0, max=1000.0),
    "v_battery_cv": Def(C.deci, None, HR(1090), min=0.0, max=1000.0),
    "lead_acid_number": Def(C.deci, None, HR(1091)),
    "drms_enable": Def(C.bool, None, HR(1093)),
    "aging_test": Def(C.uint16, None, HR(1098)),
    "bypass_enable": Def(C.bool, None, HR(1100)),
    "npe_enable": Def(C.bool, None, HR(1101)),
    # HR(1102-1103): installer-tier export-limit pair from the GivEnergy app v4.0.7. Distinct
    # registers from p_export_limit (HR1063); the relationship between the two is unconfirmed.
    # set_enable_export_limit_3ph() writes HR1103, so it decodes as a bool.
    "export_power_limit": Def(C.uint16, None, HR(1102)),
    "enable_export_limit": Def(C.bool, None, HR(1103)),
    "unbalance_output_enable": Def(C.bool, None, HR(1104)),
    "backup_enable": Def(C.bool, None, HR(1105)),
    "v_backup_nominal": Def(C.nominal_voltage, None, HR(1106)),
    "f_backup_nominal": Def(C.nominal_frequency, None, HR(1107)),
    # battery_discharge_limit_ac at HR(1108) shadows single-phase HR(314)
    "battery_discharge_limit_ac": Def(C.uint16, None, HR(1108)),
    # battery_soc_reserve at HR(1109) shadows single-phase HR(110). The GE app 4.0.7 labels
    # this "Discharge Down To %" — same concept (the SOC floor discharge stops at), different
    # wording; kept as battery_soc_reserve for parity with the single-phase field.
    "battery_soc_reserve": Def(C.uint16, None, HR(1109)),
    # battery_charge_limit_ac at HR(1110) shadows single-phase HR(313)
    "battery_charge_limit_ac": Def(C.uint16, None, HR(1110)),
    # charge_target_soc at HR(1111) shadows single-phase HR(116)
    "charge_target_soc": Def(C.uint16, None, HR(1111)),
    # HR(1112) is AC_CHARGE_ENABLE per commands.RegisterMap — distinct semantically
    # from single-phase HR(96) (master ENABLE_CHARGE), so don't shadow that field name.
    "ac_charge_enable": Def(C.bool, None, HR(1112)),
    # charge_slot_1 at HR(1113/1114) shadows single-phase HR(94/95)
    "charge_slot_1": Def(C.timeslot, None, HR(1113), HR(1114)),
    # charge_slot_2 at HR(1115/1116) shadows single-phase HR(31/32)
    "charge_slot_2": Def(C.timeslot, None, HR(1115), HR(1116)),
    "load_compensation_enable": Def(C.bool, None, HR(1117)),
    # discharge_slot_1 at HR(1118/1119) shadows single-phase HR(56/57)
    "discharge_slot_1": Def(C.timeslot, None, HR(1118), HR(1119)),
    # discharge_slot_2 at HR(1120/1121) shadows single-phase HR(44/45)
    "discharge_slot_2": Def(C.timeslot, None, HR(1120), HR(1121)),
    # HR(1122) is FORCE_DISCHARGE_ENABLE per commands.RegisterMap — distinct semantically
    # from single-phase HR(59) (master ENABLE_DISCHARGE), so don't shadow that field name.
    "force_discharge_enable": Def(C.bool, None, HR(1122)),
    "force_charge_enable": Def(C.bool, None, HR(1123)),
    "battery_maintenance_mode": Def(C.uint16, BatteryMaintenance, HR(1124)),
    #
    # Input Registers 1001–1060 — PV
    #
    # v_pv1/v_pv2 at IR(1001/1002) shadow single-phase IR(1/2)
    "v_pv1": Def(C.deci, None, IR(1001), min=0.0, max=2000.0),
    "v_pv2": Def(C.deci, None, IR(1002), min=0.0, max=2000.0),
    # i_pv1/i_pv2 at IR(1009/1010) shadow single-phase IR(8/9)
    "i_pv1": Def(C.deci, None, IR(1009), min=0.0, max=500.0),
    "i_pv2": Def(C.deci, None, IR(1010), min=0.0, max=500.0),
    # p_pv1/p_pv2 at IR(1017-1020) are uint32+deci; single-phase is raw uint16
    "p_pv1": Def(C.uint32, C.deci, IR(1017), IR(1018), max=100000),
    "p_pv2": Def(C.uint32, C.deci, IR(1019), IR(1020), max=100000),
    #
    # Input Registers 1061–1099 — Grid
    #
    # v_ac1/i_ac1/f_ac1 shadow single-phase IR(5/10/13)
    "v_ac1": Def(C.deci, None, IR(1061), min=0.0, max=500.0),
    "v_ac2": Def(C.deci, None, IR(1062), min=0.0, max=500.0),
    "v_ac3": Def(C.deci, None, IR(1063), min=0.0, max=500.0),
    "i_ac1": Def(C.deci, None, IR(1064), min=0.0, max=500.0),
    "i_ac2": Def(C.deci, None, IR(1065), min=0.0, max=500.0),
    "i_ac3": Def(C.deci, None, IR(1066), min=0.0, max=500.0),
    # f_ac1 shadows single-phase IR(13)
    "f_ac1": Def(C.centi, None, IR(1067), min=40.0, max=70.0),
    # power_factor shadows single-phase HR(52); int16 here
    "power_factor": Def(C.int16, None, IR(1068)),
    "p_inverter_out": Def(C.int32, C.deci, IR(1069), IR(1070), min=-100000, max=100000),
    "p_inverter_ac_charge": Def(C.uint32, C.deci, IR(1071), IR(1072), max=100000),
    # p_grid_apparent shadows single-phase IR(43) (was uint16, now uint32+deci)
    "p_grid_apparent": Def(C.uint32, C.deci, IR(1073), IR(1074), max=100000),
    # system_mode shadows single-phase IR(49)
    "system_mode": Def(C.uint16, None, IR(1075)),
    # status shadows single-phase IR(0)
    "status": Def(C.uint16, Status, IR(1076)),
    "start_delay_time": Def(C.uint16, None, IR(1077)),
    "p_meter_import": Def(C.uint32, C.deci, IR(1079), IR(1080), max=100000),
    "p_meter_export": Def(C.uint32, C.deci, IR(1081), IR(1082), max=100000),
    "p_load_ac1": Def(C.deci, None, IR(1083), max=6500),
    "p_load_ac2": Def(C.deci, None, IR(1084), max=6500),
    "p_load_ac3": Def(C.deci, None, IR(1085), max=6500),
    "p_load_all": Def(C.uint32, C.deci, IR(1089), IR(1090), max=100000),
    "p_out_ac1": Def(C.deci, None, IR(1091), max=6500),
    "p_out_ac2": Def(C.deci, None, IR(1092), max=6500),
    "p_out_ac3": Def(C.deci, None, IR(1093), max=6500),
    "v_out_ac1": Def(C.deci, None, IR(1094), min=0.0, max=500.0),
    "v_out_ac2": Def(C.deci, None, IR(1095), min=0.0, max=500.0),
    "v_out_ac3": Def(C.deci, None, IR(1096), min=0.0, max=500.0),
    #
    # Input Registers 1120–1140 — Battery
    #
    "battery_priority": Def(C.uint16, None, IR(1120)),
    # battery_type (IR) at IR(1121) — read-only decoded value alongside HR(1080)
    "battery_type_ir": Def(C.uint16, BatteryType, IR(1121)),
    "dc_status": Def(C.uint16, Status, IR(1124)),
    "t_inverter": Def(C.deci, None, IR(1128), min=-60.0, max=150.0),
    "t_boost": Def(C.deci, None, IR(1129), min=-60.0, max=150.0),
    "t_buck_boost": Def(C.deci, None, IR(1130), min=-60.0, max=150.0),
    "v_battery_bms": Def(C.deci, None, IR(1131), min=0.0, max=1000.0),
    # battery_soc shadows single-phase IR(59)
    "battery_soc": Def(C.uint16, None, IR(1132), min=0, max=100),
    "v_battery_pcs": Def(C.deci, None, IR(1133), min=0.0, max=1000.0),
    "v_dc_bus": Def(C.deci, None, IR(1134)),
    "v_inv_bus": Def(C.deci, None, IR(1135)),
    "p_battery_discharge": Def(C.uint32, C.deci, IR(1136), IR(1137), max=100000),
    "p_battery_charge": Def(C.uint32, C.deci, IR(1138), IR(1139), max=100000),
    # i_battery shadows single-phase IR(51); same converter and scale (centi).
    # Field-confirmed centi against a GIV-3HY-11 HV capture (V×I vs p_battery_charge).
    # Bounds match single-phase (±300 A); a centi-scaled int16 caps at ±327.67 anyway.
    "i_battery": Def(C.int16, C.centi, IR(1140), min=-300.0, max=300.0),
    #
    # Input Registers 1180–1192 — EPS
    #
    "f_nominal_eps": Def(C.centi, None, IR(1180), min=40.0, max=70.0),
    "v_eps_ac1": Def(C.deci, None, IR(1181), min=0.0, max=500.0),
    "v_eps_ac2": Def(C.deci, None, IR(1182), min=0.0, max=500.0),
    "v_eps_ac3": Def(C.deci, None, IR(1183), min=0.0, max=500.0),
    "i_eps_ac1": Def(C.deci, None, IR(1184), min=0.0, max=500.0),
    "i_eps_ac2": Def(C.deci, None, IR(1185), min=0.0, max=500.0),
    "i_eps_ac3": Def(C.deci, None, IR(1186), min=0.0, max=500.0),
    "p_eps_ac1": Def(C.uint32, C.deci, IR(1187), IR(1188), max=100000),
    "p_eps_ac2": Def(C.uint32, C.deci, IR(1189), IR(1190), max=100000),
    "p_eps_ac3": Def(C.uint32, C.deci, IR(1191), IR(1192), max=100000),
    #
    # Input Registers 1240–1245 — Additional power meters
    #
    "p_export": Def(C.uint32, C.deci, IR(1240), IR(1241), max=100000),
    "p_meter2": Def(C.uint32, C.deci, IR(1244), IR(1245), max=100000),
    #
    # Input Registers 1300–1307 — Fault codes decoded per word
    #
    "inverter_fault_codes_0": Def((_inverter_fault_code2, 0), None, IR(1300)),
    "inverter_fault_codes_1": Def((_inverter_fault_code2, 1), None, IR(1301)),
    "inverter_fault_codes_2": Def((_inverter_fault_code2, 2), None, IR(1302)),
    "inverter_fault_codes_3": Def((_inverter_fault_code2, 3), None, IR(1303)),
    "inverter_fault_codes_4": Def((_inverter_fault_code2, 4), None, IR(1304)),
    "inverter_fault_codes_5": Def((_inverter_fault_code2, 5), None, IR(1305)),
    "inverter_fault_codes_6": Def((_inverter_fault_code2, 6), None, IR(1306)),
    "inverter_fault_codes_7": Def((_inverter_fault_code2, 7), None, IR(1307)),
    #
    # Input Registers 1317–1327 — Firmware identification
    #
    "tph_software_version": Def(C.string, None, IR(1317), IR(1318), IR(1319)),
    "tph_firmware_version": Def(C.string, None, IR(1320), IR(1321), IR(1322), IR(1323), IR(1324)),
    "ac_dsp_firmware_version": Def(C.uint16, None, IR(1325)),
    "dc_dsp_firmware_version": Def(C.uint16, None, IR(1326)),
    "tph_arm_firmware_version": Def(C.uint16, None, IR(1327)),
    # firmware_version shadows single-phase HR(19)+HR(21); same converter, different registers
    "firmware_version": Def(C.firmware_version, None, IR(1325), IR(1327)),
    #
    # Input Registers 1360–1413 — Energy totals
    #
    "e_inverter_out_today": Def(C.uint32, C.deci, IR(1360), IR(1361)),
    "e_inverter_out_total": Def(C.uint32, C.deci, IR(1362), IR(1363)),
    "e_pv1_today": Def(C.uint32, C.deci, IR(1366), IR(1367)),
    "e_pv1_total": Def(C.uint32, C.deci, IR(1368), IR(1369)),
    "e_pv2_today": Def(C.uint32, C.deci, IR(1370), IR(1371)),
    "e_pv2_total": Def(C.uint32, C.deci, IR(1372), IR(1373)),
    "e_pv_total": Def(C.uint32, C.deci, IR(1374), IR(1375)),
    "e_ac_charge_today": Def(C.uint32, C.deci, IR(1376), IR(1377)),
    "e_ac_charge_total": Def(C.uint32, C.deci, IR(1378), IR(1379)),
    "e_import_today": Def(C.uint32, C.deci, IR(1380), IR(1381)),
    "e_import_total": Def(C.uint32, C.deci, IR(1382), IR(1383)),
    "e_export_today": Def(C.uint32, C.deci, IR(1384), IR(1385)),
    "e_export_total": Def(C.uint32, C.deci, IR(1386), IR(1387)),
    "e_battery_discharge_today": Def(C.uint32, C.deci, IR(1388), IR(1389)),
    "e_battery_discharge_total": Def(C.uint32, C.deci, IR(1390), IR(1391)),
    "e_battery_charge_today": Def(C.uint32, C.deci, IR(1392), IR(1393)),
    "e_battery_charge_total": Def(C.uint32, C.deci, IR(1394), IR(1395)),
    "e_load_today": Def(C.uint32, C.deci, IR(1396), IR(1397)),
    "e_load_total": Def(C.uint32, C.deci, IR(1398), IR(1399)),
    "e_export2_today": Def(C.uint32, C.deci, IR(1400), IR(1401)),
    "e_export2_total": Def(C.uint32, C.deci, IR(1402), IR(1403)),
    "e_pv_today": Def(C.uint32, C.deci, IR(1412), IR(1413)),
}


class ThreePhaseInverterRegisterGetter(RegisterGetter):
    """Structured format for three-phase inverter attributes.

    Merges the single-phase SinglePhaseInverterRegisterGetter LUT with three-phase-specific
    registers. Three-phase entries win for any key that appears in both (e.g.
    battery_soc moves from IR(59) to IR(1132)).

    p_battery and e_battery_throughput are dropped from the merged LUT: on three-phase
    they are DERIVED @computed_field properties on ThreePhaseInverter (from the native
    p_battery_charge/discharge and the charge/discharge energy totals). Left register-backed
    they would inherit single-phase IR(52) / IR(6,7), which three-phase firmware does not
    populate (they read frozen) — and a generated pydantic field cannot be shadowed by a
    same-named computed_field.

    The single-phase-only HR(101-104) names (grid_import_limit / _enabled / enable_lora /
    enable_battery_self_heating) are also dropped: the merge is keyed by field name, not
    address, so without this they would coexist with the three-phase grid_r/s/t_voltage_
    adjustment overrides — eight fields for four registers. On three-phase these addresses
    only carry the R/S/T meaning.
    """

    REGISTER_LUT = {
        k: v
        for k, v in dict(SinglePhaseInverterRegisterGetter.REGISTER_LUT, **_THREE_PHASE_LUT).items()
        if k not in _DROP_ON_THREE_PHASE
    }


_ThreePhaseInverterBase = create_model(  # type: ignore[call-overload]
    "ThreePhaseInverter",
    __config__=ConfigDict(frozen=True),
    **ThreePhaseInverterRegisterGetter.to_fields(),
)


# THREE_PHASE_SLOTS lives in model.slot_map alongside the single-phase variants.
# Re-exported here for backward compatibility.
from givenergy_modbus.model.slot_map import THREE_PHASE_SLOTS  # noqa: E402


class ThreePhaseInverter(  # type: ignore[valid-type,misc]
    _ThreePhaseInverterBase, _ThreePhaseCommands, _InverterCommands, RegisterMetadataMixin
):
    """GivEnergy three-phase inverter data model.

    Composes the `_InverterCommands` base mixin alongside `_ThreePhaseCommands`
    (which adds `set_ac_charge`, `set_force_charge`, `set_force_discharge` and
    their HR(1112/1122/1123) allowlist entries). MRO puts `_ThreePhaseCommands`
    first so the three-phase `WRITE_SAFE_REGISTERS` (a superset) wins. Methods
    on the two mixins are disjoint so the resolution order doesn't matter for
    behaviour.
    """

    REGISTER_GETTER: ClassVar[type[RegisterGetter]] = ThreePhaseInverterRegisterGetter

    @classmethod
    def from_register_cache(cls, register_cache) -> "ThreePhaseInverter":
        """Construct a ThreePhaseInverter from a RegisterCache."""
        return cls.model_validate(ThreePhaseInverterRegisterGetter(register_cache).build())

    def p_pv(self) -> int | None:
        """Computes the total PV power across both strings, or None if either is unavailable."""
        if self.p_pv1 is None or self.p_pv2 is None:  # type: ignore[attr-defined]
            return None
        return self.p_pv1 + self.p_pv2  # type: ignore[attr-defined]

    def e_pv_day(self) -> float | None:
        """Returns the combined PV energy for the day from the dedicated three-phase register."""
        return self.e_pv_today  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def battery_capacity_kwh(self) -> float | None:
        """Returns the nominal battery capacity in kWh, derived from Ah and model voltage."""
        if self.battery_capacity_ah is None or self.model is None:  # type: ignore[attr-defined]
            return None
        return self.battery_capacity_ah * self.model.system_battery_voltage / 1000  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def battery_max_power(self) -> int | None:
        """Returns the rated battery charge/discharge power in watts, derived from model and firmware."""
        return _battery_max_power(self.device_type_code, self.arm_firmware_version)  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def inverter_max_power(self) -> int | None:
        """Returns the rated inverter power in watts, derived from the device type code."""
        return _DTC_RATED_POWER.get(self.device_type_code)  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_ac_coupled(self) -> bool:
        """True for AC-coupled inverters (no integrated DC battery).

        True for Model.AC_3PH on three-phase; False when the model is unknown.
        Mirrors the field on SinglePhaseInverter (not inherited — the two inverter
        classes are parallel, like battery_max_power / inverter_max_power above).
        """
        return self.model in AC_COUPLED_MODELS  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def grid_import_power(self) -> float | None:
        """Non-negative grid import power (W); aliases p_meter_import (#205)."""
        return self.p_meter_import  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def grid_export_power(self) -> float | None:
        """Non-negative grid export power (W); aliases p_meter_export (#205)."""
        return self.p_meter_export  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def battery_charge_power(self) -> float | None:
        """Non-negative battery charge power (W); aliases p_battery_charge (#205)."""
        return self.p_battery_charge  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def battery_discharge_power(self) -> float | None:
        """Non-negative battery discharge power (W); aliases p_battery_discharge (#205)."""
        return self.p_battery_discharge  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def p_battery(self) -> float | None:
        """Net battery power (W); +ve = discharging, −ve = charging (#262).

        Derived from the native p_battery_discharge − p_battery_charge registers; the
        inherited single-phase IR(52) reads frozen on three-phase firmware. Sign matches
        single-phase, where battery_discharge_power = max(0, p_battery). Returns None if
        either input is None.
        """
        if self.p_battery_discharge is None or self.p_battery_charge is None:  # type: ignore[attr-defined]
            return None
        return self.p_battery_discharge - self.p_battery_charge  # type: ignore[attr-defined]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def e_battery_throughput(self) -> float | None:
        """Total battery energy throughput (kWh): charge_total + discharge_total (#262).

        Derived from the native energy totals (IR1394/5 + IR1390/1); the inherited
        single-phase e_battery_throughput (IR6/7) reads frozen on three-phase firmware.
        Returns None if either input is None.
        """
        if self.e_battery_charge_total is None or self.e_battery_discharge_total is None:  # type: ignore[attr-defined]
            return None
        return self.e_battery_charge_total + self.e_battery_discharge_total  # type: ignore[attr-defined]

    @property
    def slot_map(self) -> SlotMap:
        """Register address pairs for the charge/discharge time slots on this model."""
        return THREE_PHASE_SLOTS

    # Plain @property (not @computed_field) so the deprecated alias doesn't
    # appear in model_dump() output. See #84 — renamed to work_time_total_hours
    # to put the unit at the call site.
    @property
    def work_time_total(self) -> int | None:
        """Deprecated alias for `work_time_total_hours`."""
        warnings.warn(
            "ThreePhaseInverter.work_time_total is deprecated; use work_time_total_hours",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.work_time_total_hours  # type: ignore[attr-defined,no-any-return]

    @property
    def enable_standard_self_consumption_logic(self) -> bool | None:
        """Deprecated alias for `enable_inverter_parallel_mode`."""
        warnings.warn(
            "ThreePhaseInverter.enable_standard_self_consumption_logic is deprecated; "
            "use enable_inverter_parallel_mode",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.enable_inverter_parallel_mode  # type: ignore[attr-defined,no-any-return]

    # IR(44) was decoded as e_inverter_out_day (GivTCP-era guess); sentinel
    # cross-correlation (#174) confirmed it is PV-generation-today. Renamed to
    # e_pv_generation_today (inherited from the single-phase LUT, IR44); this alias
    # preserves back-compat. Note: the verified three-phase PV-generation register is
    # e_pv_today (IR1412/3) — IR(44) leaks via single-phase inheritance and is
    # unverified on three-phase hardware (see #48).
    @property
    def e_inverter_out_day(self) -> float | None:
        """Deprecated alias — returns `e_pv_today` (IR1412/1413), the verified three-phase PV-generation register.

        The old name is a GivTCP-era mislabel.

        The old `e_inverter_out_day` name was a GivTCP-era mislabel; IR44
        (`e_pv_generation_today`) leaks via single-phase LUT inheritance and is
        unverified on three-phase hardware. This alias returns `e_pv_today`
        directly so consumers following the deprecation warning get the same
        value they were reading via the alias.
        """
        warnings.warn(
            "ThreePhaseInverter.e_inverter_out_day is deprecated; use e_pv_today",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.e_pv_today  # type: ignore[attr-defined,no-any-return]

    # HR(1078) was named battery_power_cutoff (implying a power value in watts), but
    # the GE app confirms it is "Battery Reserve %" — an SOC percentage. Renamed to
    # battery_reserve_soc; this alias preserves back-compat for a release.
    @property
    def battery_power_cutoff(self) -> int | None:
        """Deprecated alias for `battery_reserve_soc`."""
        warnings.warn(
            "ThreePhaseInverter.battery_power_cutoff is deprecated; use battery_reserve_soc",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.battery_reserve_soc  # type: ignore[attr-defined,no-any-return]

    # HR(1018-1041) renamed: _1/_2/_3 → _trip/_reconnect/_grid (installer-confirmed band structure).
    # Aliases preserve back-compat for a release.

    @property
    def v_grid_low_limit_1(self) -> float | None:
        """Deprecated alias for `v_grid_low_limit_trip`."""
        warnings.warn(
            "ThreePhaseInverter.v_grid_low_limit_1 is deprecated; use v_grid_low_limit_trip",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.v_grid_low_limit_trip  # type: ignore[attr-defined,no-any-return]

    @property
    def v_grid_high_limit_1(self) -> float | None:
        """Deprecated alias for `v_grid_high_limit_trip`."""
        warnings.warn(
            "ThreePhaseInverter.v_grid_high_limit_1 is deprecated; use v_grid_high_limit_trip",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.v_grid_high_limit_trip  # type: ignore[attr-defined,no-any-return]

    @property
    def f_grid_low_limit_1(self) -> float | None:
        """Deprecated alias for `f_grid_low_limit_trip`."""
        warnings.warn(
            "ThreePhaseInverter.f_grid_low_limit_1 is deprecated; use f_grid_low_limit_trip",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.f_grid_low_limit_trip  # type: ignore[attr-defined,no-any-return]

    @property
    def f_grid_high_limit_1(self) -> float | None:
        """Deprecated alias for `f_grid_high_limit_trip`."""
        warnings.warn(
            "ThreePhaseInverter.f_grid_high_limit_1 is deprecated; use f_grid_high_limit_trip",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.f_grid_high_limit_trip  # type: ignore[attr-defined,no-any-return]

    @property
    def v_grid_low_limit_2(self) -> float | None:
        """Deprecated alias for `v_grid_low_limit_reconnect`."""
        warnings.warn(
            "ThreePhaseInverter.v_grid_low_limit_2 is deprecated; use v_grid_low_limit_reconnect",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.v_grid_low_limit_reconnect  # type: ignore[attr-defined,no-any-return]

    @property
    def v_grid_high_limit_2(self) -> float | None:
        """Deprecated alias for `v_grid_high_limit_reconnect`."""
        warnings.warn(
            "ThreePhaseInverter.v_grid_high_limit_2 is deprecated; use v_grid_high_limit_reconnect",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.v_grid_high_limit_reconnect  # type: ignore[attr-defined,no-any-return]

    @property
    def f_grid_low_limit_2(self) -> float | None:
        """Deprecated alias for `f_grid_low_limit_reconnect`."""
        warnings.warn(
            "ThreePhaseInverter.f_grid_low_limit_2 is deprecated; use f_grid_low_limit_reconnect",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.f_grid_low_limit_reconnect  # type: ignore[attr-defined,no-any-return]

    @property
    def f_grid_high_limit_2(self) -> float | None:
        """Deprecated alias for `f_grid_high_limit_reconnect`."""
        warnings.warn(
            "ThreePhaseInverter.f_grid_high_limit_2 is deprecated; use f_grid_high_limit_reconnect",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.f_grid_high_limit_reconnect  # type: ignore[attr-defined,no-any-return]

    @property
    def v_grid_low_limit_3(self) -> float | None:
        """Deprecated alias for `v_grid_low_limit_grid`."""
        warnings.warn(
            "ThreePhaseInverter.v_grid_low_limit_3 is deprecated; use v_grid_low_limit_grid",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.v_grid_low_limit_grid  # type: ignore[attr-defined,no-any-return]

    @property
    def v_grid_high_limit_3(self) -> float | None:
        """Deprecated alias for `v_grid_high_limit_grid`."""
        warnings.warn(
            "ThreePhaseInverter.v_grid_high_limit_3 is deprecated; use v_grid_high_limit_grid",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.v_grid_high_limit_grid  # type: ignore[attr-defined,no-any-return]

    @property
    def f_grid_low_limit_3(self) -> float | None:
        """Deprecated alias for `f_grid_low_limit_grid`."""
        warnings.warn(
            "ThreePhaseInverter.f_grid_low_limit_3 is deprecated; use f_grid_low_limit_grid",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.f_grid_low_limit_grid  # type: ignore[attr-defined,no-any-return]

    @property
    def f_grid_high_limit_3(self) -> float | None:
        """Deprecated alias for `f_grid_high_limit_grid`."""
        warnings.warn(
            "ThreePhaseInverter.f_grid_high_limit_3 is deprecated; use f_grid_high_limit_grid",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.f_grid_high_limit_grid  # type: ignore[attr-defined,no-any-return]

    @property
    def time_grid_low_voltage_limit_1(self) -> float | None:
        """Deprecated alias for `time_grid_low_voltage_limit_trip`."""
        warnings.warn(
            "ThreePhaseInverter.time_grid_low_voltage_limit_1 is deprecated; use time_grid_low_voltage_limit_trip",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.time_grid_low_voltage_limit_trip  # type: ignore[attr-defined,no-any-return]

    @property
    def time_grid_high_voltage_limit_1(self) -> float | None:
        """Deprecated alias for `time_grid_high_voltage_limit_trip`."""
        warnings.warn(
            "ThreePhaseInverter.time_grid_high_voltage_limit_1 is deprecated; use time_grid_high_voltage_limit_trip",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.time_grid_high_voltage_limit_trip  # type: ignore[attr-defined,no-any-return]

    @property
    def time_grid_low_voltage_limit_2(self) -> float | None:
        """Deprecated alias for `time_grid_low_voltage_limit_reconnect`."""
        warnings.warn(
            "ThreePhaseInverter.time_grid_low_voltage_limit_2 is deprecated; use time_grid_low_voltage_limit_reconnect",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.time_grid_low_voltage_limit_reconnect  # type: ignore[attr-defined,no-any-return]

    @property
    def time_grid_high_voltage_limit_2(self) -> float | None:
        """Deprecated alias for `time_grid_high_voltage_limit_reconnect`."""
        warnings.warn(
            "ThreePhaseInverter.time_grid_high_voltage_limit_2 is deprecated; "
            "use time_grid_high_voltage_limit_reconnect",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.time_grid_high_voltage_limit_reconnect  # type: ignore[attr-defined,no-any-return]

    @property
    def time_grid_low_freq_limit_1(self) -> float | None:
        """Deprecated alias for `time_grid_low_freq_limit_trip`."""
        warnings.warn(
            "ThreePhaseInverter.time_grid_low_freq_limit_1 is deprecated; use time_grid_low_freq_limit_trip",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.time_grid_low_freq_limit_trip  # type: ignore[attr-defined,no-any-return]

    @property
    def time_grid_high_freq_limit_1(self) -> float | None:
        """Deprecated alias for `time_grid_high_freq_limit_trip`."""
        warnings.warn(
            "ThreePhaseInverter.time_grid_high_freq_limit_1 is deprecated; use time_grid_high_freq_limit_trip",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.time_grid_high_freq_limit_trip  # type: ignore[attr-defined,no-any-return]

    @property
    def time_grid_low_freq_limit_2(self) -> float | None:
        """Deprecated alias for `time_grid_low_freq_limit_reconnect`."""
        warnings.warn(
            "ThreePhaseInverter.time_grid_low_freq_limit_2 is deprecated; use time_grid_low_freq_limit_reconnect",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.time_grid_low_freq_limit_reconnect  # type: ignore[attr-defined,no-any-return]

    @property
    def time_grid_high_freq_limit_2(self) -> float | None:
        """Deprecated alias for `time_grid_high_freq_limit_reconnect`."""
        warnings.warn(
            "ThreePhaseInverter.time_grid_high_freq_limit_2 is deprecated; use time_grid_high_freq_limit_reconnect",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.time_grid_high_freq_limit_reconnect  # type: ignore[attr-defined,no-any-return]


# Models that decode via the three-phase / 1000-range register layout. The residential
# ALL_IN_ONE (DTC family "8", e.g. 0x8001) is deliberately absent: it is HV but single-
# phase, and decoding it as ThreePhaseInverter shadows ~30 live fields (battery_soc, v_ac1,
# f_ac1, firmware, charge slots, status…) to IR/HR(1000+) addresses it doesn't expose,
# zeroing them. It carries its data in the single-phase IR(0)/IR(180) banks and so decodes
# correctly as SinglePhaseInverter. Verified against real AIO register dumps (#105). HV
# battery voltage, extended slots and is_hv stay model-keyed at the capabilities layer.
THREE_PHASE_MODELS: frozenset[Model] = frozenset(
    {
        Model.HYBRID_3PH,
        Model.AC_3PH,
        Model.AIO_COMMERCIAL,
        Model.HYBRID_HV_GEN3,
        Model.ALL_IN_ONE_HYBRID,
    }
)


def select_inverter(model: Model, register_cache) -> "SinglePhaseInverter | ThreePhaseInverter":
    """Return the appropriate inverter model instance for the given device model.

    Genuinely three-phase and HV-hybrid units use the 1000-range register address layout;
    everything else — including the residential single-phase ALL_IN_ONE — uses the
    single-phase layout (see THREE_PHASE_MODELS for why the AIO is excluded).
    """
    if model in THREE_PHASE_MODELS:
        return ThreePhaseInverter.from_register_cache(register_cache)
    return SinglePhaseInverter.from_register_cache(register_cache)
