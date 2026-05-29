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

`YYWW` dates we know for this plant (prefix + week only; not backported
into the bytes — see [`../README.md`](../README.md#known-manufacture-dates-are-not-backported)):

| Device | Prefix | Manufacture | In the bytes |
|---|---|---|---|
| EMS controller | `EMS` | week 22, 2025 | `EMS2522000` — survived (old redactor missed EMS-format serials) |
| Inverter #1 | `CE` | week 31, 2022 | `CE0000G000` — zeroed at capture |
| Inverter #2 | `CE` | week 42, 2022 | `CE2242G000` — survived (cross-frame split) |
| Data adapter | `FO` | week 22, 2025 | `FO0000G000` — zeroed at capture |

Battery serials (`BE`/`BJ` Giv-Bat 5.2, `AC` Giv-Bat 5.12 Gen3) and the
`AB` response-source: prefixes known, manufacture dates not disclosed.

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
