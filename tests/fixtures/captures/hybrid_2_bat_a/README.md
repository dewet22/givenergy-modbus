# `hybrid_2_bat_a` — single-phase hybrid, direct (no EMS), 2 batteries

Shared conventions (redaction, naming scheme, battery-model mapping) are
in [`../README.md`](../README.md).

## Captures

| File | Vantage |
|---|---|
| `hybrid_gen1_arm449_givbat82_givbat95gen3_60min.log` | HYBRID_GEN1 dongle, ~1 hr (1840 frames) |
| `hybrid_gen1_arm449_0x11_poll_10min.log` | Library polling at `0x11`, ~10 min (482 frames) |

### `hybrid_gen1_arm449_0x11_poll_10min.log`

Recorded with the library polling the inverter at device `0x11` (inverter_address
overridden to `0x11` for HYBRID_GEN1 during recording). Prerequisite fixture for the
`0x11` unification cleanup tracked in
[#189](https://github.com/dewet22/givenergy-modbus/issues/189).

Banks in this capture:
- `0x11`: HR(0, 60, 120) + IR(0, 120, 180) — inverter config and measurements
- `0x31`: HR(0, 60, 120) + IR(0, 60, 120, 180, 240) — passive HA traffic on the bus
- `0x30`, `0x32`–`0x37`: battery IR(60) blocks

Notable difference from the passive dongle capture: HR config banks now appear under
`0x11`, confirming the "identity-only at `0x11`" claim in the prior `inverter_address_for`
docstring was false — the inverter serves its full register file at both addresses.

## Topology

Single-phase HYBRID_GEN1 inverter (ARM firmware 449) with two LV
batteries — one Giv-Bat 8.2 (`BG`) and one Giv-Bat 9.5 Gen3 (`DZ`). No
EMS; the dongle talks to the inverter directly. This is the first
non-EMS / hybrid fixture.

## Origin

A slice of a long-running self-capture from a maintainer's own system
(May 2026), already redacted at capture time (old all-zeros scheme —
manufacture dates not recoverable).

## Why it's here

- First HYBRID topology fixture — every other capture is from the EMS
  installation (`ems_2_inv_3_bat_a`).
- Concrete addressing evidence for
  [#119](https://github.com/dewet22/givenergy-modbus/issues/119): the
  same HYBRID_GEN1 inverter answers at `0x11` (identity only), `0x31`
  and `0x32` (inverter banks; `0x32` also carries battery #1's IR
  block), with batteries at `0x32`/`0x33` and further slots
  `0x30`/`0x34`–`0x37`. This is the `0x11`/`0x31`/`0x32` split the
  addressing redesign turns on — passive-capture evidence (not active
  poll).
- Decoder paths absent from the EMS fixtures: four `error=True`
  responses (including an `IR(236,60)` error that unusually carries a
  non-zero register count) and a `NullResponse` (transparent function
  code 0).

## Known manufacture dates

`YYWW` dates we know for this plant (prefix + week only):

| Device | Prefix | Manufacture | In the bytes |
|---|---|---|---|
| Inverter | `SA` | week 14, 2021 | `SA2114G000` — date backported (#158) |
| Dongle | `WF` | week 25, 2021 | `WF2125G000` — date backported (#158) |

The inverter's firmware ceiling (ARM 449, can't take >449) ties to its
early-2021 manufacture — the transformer-spec change that landed in 2022.
Battery serials (`BG` Giv-Bat 8.2, `DZ` Giv-Bat 9.5 Gen3) and the `AB`
response-source: prefixes known, dates not disclosed.

## Clean

No decoder gaps — no func #57, no undecoded frames beyond the expected
heartbeats; a good baseline hybrid reference.
