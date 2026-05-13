"""GivEnergy three-phase inverter data model."""

from pydantic import ConfigDict, create_model

from givenergy_modbus.model.battery import BatteryMaintenance
from givenergy_modbus.model.inverter import (
    BatteryType,
    Model,
    PowerFactorFunctionModel,
    SinglePhaseInverter,
    SinglePhaseInverterRegisterGetter,
    SlotMap,
    Status,
)
from givenergy_modbus.model.register import HR, IR, RegisterGetter
from givenergy_modbus.model.register import Converter as C
from givenergy_modbus.model.register import RegisterDefinition as Def

# Registers that are three-phase specific or that shadow single-phase registers at higher addresses.
# When merged with InverterRegisterGetter.REGISTER_LUT these entries win (dict update semantics).
_THREE_PHASE_LUT = {
    #
    # Holding Registers 1001–1124 — Three-Phase configuration
    #
    "set_command_save": Def(C.bool, None, HR(1001)),
    "active_rate": Def(C.uint16, None, HR(1002)),
    "reactive_rate": Def(C.uint16, None, HR(1003)),
    "set_power_factor": Def(C.uint16, None, HR(1004)),
    "grid_connect_time": Def(C.uint16, None, HR(1007)),
    "grid_reconnect_time": Def(C.uint16, None, HR(1008)),
    "v_grid_low_limit_1": Def(C.deci, None, HR(1018), min=0.0, max=500.0),
    "v_grid_high_limit_1": Def(C.deci, None, HR(1019), min=0.0, max=500.0),
    "f_grid_low_limit_1": Def(C.centi, None, HR(1020), min=40.0, max=70.0),
    "f_grid_high_limit_1": Def(C.centi, None, HR(1021), min=40.0, max=70.0),
    "v_grid_low_limit_2": Def(C.deci, None, HR(1022), min=0.0, max=500.0),
    "v_grid_high_limit_2": Def(C.deci, None, HR(1023), min=0.0, max=500.0),
    "f_grid_low_limit_2": Def(C.centi, None, HR(1024), min=40.0, max=70.0),
    "f_grid_high_limit_2": Def(C.centi, None, HR(1025), min=40.0, max=70.0),
    "v_grid_low_limit_3": Def(C.deci, None, HR(1026), min=0.0, max=500.0),
    "v_grid_high_limit_3": Def(C.deci, None, HR(1027), min=0.0, max=500.0),
    "f_grid_low_limit_3": Def(C.centi, None, HR(1028), min=40.0, max=70.0),
    "f_grid_high_limit_3": Def(C.centi, None, HR(1029), min=40.0, max=70.0),
    # HR(1030-1033) — CEE grid limits
    "v_grid_low_limit_cee": Def(C.deci, None, HR(1030), min=0.0, max=500.0),
    "v_grid_high_limit_cee": Def(C.deci, None, HR(1031), min=0.0, max=500.0),
    "f_grid_low_limit_cee": Def(C.centi, None, HR(1032), min=40.0, max=70.0),
    "f_grid_high_limit_cee": Def(C.centi, None, HR(1033), min=40.0, max=70.0),
    # HR(1034-1041) — time-based grid voltage/frequency limits
    "time_grid_low_voltage_limit_1": Def(C.centi, None, HR(1034)),
    "time_grid_high_voltage_limit_1": Def(C.centi, None, HR(1035)),
    "time_grid_low_voltage_limit_2": Def(C.centi, None, HR(1036)),
    "time_grid_high_voltage_limit_2": Def(C.centi, None, HR(1037)),
    "time_grid_low_freq_limit_1": Def(C.centi, None, HR(1038)),
    "time_grid_high_freq_limit_1": Def(C.centi, None, HR(1039)),
    "time_grid_low_freq_limit_2": Def(C.centi, None, HR(1040)),
    "time_grid_high_freq_limit_2": Def(C.centi, None, HR(1041)),
    "v_10min_protect": Def(C.deci, None, HR(1042), min=0.0, max=500.0),
    "pf_model": Def(C.uint16, PowerFactorFunctionModel, HR(1043)),
    "f_over_derate_start": Def(C.centi, None, HR(1045), min=40.0, max=70.0),
    "f_over_derate_slope": Def(C.uint16, None, HR(1046)),
    # HR(1047-1061) — reactive power / derating detail
    "q_lockin_power": Def(C.uint16, None, HR(1047)),
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
    "p_export_limit": Def(C.deci, None, HR(1063), max=6500),
    "battery_power_cutoff": Def(C.uint16, None, HR(1078)),
    "ac_power_derate_delay": Def(C.centi, None, HR(1079)),
    # battery_type at HR(1080) shadows the single-phase HR(54)
    "battery_type": Def(C.uint16, BatteryType, HR(1080)),
    "max_charge_current": Def(C.uint16, None, HR(1088)),
    "v_battery_lv": Def(C.deci, None, HR(1089), min=0.0, max=1000.0),
    "v_battery_cv": Def(C.deci, None, HR(1090), min=0.0, max=1000.0),
    "lead_acid_number": Def(C.deci, None, HR(1091)),
    "drms_enable": Def(C.bool, None, HR(1093)),
    "aging_test": Def(C.uint16, None, HR(1098)),
    "bypass_enable": Def(C.bool, None, HR(1100)),
    "npe_enable": Def(C.bool, None, HR(1101)),
    "unbalance_output_enable": Def(C.bool, None, HR(1104)),
    "backup_enable": Def(C.bool, None, HR(1105)),
    "v_backup_nominal": Def(C.nominal_voltage, None, HR(1106)),
    "f_backup_nominal": Def(C.nominal_frequency, None, HR(1107)),
    # battery_discharge_limit_ac at HR(1108) shadows single-phase HR(314)
    "battery_discharge_limit_ac": Def(C.uint16, None, HR(1108)),
    # battery_soc_reserve at HR(1109) shadows single-phase HR(110)
    "battery_soc_reserve": Def(C.uint16, None, HR(1109)),
    # battery_charge_limit_ac at HR(1110) shadows single-phase HR(313)
    "battery_charge_limit_ac": Def(C.uint16, None, HR(1110)),
    # charge_target_soc at HR(1111) shadows single-phase HR(116)
    "charge_target_soc": Def(C.uint16, None, HR(1111)),
    # enable_charge at HR(1112) shadows single-phase HR(96)
    "enable_charge": Def(C.bool, None, HR(1112)),
    # charge_slot_1 at HR(1113/1114) shadows single-phase HR(94/95)
    "charge_slot_1": Def(C.timeslot, None, HR(1113), HR(1114)),
    # charge_slot_2 at HR(1115/1116) shadows single-phase HR(31/32)
    "charge_slot_2": Def(C.timeslot, None, HR(1115), HR(1116)),
    "load_compensation_enable": Def(C.bool, None, HR(1117)),
    # discharge_slot_1 at HR(1118/1119) shadows single-phase HR(56/57)
    "discharge_slot_1": Def(C.timeslot, None, HR(1118), HR(1119)),
    # discharge_slot_2 at HR(1120/1121) shadows single-phase HR(44/45)
    "discharge_slot_2": Def(C.timeslot, None, HR(1120), HR(1121)),
    # enable_discharge at HR(1122) shadows single-phase HR(59)
    "enable_discharge": Def(C.bool, None, HR(1122)),
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
    # i_battery shadows single-phase IR(51); same converter, different scale
    "i_battery": Def(C.int16, C.deci, IR(1140), min=-500.0, max=500.0),
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
    # Input Registers 1300–1307 — Fault codes (raw; decode separately if needed)
    #
    "inverter_fault_code_0": Def(C.uint16, None, IR(1300)),
    "inverter_fault_code_1": Def(C.uint16, None, IR(1301)),
    "inverter_fault_code_2": Def(C.uint16, None, IR(1302)),
    "inverter_fault_code_3": Def(C.uint16, None, IR(1303)),
    "inverter_fault_code_4": Def(C.uint16, None, IR(1304)),
    "inverter_fault_code_5": Def(C.uint16, None, IR(1305)),
    "inverter_fault_code_6": Def(C.uint16, None, IR(1306)),
    "inverter_fault_code_7": Def(C.uint16, None, IR(1307)),
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
    """

    REGISTER_LUT = dict(SinglePhaseInverterRegisterGetter.REGISTER_LUT, **_THREE_PHASE_LUT)


_ThreePhaseInverterBase = create_model(  # type: ignore[call-overload]
    "ThreePhaseInverter",
    __config__=ConfigDict(frozen=True),
    **ThreePhaseInverterRegisterGetter.to_fields(),
)


THREE_PHASE_SLOTS = SlotMap(
    charge_slots=((1113, 1114), (1115, 1116)),
    discharge_slots=((1118, 1119), (1120, 1121)),
)


class ThreePhaseInverter(_ThreePhaseInverterBase):  # type: ignore[valid-type,misc]
    """GivEnergy three-phase inverter data model."""

    @classmethod
    def from_register_cache(cls, register_cache) -> "ThreePhaseInverter":
        """Construct a ThreePhaseInverter from a RegisterCache."""
        return cls.model_validate(ThreePhaseInverterRegisterGetter(register_cache).build())

    @property
    def slot_map(self) -> SlotMap:
        """Register address pairs for the charge/discharge time slots on this model."""
        return THREE_PHASE_SLOTS


THREE_PHASE_MODELS: frozenset[Model] = frozenset(
    {
        Model.HYBRID_3PH,
        Model.AC_3PH,
        Model.AIO_COMMERCIAL,
        Model.ALL_IN_ONE,
        Model.HYBRID_HV_GEN3,
        Model.ALL_IN_ONE_HYBRID,
    }
)


def select_inverter(model: Model, register_cache) -> "SinglePhaseInverter | ThreePhaseInverter":
    """Return the appropriate inverter model instance for the given device model.

    Three-phase and AIO/HV units use a different register address layout;
    everything else uses the single-phase layout.
    """
    if model in THREE_PHASE_MODELS:
        return ThreePhaseInverter.from_register_cache(register_cache)
    return SinglePhaseInverter.from_register_cache(register_cache)
