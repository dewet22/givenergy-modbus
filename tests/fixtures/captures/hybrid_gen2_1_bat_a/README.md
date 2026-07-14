# `hybrid_gen2_1_bat_a` — single-phase hybrid Gen2 3.6, direct (no EMS), 1 battery

Shared conventions (redaction, naming scheme, battery-model mapping) are
in [`../README.md`](../README.md).

## Captures

| File | Vantage |
|---|---|
| `hybrid_gen2_arm920_60s.log` | HYBRID_GEN2 passive HA capture, 60 s (14 frames) |

## Topology

Single-phase **HYBRID_GEN2** inverter (device-type-code `0x2003`, ARM
firmware **920** → `arm_fw // 100 == 9`, the Gen2 discriminator),
`inverter_max_power` 3600 W — the "3.6" model. One LV battery (16 cells,
186 Ah, ~9.5 kWh, LiFePO4). DC-coupled (`is_ac_coupled == False`), two PV
strings.

This is the **first Gen2 fixture** — every prior hybrid capture is
HYBRID_GEN1 (ARM 449). It is the passive-capture evidence behind the
[hass#293](https://github.com/dewet22/givenergy-home-assistant/issues/293)
battery-energy routing fix.

Banks in this capture (all at `0x11`, library polling shape): HR(0, 60,
120) + IR(0, 60, 120, 180). No separate battery-bank address — the LV
pack decodes from the inverter's own IR banks.

## Why it's here

- **First HYBRID_GEN2 topology fixture.** Gives the golden-master and
  live-cycle suites their first Gen2 coverage; previously Gen2 was
  entirely untested.
- **Pins the hass#293 routing fix.** Gen2 3.6 hybrids resolve to
  `Model.HYBRID_GEN2`, which was undeclared in `manifest.VALUE_SOURCES`,
  so the canonical daily battery-energy fields returned `None`. This
  capture is the evidence: daily charge/discharge live at **alt1**
  (`IR36`/`IR37`) → 4.7 / 5.5 kWh, corroborated by `e_ac_charge_today`
  4.8; GEN1's alt2 daily reads 0.0.
- **Confirms `IR44 == PV generation` on Gen2.** The DC-coupled hybrid PV
  fields (`e_pv1_day`, `e_pv2_day`, `e_pv_generation_today`) are real and
  sun-shaped, so the manifest hybrid field-identity holds on GEN2, not
  just GEN1.

## Deferred: battery-energy total

The lifetime battery-energy total is **not** derivable from this capture.
alt1's total register (`IR180`/`IR181`) reads an implausible 0 for a unit
with ~7397 kWh throughput, and the alt2/alt3 total candidates live in the
`HR(4100+)` bank, which the library polls on no model — so a passive
capture can never contain it. Confirming the Gen2 total source needs a
directed `ReadHoldingRegisters(base=4100, count~16)` probe on a Gen2.

## Known manufacture dates

`YYWW` dates preserved by the capture-time redaction (prefix + week only;
trailing unit digits zeroed):

| Device | Prefix | Manufacture | In the bytes |
|---|---|---|---|
| Inverter | `EA` | week 02, 2023 | `EA2302G000` |
| Dongle | `WG` | week 02, 2023 | `WG2302G000` |
| Battery | `DF` | week 44, 2022 | `DF2244G000` |

## Origin

A single 60-second poll cycle from the hass#293 reporter's system
(`crg-n`), 2026-07-13, captured with `givenergy-cli capture` and already
redacted at source (unit digits zeroed; our `FrameRedactor` re-run is a
no-op, verified zero unredacted serials).

## Clean

No decoder gaps and no error frames — a clean single-cycle Gen2 baseline.
