# `aio_a` — All-in-One (integrated inverter + HV battery)

Shared conventions (redaction, naming scheme, battery-model mapping) are
in [`../README.md`](../README.md).

## Captures

| File | Vantage |
|---|---|
| `aio_arm612_5min.log` | AIO dongle, ~5 min (53 frames) |
| `aio_arm620_redetect_7min.log` | AIO dongle, direct poll (not via a Gateway), ~7 min (77 frames), 2026-07-08 — with a **Re-detect Plant** pressed early, so it carries `HR(0,60)` identity + every config bank incl. `HR(300,60)` |

## Topology

A single All-in-One unit (Model.ALL_IN_ONE, ARM firmware 612 in the May
capture, 620 in the July one) — inverter and battery integrated in one
chassis. The battery is **HV, separately addressed** as a BCU stack:
BAMS at `0xA0`, BCU at `0x70`, BMU modules at `0x50`–`0x53`. Two CT
meters at `0x01`/`0x02`. The inverter answers at device `0x11`;
**nothing at `0x32`**.

## Origin

`aio_arm612_5min.log`: contributed via [dewet22/givenergy-modbus#105](https://github.com/dewet22/givenergy-modbus/issues/105)
during the AIO connection investigation (May 2026). A passive
`givenergy-cli capture` (the dongle relaying the vendor app's polling),
already redacted at capture time (old all-zeros scheme — manufacture
dates not recoverable).

`aio_arm620_redetect_7min.log`: supplied by the dual-AIO + Gateway
reporter via [dewet22/givenergy-hass#95](https://github.com/dewet22/givenergy-hass/issues/95)
(2026-07-08) — one AIO of the same plant family polled directly on
hass v1.4.0rc1, with a Re-detect pressed to pull the HR banks into the
passive window (dongle fan-out mirrors every response to the listener).
Partially redacted at capture time by the bundled 2.10.1 redactor
(envelope + inverter serials); the HV battery family — the BCU serial at
`IR(138–142)` and the modules' split-layout serial tails — was
re-redacted through the library before commit (date scheme, CRCs
re-encoded). Every BMU module on this firmware (`BAAA0013`) stores its
serial split on the wire (prefix at IR110, tail at IR115–118) — the
split-serial redaction gap's layout, here on all four modules.

## Why it's here

- Third distinct topology alongside the EMS install and the direct hybrid.
- Decisive addressing evidence for
  [#119](https://github.com/dewet22/givenergy-modbus/issues/119): the AIO
  answers at `0x11` and exposes **nothing at `0x32`**, confirming `0x32`
  is not "the inverter" and the `0x11→0x32` rewrite is wrong for this
  model. Root cause of [#105](https://github.com/dewet22/givenergy-modbus/issues/105)
  (AIO can't connect — the library polls `0x32`).
- First capture exercising the **HV BCU stack** (`0x70`/`0xA0`/`0x50`–`0x53`),
  which the battery-model mapping's HV section had no fixture for.
- `aio_arm620_redetect_7min.log` is the **first fixture that drives the live
  detect → load_config → refresh cycle CLEANLY** (no missing banks), and the
  first with live `HR(300,60)` coverage — the AC-config block the
  `has_ac_config_block` manifest gate polls. It backs the strict
  `aio_redetect_clean` case in `tests/client/test_mock_plant_integration.py`.

## Known manufacture dates

`YYWW` dates we know for this plant (prefix + week only):

| Device | Prefix | Manufacture | In the bytes |
|---|---|---|---|
| Inverter (AIO) | `CH` | week 14, 2024 | `CH2414G000` — date backported (#158) |
| Dongle | `WJ` | week 14, 2024 | `WJ2414G000` — date backported (#158) |

HV BCU/BMS serials (`HC`/`HX`) and the `AB` response-source: prefixes
known, manufacture dates not disclosed.

## Clean

No decoder gaps — no func #57, no undecoded frames beyond the expected
heartbeats.
