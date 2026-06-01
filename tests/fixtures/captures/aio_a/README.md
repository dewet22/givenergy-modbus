# `aio_a` — All-in-One (integrated inverter + HV battery)

Shared conventions (redaction, naming scheme, battery-model mapping) are
in [`../README.md`](../README.md).

## Captures

| File | Vantage |
|---|---|
| `aio_arm612_5min.log` | AIO dongle, ~5 min (53 frames) |

## Topology

A single All-in-One unit (Model.ALL_IN_ONE, ARM firmware 612) — inverter
and battery integrated in one chassis. The battery is **HV, separately
addressed** as a BCU stack: BAMS at `0xA0`, BCU at `0x70`, BMU modules
at `0x50`–`0x53`. Two CT meters at `0x01`/`0x02`. The inverter answers
at device `0x11`; **nothing at `0x32`**.

## Origin

Contributed via [dewet22/givenergy-modbus#105](https://github.com/dewet22/givenergy-modbus/issues/105)
during the AIO connection investigation (May 2026). A passive
`givenergy-cli capture` (the dongle relaying the vendor app's polling),
already redacted at capture time (old all-zeros scheme — manufacture
dates not recoverable).

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
