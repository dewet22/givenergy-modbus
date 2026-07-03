# `gateway_2aio_a` — Gen1 Gateway fronting 2× parallel AIO

Shared conventions (redaction, naming scheme, battery-model mapping) are
in [`../README.md`](../README.md).

## Captures

| File | Vantage |
|---|---|
| `gateway_gaaa0014_10min_daylight.log` | Gateway dongle, ~10 min daylight (solar non-zero, p_pv ≈ 2 kW; GivTCP + HA + cloud sharing the bus) |
| `gateway_gaaa0014_10min_night.log` | Gateway dongle, ~10 min deep-night (p_pv = 0; **GivTCP-only** — the cleanest single-client poll-cycle record) |

## Topology

Gen1 Gateway (Model.GATEWAY, `HR(0)=0x7001`, firmware `GAAA0014`) fronting two
parallel AIOs (`parallel_aio_num=2`); batteries are register-embedded per-AIO in
the gateway rollup (IR1600–1859), NOT separately-addressed LV packs — nothing
answers at `0x32` (#358). Two live meters at `0x01`/`0x02`.
Passive transcription of GivTCP (30 s polling) + the HA integration + cloud
traffic sharing the bus.

## Origin

Contributed via [dewet22/givenergy-hass#95](https://github.com/dewet22/givenergy-hass/issues/95)
(2026-07-03) during Gateway support work — the first live Gateway capture. The
same plant's AIO history backs the #293 register-identity analysis.

## Notable

- First live-traffic validation of the GatewayV1 register map: today-counters
  are exact (per-AIO charge 9.8+9.3 = battery 19.1 kWh), AC-side vs battery-DC
  energy blocks show conversion losses in the correct direction both ways.
- **Falsified the GatewayV2 selector** (#360): `IR(1600-1603)` =
  `0x4741 0x4141 0x0000 0x0104` ("GAAA0014") tripped the old raw `>= 10` test
  into the swapped-word V2 layout; all ten uint32 energy totals decode sanely
  only in V1 order.
- **Live AIO-serial layout**: contiguous 5-register stride from IR(1841)
  (aio1 1841-1845, aio2 1846-1850) — neither pre-live serial table had it,
  which exempted aio2 from FrameRedactor's LUT-derived redaction; the
  committed captures are re-redacted (`CH2542G000`) with CRCs re-encoded
  through the library.
- The night capture predates the HA entry (its config-flow attempt exposed #358),
  so it is a pure GivTCP conversation; the daylight capture interleaves three
  clients. Day/night pairing mirrors the contrast that settled #293.
