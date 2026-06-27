# Writable registers

This document covers the full write surface of the GivEnergy Modbus library: which
holding registers can be written, at what tier, through which API entry point, and what
is known about their effect.

## Provenance

The primary source is the GivEnergy Android app v4.0.7 "Direct Control" tab, which
exposes the manufacturer's own writable-register map for end users (post–cloud-portal
retirement) and a separate installer-login surface.  The app is Flutter-based; its
full holding-register write map (460 entries) and per-model telemetry-kind table live
in the Dart AOT snapshot inside `libapp.so` and were extracted via
[blutter](https://github.com/worawit/blutter) without requiring hardware or a live
cloud connection.  The v4.1.6 hybrid Modbus RTU protocol document (2024-10-30) provides
supplementary context; a parsed inventory lives in `docs/reference/registers/`.

GivEnergy entered administration in 2025.  No further firmware or documentation
updates are expected, which makes the app-binary extraction the most authoritative
source likely to exist.

## Write tiers

The library enforces two independent gates around every write.

**Gate 1 (client):** `Client.one_shot_command()` validates that each request is in the
per-model safe set before dispatching.  `Client.installer_command()` extends that set
to include `INSTALLER_WRITE_REGISTERS`, but is never used by `one_shot_command()`.

**Gate 2 (PDU):** `WriteHoldingRegisterRequest.ensure_valid_state()` — called
automatically during encode — checks the register against the appropriate allow-list.
A request constructed without `installer=True` is rejected if its register is not in
`WRITE_SAFE_REGISTERS`; one constructed with `installer=True` is rejected if it is not
in `INSTALLER_WRITE_REGISTERS`.  The two sets are disjoint by design.

| Tier | Entry point | Register set | Typical use |
|---|---|---|---|
| Standard | `one_shot_command()` | `WRITE_SAFE_REGISTERS` | Charge slots, SOC limits, mode switches, EMS scheduling |
| Installer — config | `installer_command()` | `INSTALLER_WRITE_REGISTERS` (non-destructive) | Grid-protection limits, battery commissioning, hardware enables |
| Installer — destructive | `installer_command()` | `INSTALLER_WRITE_REGISTERS` (destructive group) | Factory reset, energy-total reset, black-start |

!!! warning "Installer tier — read before use"
    Installer registers control grid-safety parameters, hardware operating modes, and
    factory configuration.  Incorrect values can leave a site operating outside
    grid-code tolerances, prevent battery charging, or — for the destructive group —
    wipe all installer configuration irreversibly.

    - Always obtain a baseline read of the current register value before writing.
    - Apply changes incrementally and verify telemetry after each step.
    - The destructive command helpers (`restore_factory_defaults`, `reset_energy_totals`,
      `three_phase_factory_reset`, `enable_black_start`) require `confirm=True` and will
      raise `ValueError` without it.  This is intentional — there is no undo.
    - The original motivation for exposing this tier: with GivEnergy in administration
      there is no longer a field-engineer path to correct a factory-misconfigured
      inverter.  Use it accordingly — sparingly, deliberately, with a known target value
      in hand.

---

## Standard write surface

Accessed via `Client.one_shot_command()`.  All registers below are in
`WRITE_SAFE_REGISTERS` (`givenergy_modbus/pdu/write_registers.py`).

### Charge / discharge enable and targets

| HR | Field name | Description | Range / values |
|---|---|---|---|
| 20 | `enable_charge_target` | Enable AC charge upper % limit | bool |
| 96 | `enable_charge` | Enable battery charging | bool |
| 59 | `enable_discharge` | Enable battery discharging | bool |
| 116 | `charge_target_soc` | AC charge upper SOC % limit | 4–100 % |
| 110 | `battery_soc_reserve` | Discharge floor / SOC reserve | 4–100 % |
| 111 | `battery_charge_limit` | Battery charge power limit | 0–100 % of rated |
| 112 | `battery_discharge_limit` | Battery discharge power limit | 0–100 % of rated |
| 114 | `battery_discharge_min_power_reserve` | Minimum discharge power reserve | 4–100 % |
| 29 | `battery_calibration_stage` | SOC force-adjust | 0 (Stop), 1 (Start), 3 (Charge Only) |

### Charge slots 1–10

| HR (start / end) | Field names | Notes |
|---|---|---|
| 94 / 95 | `charge_slot_1_start` / `_end` | HHMM format |
| 31 / 32 | `charge_slot_2_start` / `_end` | |
| 246 / 247 | `charge_slot_3_start` / `_end` | |
| 249 / 250 | `charge_slot_4_start` / `_end` | |
| 252 / 253 | `charge_slot_5_start` / `_end` | |
| 255 / 256 | `charge_slot_6_start` / `_end` | |
| 258 / 259 | `charge_slot_7_start` / `_end` | |
| 261 / 262 | `charge_slot_8_start` / `_end` | |
| 264 / 265 | `charge_slot_9_start` / `_end` | |
| 267 / 268 | `charge_slot_10_start` / `_end` | |

### Discharge slots 1–10

| HR (start / end) | Field names | Notes |
|---|---|---|
| 56 / 57 | `discharge_slot_1_start` / `_end` | |
| 44 / 45 | `discharge_slot_2_start` / `_end` | |
| 276 / 277 | `discharge_slot_3_start` / `_end` | |
| 279 / 280 | `discharge_slot_4_start` / `_end` | |
| 282 / 283 | `discharge_slot_5_start` / `_end` | |
| 285 / 286 | `discharge_slot_6_start` / `_end` | |
| 288 / 289 | `discharge_slot_7_start` / `_end` | |
| 291 / 292 | `discharge_slot_8_start` / `_end` | |
| 294 / 295 | `discharge_slot_9_start` / `_end` | |
| 297 / 298 | `discharge_slot_10_start` / `_end` | |

### Battery mode and scheduling

| HR | Field name | Description | Notes |
|---|---|---|---|
| 27 | `battery_power_mode` | Enable eco mode | bool |
| 50 | `active_power_rate` | Active power rate | 0–100 % |
| 163 | `inverter_reboot` | Restart inverter | write 100; non-damaging |
| 166 | `enable_rtc` | Real-time control | bool |
| 199 | `enable_inverter_parallel_mode` | Enable parallel mode | bool |
| 299 | `discharge_target_soc_10` | DC discharge 10 lower SOC % limit | 0–100 % |
| 331 | `force_off_grid` | Force off-grid | bool; see note below |

!!! note "HR331 — Force off-grid"
    This is a sustained islanding state, not a momentary reboot.  A stuck write
    leaves the site off-grid with no auto-recovery.  Bounded boolean; admitted to
    the standard tier because the app exposes it to end users, but treat with care
    at call sites.

### System time

| HR | Description |
|---|---|
| 35 | System time: year |
| 36 | System time: month |
| 37 | System time: day |
| 38 | System time: hour |
| 39 | System time: minute |
| 40 | System time: second |

Use `set_system_date_time(dt)` rather than writing these individually.

### AC-coupled config (AC / All-in-One models)

Gated on `PlantCapabilities.has_ac_config_block` inside `one_shot_command()`.

| HR | Field name | Description | Range |
|---|---|---|---|
| 311 | `export_power_priority` | Export power priority | 0=Load / 1=Battery / 2=Grid |
| 313 | `inverter_charge_power_pct` | Inverter charge power % | 1–100 % |
| 314 | `inverter_discharge_power_pct` | Inverter discharge power % | 1–100 % |
| 317 | `enable_eps` | Enable EPS | bool |
| 318 | `battery_pause_mode` | Pause battery | `BatteryPauseMode` enum |
| 319 | `battery_pause_slot_start` | Pause slot start | HHMM |
| 320 | `battery_pause_slot_end` | Pause slot end | HHMM |

!!! note "HR313 / HR314 floor at 1, not 0"
    Writing 0 to HR313 or HR314 returns an error on AC hardware (confirmed via
    wire capture).  The range floor is 1 for AC inverters.  DC-coupled models keep
    a 0-floor for HR111 / HR112.

### Three-phase

| HR | Field name | Description |
|---|---|---|
| 1005 | `real_time_control_3ph` | Real-time control (mirrors HR166) |
| 1078 | `battery_reserve_pct_3ph` | Battery reserve % |
| 1108 | `discharge_power_rate_3ph` | Discharge power rate |
| 1109 | `discharge_down_to_pct_3ph` | Discharge down-to % |
| 1110 | `charge_power_rate_3ph` | Charge power rate |
| 1111 | `charge_up_to_pct_3ph` | Charge up-to % |
| 1112 | `enable_ac_charge_3ph` | Enable AC charge |
| 1113 / 1114 | `ac_charge_1_start` / `_end` | AC charge slot 1 |
| 1115 / 1116 | `ac_charge_2_start` / `_end` | AC charge slot 2 |
| 1118 / 1119 | `dc_discharge_1_start` / `_end` | DC discharge slot 1 |
| 1120 / 1121 | `dc_discharge_2_start` / `_end` | DC discharge slot 2 |
| 1122 | `enable_force_discharge_3ph` | Enable force discharge |
| 1123 | `enable_force_charge_3ph` | Enable force charge |

### EMS plant-level scheduling (HR2040–2071)

| HR | Description | Notes |
|---|---|---|
| 2040 | Enable plant EMS control | bool |
| 2044–2046 | EMS discharge slot 1 (start / end / SOC limit) | |
| 2047–2049 | EMS discharge slot 2 | |
| 2050–2052 | EMS discharge slot 3 | |
| 2053–2055 | EMS charge slot 1 (start / end / SOC limit) | |
| 2056–2058 | EMS charge slot 2 | |
| 2059–2061 | EMS charge slot 3 | |
| 2062–2064 | EMS export slot 1 (start / end / SOC limit) | |
| 2065–2067 | EMS export slot 2 | |
| 2068–2070 | EMS export slot 3 | |
| 2071 | EMS export power limit | Installer/DNO — not user-writable via app |

Use the `set_ems_*` helpers in `commands.py` rather than writing these directly.

### Smart load time slots (HR554–573)

| HR (start / end) | Description |
|---|---|
| 554 / 555 | Smart load slot 1 |
| 556 / 557 | Smart load slot 2 |
| 558 / 559 | Smart load slot 3 |
| 560 / 561 | Smart load slot 4 |
| 562 / 563 | Smart load slot 5 |
| 564 / 565 | Smart load slot 6 |
| 566 / 567 | Smart load slot 7 |
| 568 / 569 | Smart load slot 8 |
| 570 / 571 | Smart load slot 9 |
| 572 / 573 | Smart load slot 10 |

### Misc / hardware-gated

| HR | Field name | Description | Notes |
|---|---|---|---|
| 104 | — | Enable battery self-heating | Hardware/batch-gated: write may be rejected per-unit |
| 172 | — | Enable manual battery heater | Likely hardware-gated like HR104 |
| 5010 | — | Restart hardware | Non-damaging; same class as HR163 |
| 5014 | — | Enable calculated load | |

---

## Installer write surface

Accessed via `Client.installer_command()`.  All registers below are in
`INSTALLER_WRITE_REGISTERS` and are inaccessible through `one_shot_command()`.
See the safety note at the top of this document.

### AC grid protection — voltage and frequency limits

Three-level trip scheme: level 1 is the tighter (quicker) trip, level 2 is looser,
and HR79–83 form the third/final level including the 10-minute average voltage monitor.
Converters for this block are inferred from the three-phase parallel block (HR1018–1042);
unverified on live single-phase hardware.

The corresponding `Def` fields (`v_ac_low/high_limit_N`, `f_ac_low/high_limit_N`,
`t_ac_low/high_voltage/freq_N`) are in `givenergy_modbus/model/inverter.py` and can
be read back after a poll.  No bounds-validating `set_*` helpers exist for this block
yet — callers must construct `WriteHoldingRegisterRequest(..., installer=True)`
directly and validate the value against grid-code tolerances themselves.

| HR | Field name | Description | Unit / range |
|---|---|---|---|
| 63 | `v_ac_low_limit_1` | AC undervoltage limit 1 | V × 0.1; 0–500 |
| 64 | `v_ac_high_limit_1` | AC overvoltage limit 1 | V × 0.1; 0–500 |
| 65 | `f_ac_low_limit_1` | AC underfrequency limit 1 | Hz × 0.01; 40–70 |
| 66 | `f_ac_high_limit_1` | AC overfrequency limit 1 | Hz × 0.01; 40–70 |
| 67 | `t_ac_low_voltage_1` | Undervoltage 1 protection time | s × 0.01 |
| 68 | `t_ac_high_voltage_1` | Overvoltage 1 protection time | s × 0.01 |
| 69 | `t_ac_low_freq_1` | Underfrequency 1 protection time | s × 0.01 |
| 70 | `t_ac_high_freq_1` | Overfrequency 1 protection time | s × 0.01 |
| 71 | `v_ac_low_limit_2` | AC undervoltage limit 2 | V × 0.1; 0–500 |
| 72 | `v_ac_high_limit_2` | AC overvoltage limit 2 | V × 0.1; 0–500 |
| 73 | `f_ac_low_limit_2` | AC underfrequency limit 2 | Hz × 0.01; 40–70 |
| 74 | `f_ac_high_limit_2` | AC overfrequency limit 2 | Hz × 0.01; 40–70 |
| 75 | `t_ac_low_voltage_2` | Undervoltage 2 protection time | s × 0.01 |
| 76 | `t_ac_high_voltage_2` | Overvoltage 2 protection time | s × 0.01 |
| 77 | `t_ac_low_freq_2` | Underfrequency 2 protection time | s × 0.01 |
| 78 | `t_ac_high_freq_2` | Overfrequency 2 protection time | s × 0.01 |
| 79 | `v_ac_low_limit_3` | AC undervoltage limit (final) | V × 0.1; 0–500 |
| 80 | `v_ac_high_limit_3` | AC overvoltage limit (final) | V × 0.1; 0–500 |
| 81 | `f_ac_low_limit_3` | AC underfrequency limit (final) | Hz × 0.01; 40–70 |
| 82 | `f_ac_high_limit_3` | AC overfrequency limit (final) | Hz × 0.01; 40–70 |
| 83 | `v_ac_10min_protect` | AC voltage 10-minute average protection | V × 0.1; 0–500 |

### Grid import / anti-islanding

| HR | Field name | Description | Notes |
|---|---|---|---|
| 101 | — | Grid import limit (value) | raw uint16 |
| 102 | — | Grid import limit enabled | bool; `set_grid_import_limit_enabled()` |
| 115 | — | Anti-islanding detection | bool; `set_anti_islanding_detection()` |

### Battery commissioning

| HR | Field name | Description | Range / notes |
|---|---|---|---|
| 174 | — | Wake battery | write 1 |
| 201 | — | Restart battery | write 1 |
| 308 | `battery_nominal_power` | Battery nominal power | W; no app range — consult battery spec |
| 309 | `battery_nominal_current` | Battery nominal current | A; no app range |
| 310 | `battery_max_charge_pct` | Battery max charge % | 20–100 %; `set_battery_max_charge_pct()` |

!!! note "HR308–310 scale"
    Register addresses extracted from the GE app 4.0.7 binary.  Scale and exact
    unit encoding are unconfirmed on live hardware — treat the raw value as uint16
    until a confirming capture is available.

### Plant and inverter operating config (AC block, HR300–359)

This block is polled on AC-coupled and All-in-One inverters (`has_ac_config_block`), so
these registers are now **decoded for read-back** — a consumer can read the current value
before issuing an installer write. The field names below are the getter fields in
`model/inverter.py`. Scale/semantics are unconfirmed on live hardware (raw `uint16` unless
noted), but raw read-back is correct regardless. On non-AC/AIO models the block is not
polled and these fields read `None`.

| HR | Field name | Description | Notes |
|---|---|---|---|
| 300 | `enable_plant_mode` | Enable plant mode | bool; `set_enable_plant_mode()` |
| 301 | `plant_role` | Plant role (app: "Plant Master/Slave"; read-only — not writable) | raw |
| 302 | `plant_meters` | Plant meters | raw |
| 303 | `overfrequency_load_drop_recovery_delay` | Overfrequency load drop recovery delay | raw |
| 305 | `mppt_operating_mode` | MPPT operating mode | raw |
| 306 | `connection_loading_slope` | Connection loading slope | raw |
| 307 | `eps_nominal_voltage` | EPS nominal voltage | raw |
| 312 | `underfrequency_add_load_delay` | Underfrequency add load delay | raw |
| 315 | `en50549_zero_current_lower_voltage_limit` | EN50549 zero-current static lower voltage limit | raw |
| 316 | `en50549_zero_current_upper_voltage_limit` | EN50549 zero-current static upper voltage limit | raw |
| 321 | `overfrequency_derating_start_point` | Overfrequency derating start point | raw |
| 322 | `enable_tariff_pricing_battery_logic` | Enable tariff pricing battery logic | bool |
| 323 | `import_price_battery_discharge_threshold` | Import price battery discharge threshold | raw |
| 324 | `import_price_battery_charge_threshold` | Import price battery charge threshold | raw |
| 325 | `export_price_battery_discharge_threshold` | Export price battery discharge threshold | raw |
| 326 | `underfrequency_derating_start_point` | Underfrequency derating start point | raw |
| 327 | `underfrequency_loading_slope` | Underfrequency loading slope | raw |
| 328 | `overfrequency_derating_stop_point` | Overfrequency derating stop point | raw |
| 329 | `enable_bms_ocv_calibration` | Enable BMS OCV calibration | bool |
| 330 | `gateway_power_off_setting` | Gateway power off setting | raw |
| 332 | `enable_micro_grid` | Enable micro grid | bool; `set_enable_micro_grid()` |
| 347 | `disable_leds` | Disable LEDs | bool |
| 348 | `lcd_screen_idle_timeout` | LCD screen idle timeout | raw |
| 349 | `lead_acid_battery_calibration_upper_limit` | Lead acid battery calibration upper limit | raw |
| 350 | `lead_acid_battery_calibration_lower_limit` | Lead acid battery calibration lower limit | raw |
| 351 | `inverter_operating_mode` | Inverter operating mode | raw |

### EV charger (HR333–336)

| HR | Field name | Description | Range / notes |
|---|---|---|---|
| 333 | `enable_ev_charger` | EV charger enable | bool; `set_enable_ev_charger()` |
| 334 | `ev_charger_import_limit` | EV charger import limit | raw |
| 335 | `ev_charger_reconnection_wait_time` | EV charger reconnection wait time | raw |
| 336 | `ev_charger_soc_limit` | EV charger SOC limit | 0–100 %; `set_ev_charger_soc_limit()` |

### Fan, gateway, and communications

| HR | Description | Notes |
|---|---|---|
| 337 | Enable fan | bool |
| 338 | Fan speed | raw |
| 339 | Enable gateway | bool |
| 340 | BMS communication mode | raw |
| 341 | N-PE relay toggle | raw |
| 342 | AFCI setting | raw |

### Generator (HR343–346)

| HR | Description | Range / notes |
|---|---|---|
| 343 | Enable generator | bool; `set_enable_generator()` |
| 344 | Generator start SOC | 0–100 %; `set_generator_start_soc()` |
| 345 | Generator stop SOC | 0–100 %; `set_generator_stop_soc()` |
| 346 | Generator charge power | raw |

### Smart load — non-slot controls (HR540–553)

See the [standard tier](#smart-load-time-slots-hr554573) for the slot start/end times;
these registers control the feature's enable state and operating thresholds.

| HR | Field name | Description | Range / notes |
|---|---|---|---|
| 540 | — | Enable smart load | bool; `set_enable_smart_load()` |
| 541 | — | Smart load control SOC | 50–100 %; `set_smart_load_control_soc()` |
| 542 | — | Enable general load | bool |
| 543 | — | General load control SOC | 50–100 %; `set_general_load_control_soc()` |
| 544 | — | Generator control SOC | 10–90 %; `set_generator_control_soc()` |
| 545 | — | Generator voltage min | raw |
| 546 | — | Generator voltage max | raw |
| 547 | — | Generator frequency min | raw |
| 548 | — | Generator frequency max | raw |
| 552 | — | Smart load export power | raw |
| 553 | — | Smart load delay time | raw |

### Three-phase power quality and grid compliance

| HR | Description | Notes |
|---|---|---|
| 1048 | Q lock-out power | `q_lock_out_power` Def; raw uint16 |
| 1077 | PV input mode | `pv_input_mode` Def; raw uint16 |
| 1081–1087 | QU curve points and reactive power limits | raw |
| 1102 | Export limit (three-phase) | raw |
| 1103 | Enable export limit (three-phase) | bool; `set_enable_export_limit_3ph()` |
| 1125 | Enable LoRa | bool |
| 1126 | Meter CT direction | raw |
| 1127–1129 | Load shedding voltage limits and minimum active power % | raw |
| 1130 | Import limit (three-phase) | raw |
| 1131 | Enable import limit (three-phase) | bool; `set_enable_import_limit_3ph()` |
| 1144 | Enable meter wiring detection | bool |
| 1149 | Meter wiring detection state | raw |
| 1156 | Safety function control word | raw |
| 1158–1165 | Active power ratio, high/low points, QP lock in/out voltage, min PF | raw |

### Dual-grid / plant

| HR | Description | Notes |
|---|---|---|
| 4001 | Dual grid supply operational mode | raw |

### Special commands (non-destructive)

| HR | Description | Notes |
|---|---|---|
| 5002 | Send wake-up signal | write 1 |
| 5005 | Enable PV meter preset | bool |
| 5006 | Enable AC meter preset | bool |
| 5007 | Enable N-PE | bool |
| 5008 | Enable CT auto configuration | bool |
| 5009 | Enable auto address configuration | bool |
| 5011 | Grid power limit | raw |
| 5012 | AC overcurrent limit | raw |

### Peak shaving / export-import control (EMS installer, HR20000+)

| HR | Description | Notes |
|---|---|---|
| 20000 | Enable grid export limit | bool; `set_peak_shaving_export_limit_enabled()` |
| 20001 | Grid export limit | raw |
| 20002 | Enable peak shaving | bool; `set_peak_shaving_enabled()` |
| 20003 | Peak shaving threshold | raw |
| 20020 | Enable import limit | bool |
| 20021 | Import limit threshold | raw |
| 20050 | Peak shaving power | raw |
| 20051 | Valley filling power | raw |

!!! note "Peak-shaving polling (HR20000–20051)"
    The `has_peak_shaving_block` capability flag is currently `False` for all
    models, so no poll is issued for this range.  The corresponding `Def` entries
    exist and will decode once a confirming live capture allows a model to be added
    to the capability set.

### Destructive operations

!!! danger "These actions cannot be undone"
    Each helper below raises `ValueError` unless called with `confirm=True`.
    Read the docstring of each helper before use.  Obtain the current register
    state beforehand; there is no rollback.

| HR | Helper | Description |
|---|---|---|
| 162 | `reset_energy_totals(confirm=True)` | Clear all lifetime energy counters |
| 1016 | `three_phase_factory_reset(confirm=True)` | Three-phase factory reset (no meter reset) |
| 5003 | `enable_black_start(confirm=True)` | Activate EPS black-start mode |
| 5004 | `restore_factory_defaults(confirm=True)` | Wipe all installer config to factory defaults |

---

## Held-back registers

These registers appear in the GE app 4.0.7 writable map but are intentionally not
admitted to either allow-list pending a bounds-validating `set_*` wrapper or
additional field evidence.

| HR | App name | Reason held back |
|---|---|---|
| 479 | DC Wind CVT Voltage | Raw 16-bit voltage setpoint; no range guard — admit only with a validating command |

---

## Reconciliation status

The app 4.0.7 holding-register inventory (460 entries) is committed to
`docs/reference/registers/app_4.0.7_inventory.json`.  A diff against the library's
live `REGISTER_LUT`s and `WRITE_SAFE_REGISTERS` runs as a regression test in CI via
`scripts/audit_register_doc.py --app-source`.  The audit does not currently cover
`INSTALLER_WRITE_REGISTERS` — installer allow-list drift would not be caught by CI.
The reconciliation stands at 390 matched / 70 app-only gaps, after decoding the polled
installer-config block (HR300–351), the three-phase QU-curve / export-limit registers
(HR1081–1087, HR1102–1103) and HR331. The remaining gaps are predominantly registers in
blocks not admitted to the read poll (special commands HR5000+, peak-shaving HR20000+) or
identity/serial registers that are document-only by design.
