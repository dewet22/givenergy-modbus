# `ems_2_inv_3_bat_a` — EMS controller + 2 managed inverters, 3 batteries

Shared conventions (redaction, naming scheme, battery-model mapping) are
in [`../README.md`](../README.md).

## Captures

| File | Vantage |
|---|---|
| `ems_arm1036_60s.log` | EMS dongle, ~1 min |
| `ems_arm1036_30min.log` | EMS dongle, 30 min |
| `ac_arm282_2x_givbat52_30min.log` | inverter #1 dongle (2× Giv-Bat 5.2), 30 min |
| `ac_arm282_1x_givbat512gen3_30min.log` | inverter #2 dongle (1× Giv-Bat 5.12 Gen3), 30 min |

## Topology

EMS controller (Model.EMS, ARM firmware 1036) plus two AC-coupled
inverters (Model.AC, ARM firmware 282, single-phase). Three batteries
total: two Giv-Bat 5.2 attached to inverter #1 in a primary/secondary
chain, one Giv-Bat 5.12 Gen3 attached to inverter #2. Grid and load CTs
visible on the EMS bus at sub-addresses `0x01` and `0x03`.

## Origin

Contributed via [dewet22/givenergy-hass#52](https://github.com/dewet22/givenergy-hass/issues/52)
during EMS support investigation (May 2026).

## Known manufacture dates

`YYWW` dates we know for this plant (prefix + week only):

| Device | Prefix | Manufacture | In the bytes |
|---|---|---|---|
| EMS controller | `EMS` | week 22, 2025 | `EMS2522000` — date preserved (EMS format survived old redactor) |
| Inverter #1 | `CE` | week 31, 2022 | `CE2231G000` — date backported (#158) |
| Inverter #2 | `CE` | week 42, 2022 | `CE2242G000` — date preserved (cross-frame split survived old redactor) |
| Data adapter | `FO` | week 22, 2025 | `FO2522G000` — date backported (#158) |

Battery serials (`BE`/`BJ` Giv-Bat 5.2, `AC` Giv-Bat 5.12 Gen3) and the
`AB` response-source: prefixes known, manufacture dates not disclosed.

## Register findings

### EMS `total_battery_power` (IR2090): positive = discharge, negative = charge

Confirmed from `ems_arm1036_60s.log` (2026-07-10, for hass EMS charge/discharge
energy sensors). The 30-min capture can't pin the sign — the battery is idle
throughout (`remaining_battery_wh` flat at 7442, IR2090 ±40 W noise) — but the
60s capture catches a real ~2.5 kW flow and pins it two independent ways:

- **Busbar balance at the active tick:** `total_battery_power = +2511`,
  `grid_meter_power = −1834` (IR2089), `calc_load_power = 677` (IR2086), PV = 0.
  Only "positive = discharge" closes the balance to the watt — battery
  discharging 2511 W feeds 677 W load + exports 1834 W (`677 + 1834 = 2511`). The
  other three sign combinations miss by 700–3700 W.
- **Internal identity:** `total_battery_power (2511)` = `inverter_1_power (1042) +
  inverter_2_power (1469)` exactly (IR2054/2055) — IR2090 is the sum of the
  managed inverters' battery throughput, inheriting their house convention.

So IR2090 follows the library house convention (positive = discharge/export),
matching inverter-level `p_battery`. Caveat: a single active tick (exact
balance), not a multi-sample SOC integral — no committed EMS capture catches the
battery moving its SOC measurably. Re-confirm against an energy ramp if one turns
up. Related: `grid_meter_power` (IR2089) reads **positive = import** here (the
opposite of the inverter-level grid convention) — that fell out of the same
balance but wasn't the target of this check, so treat it as a lead, not a lock.

## Known artifacts

The `ac_arm282_1x_givbat512gen3_30min.log` capture contains ten 70-byte
CSV broadcast frames from the inverter's dongle (`,<ip>,<netmask>,<gateway>`
payload, redacted to all-zeroes) — the WO-prefix LAN-config broadcast
tracked in [#100](https://github.com/dewet22/givenergy-modbus/issues/100).
The framer decodes these as `InvalidFrame`. The paired
`ac_arm282_2x_givbat52_30min.log` capture (same model + ARM firmware)
emits zero such frames — a dongle-firmware divergence.

Note: these are **not** function #57 frames — an earlier read mistook
them for that (a naïve `0x39` byte-scan hits the `9` in the unredacted
IP); function #57 does not appear in any committed capture, only under
live EMS polling (see [#114](https://github.com/dewet22/givenergy-modbus/issues/114)).
