# `hybrid_hv_gen3_a` — residential single-phase HV hybrid (GIV-HY-8.0-G3-HV), 3 HV modules

Shared conventions (redaction, naming scheme, battery-model mapping) are
in [`../README.md`](../README.md).

## Captures

| File | Vantage |
|---|---|
| `givhy80g3hv_hass295_120s.log` | HYBRID_HV_GEN3 passive HA capture, 120 s (34 frames) |

## Topology

Single-phase **HYBRID_HV_GEN3** inverter (device-type-code `0x8102`, DTC
family `81`), `_DTC_RATED_POWER` 8000 W — the "8.0" model. HV battery
architecture: one BCU at `0x70` fronting **three** BMU modules at
`0x50`/`0x51`/`0x52` (24 cells each, 52 Ah, ~3.34 V/cell), plus a grid
meter at `0x01`. DC-coupled (`is_ac_coupled == False`), two PV strings.

Banks in this capture (at `0x11`): HR(240-299, 1060-1124) + IR(0-59,
180-239, 1000-1413). Note the **absence of HR(0)** — this is 120 s of
steady-state refresh traffic, and the identity bank is a `load_config()`
read taken once at startup. The capture therefore cannot self-classify:
the `0x8102` device-type code comes from the reporter's own plant export,
not from these bytes. A `0x32` cache is created but stays empty.

## Why it's here

- **First 81xx capture of any kind.** `Model.HYBRID_HV_GEN3`'s membership
  in `CAPABILITIES["is_three_phase"]` had never been exercised against
  hardware — the only three-phase HV fixture is `three_phase_hv_a`
  (GIV-3HY-11), whose HR(0) reads `0x4004` → `Model.HYBRID_3PH`, a
  genuinely three-phase family.
- **The evidence for the reclassification.** Family 81 is a residential HV
  hybrid on a *single* phase, the same shape the manifest already carves
  out for `ALL_IN_ONE` (family 8). Decoded both ways off this one cache:

  | field | `ThreePhaseInverter` | `SinglePhaseInverter` |
  |---|---|---|
  | `battery_soc` | 0 | 100 |
  | `p_pv1` | 0.0 | 674 |
  | `p_pv2` | 0.0 | 4531 |
  | `p_battery` | 0.0 | 58 |
  | `e_consumption_today` | *(no attr)* | 5.2 |
  | `v_battery` | 240.07 | 240.07 |

  The single-phase decode is self-consistent for a sunny July afternoon
  (100 % SOC, 5.2 kW PV, 4458 W export, 378 W house load) and corroborated
  by the BCU's own independent view of the stack (SOC 96-100 %, 238.2 V vs
  the inverter's 240.07 V).

- **Pins why a readability probe cannot discriminate here.** Unlike the
  AIO, which error-responds to 1000-range reads, this unit **answers every
  one of IR(1000-1413) with zeros**. All 414 registers are present and all
  are zero, against 50 non-zero of 60 in IR(0-59). That is why the
  misclassification surfaced to the reporter as a live-but-idle plant
  (SOC 0 %, house consumption 0, both PV strings 0 W) rather than an
  obvious decode failure — and why the fix has to be a model-keyed
  capability rather than a probe.

## Not settled by this capture

- **`ALL_IN_ONE_HYBRID` (DTC family 82)** is also family-8-adjacent and
  also in `is_three_phase`. Nothing here speaks to it either way; it is
  left in the set pending its own capture.
- **The HR(0-179) write addresses are inherited, not wire-confirmed.**
  Reclassifying moves this model onto `WRITE_SAFE_SINGLE_PHASE`, so slot
  and charge controls now write to HR94/95, 31/32, 56/57, 44/45, 96, 110
  and 116 rather than their 1000-range twins. That is a 1:1 re-addressing
  of the same eleven controls (see `WRITE_SAFE_THREE_PHASE`'s derivation)
  and it is *required* for coherence — post-reclassification `slot_map` is
  `EXTENDED_SLOTS`, so holding the three-phase allowlist would leave every
  slot 1/2 address unwritable. But this capture carries no HR(0-179) at
  all, so the addresses come from the single-phase classification rather
  than from these bytes. There is no positive evidence for the 1000-range
  alternative either, and the whole 1000-range reads zeros here, so the
  inherited position is the better-supported of the two — it is not
  evidence-free, just not directly confirmed. A directed
  `HR(0,60)`/`HR(60,60)`/`HR(120,60)` read on an 81xx unit would settle it.
  Pinned meanwhile by `test_write_safe_registers_hybrid_hv_gen3_*` and
  `test_hybrid_hv_gen3_slot_map_addresses_are_all_write_safe`.
- **Battery-side power ceiling.** The reporter observes the portal showing
  5990 W max discharge against our 8000 W (the inverter's rated AC output
  from `_DTC_RATED_POWER["8102"]`), with 3 of a possible 6 HV modules. His
  stack-voltage × max-battery-current hypothesis checks out arithmetically
  on this capture (240.07 V × 25 A = 6002 W, ~0.2 % off), but the current
  limit is not reported by the inverter, so a derived ceiling would need
  per-model current constants. Wants a second unit with a different stack
  size before anything depends on it.

## Known manufacture dates

`YYWW` dates preserved by the capture-time redaction (prefix + week only;
trailing unit digits zeroed):

| Device | Prefix | Manufacture | In the bytes |
|---|---|---|---|
| Inverter | `FG` | week 44, 2024 | `FG2444G000` |
| Dongle | `WH` | week 44, 2024 | `WH2444G000` |
| HV BMU modules (×3) | `HY` | week 46, 2024 | `HY2446G000` |

All three BMU modules came from the same batch, so redaction collapses
them to one string — the same effect seen on `three_phase_hv_a`. The BCU's
own serial (IR138-142) is not in this capture; only IR(60-119) was polled
at `0x70`. `AB1234G000` is the library's own request-side data-adapter
placeholder, not a device serial (it appears identically in
`hybrid_2_bat_a` and `three_phase_hv_a`).

## Origin

A 120-second passive capture from `KevC1978` on
[dewet22/givenergy-hass#295](https://github.com/dewet22/givenergy-hass/issues/295)
(2026-07-14), integration 1.4.8 / library 2.12.2, taken with
`givenergy-cli capture` and already redacted at source. Our
`scan_capture_serials.py` re-run is clean.

## Clean

34 frames, no error responses and no decoder gaps.
