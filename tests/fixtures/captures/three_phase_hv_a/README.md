# `three_phase_hv_a` — three-phase HV hybrid (GIV-3HY-11), 6 HV battery modules

Shared conventions (redaction, naming scheme, battery-model mapping) are
in [`../README.md`](../README.md).

## Captures

| File | Vantage |
|---|---|
| `giv3hy11_hass174_180s.txt` | HA-integration wire capture, 180 s (156 frames) |
| `giv3hy11_da011_10min.log` | givenergy-cli passive capture, ~10 min (128 frames, zero error responses) — same plant, 2026-07-08; adds per-module BMU reads at 0x50–0x55 and BAMS blocks at 0x90/0xA0 |

### Format note

Unlike the other fixtures (givenergy-cli's `<ts> rx <hex>` log format),
`giv3hy11_hass174_180s.txt` is the **Home Assistant integration's** capture format —
`tx: <hex>` / `rx: <hex>`, one frame per line, no timestamps. Preserved as-shared;
`tests/model/test_three_phase_from_capture.py` has a small loader for it.
`giv3hy11_da011_10min.log` uses the standard cli log format (`# …` comment lines are
reconnect markers, preserved as captured).

## Topology

Three-phase HV hybrid inverter, model `GIV-3HY-11` (firmware `DA0.011-DD0.011-A0.011`),
with **6 HV battery modules** (52 Ah / 20.37 kWh) behind a BCU. The inverter answers at
`0x11` (full register file incl. the IR(1000–1413) three-phase banks); the HV battery
stack responds at `0x70` (BCU cluster block, plus a second IR(120,60) block carrying the
BCU's own serial at IR(138–142)); **each BMU module answers at its own device address
0x50–0x55** with the plain IR(60–119) per-cell block; further devices at `0x90`/`0xA0`
(BAMS, IR(60,60) only in this capture).

## Origin

Posted publicly by reporter `lamztib` on
[givenergy-hass#174](https://github.com/dewet22/givenergy-hass/issues/174) (June 2026),
captured with HA 2026.6.3 / integration 1.3.2 / givenergy-modbus 2.3.2. Redacted at capture
time by the integration (all-zeros scheme — serials zeroed to `…G000`, manufacture dates not
recoverable). The Modbus frames carry no IP/host. **One serial the integration's redactor
missed:** the BCU unit serial at 0x70/IR(138) — its location was only discovered later
(#375), so it wasn't a redaction target in June. Re-redacted through the library's
`FrameRedactor` (`…G000`, CRC re-encoded) once IR(138) was modelled; caught by
`scripts/scan_capture_serials.py` (#378).

`giv3hy11_da011_10min.log` was supplied privately by the same reporter (2026-07-08, via
the hass-side soak) and redacted through the library's `FrameRedactor` before commit
(date-redaction scheme — prefix + manufacture date kept, unit digits zeroed, CRCs
re-encoded). One quirk needed a manual pass: module `0x55` stores its serial *split* on
the wire (`HY` at IR(110), the `2336G…` tail at IR(115–118) — a layout the fixed-group
redactor cannot see as one serial), so its unit digits were hand-zeroed through the
library encoder. The split layout itself is preserved as captured.

## Why it's here

- **First real three-phase dataset** the project has — every other fixture is
  single-phase / AIO / EMS. Until this, all three-phase tests primed synthetic registers.
- Drove and now locks in the three-phase battery fixes it surfaced:
  - [#264](https://github.com/dewet22/givenergy-modbus/issues/264): `i_battery` is
    centi, not deci (it was decoding 10× high) — confirmed by the V×I identity against
    this capture.
  - [#262](https://github.com/dewet22/givenergy-modbus/issues/262): derived `p_battery`
    (discharge − charge) and `e_battery_throughput` (charge + discharge totals), which
    read frozen when inherited from the single-phase registers.
- BCU cluster-level decode (`number_of_modules`, `battery_soc_max/min`, `battery_voltage`,
  `battery_soh`) — the path consumers read per-stack SOC from.
- **Per-module BMU per-cell decode, wire-validated** (`giv3hy11_da011_10min.log`): all 6
  modules answer at 0x50–0x55 with sane per-cell voltages (~3.35 V LiFePO4) and
  temperatures — the multi-module probe [#265](https://github.com/dewet22/givenergy-modbus/issues/265)
  asked for. Also first wire evidence of the BCU's own serial at IR(138–142) (#375).

## Known limitations

- The earlier `giv3hy11_hass174_180s.txt` predates the per-module BMU layout fix: its
  module-0 stride overlapped the BCU's own IR(60–105) block, so per-cell data in *that*
  capture decodes as garbage (the historical #265 problem — since resolved; the .log
  capture supersedes it for per-cell assertions). Its regression test deliberately
  asserts only inverter-level and BCU-cluster fields.
- Neither capture carries `HR(0,60)` at `0x11` (both poll sets read IR for identity), so
  this fixture **cannot drive a live `detect()` cycle** — three-phase live-full-cycle
  coverage remains open as
  [#370](https://github.com/dewet22/givenergy-modbus/issues/370).
