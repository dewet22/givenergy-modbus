# `three_phase_hv_a` — three-phase HV hybrid (GIV-3HY-11), 6 HV battery modules

Shared conventions (redaction, naming scheme, battery-model mapping) are
in [`../README.md`](../README.md).

## Captures

| File | Vantage |
|---|---|
| `giv3hy11_hass174_180s.txt` | HA-integration wire capture, 180 s (156 frames) |

### Format note

Unlike the other fixtures (givenergy-cli's `<ts> rx <hex>` log format), this is the
**Home Assistant integration's** capture format — `tx: <hex>` / `rx: <hex>`, one frame
per line, no timestamps. Preserved as-shared; `tests/model/test_three_phase_from_capture.py`
has a small loader for it.

## Topology

Three-phase HV hybrid inverter, model `GIV-3HY-11` (firmware `DA0.011-DD0.011-A0.011`),
with **6 HV battery modules** (52 Ah / 20.37 kWh) behind a BCU. The inverter answers at
`0x11` (full register file incl. the IR(1000–1413) three-phase banks); the HV battery
stack responds at `0x70` (BCU cluster block) with further devices at `0x90`/`0xA0`.

## Origin

Posted publicly by reporter `lamztib` on
[givenergy-hass#174](https://github.com/dewet22/givenergy-hass/issues/174) (June 2026),
captured with HA 2026.6.3 / integration 1.3.2 / givenergy-modbus 2.3.2. Already redacted
at capture time by the integration (all-zeros scheme — serials zeroed to `…G000`,
manufacture dates not recoverable). The Modbus frames carry no IP/host.

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

## Known-suspect

Per-module **BMU** per-cell data is **not** validated by this capture and is known wrong —
the module-0 stride overlaps the BCU's own IR(60–105) block, so per-cell temps/voltages
decode as garbage. Tracked in
[#265](https://github.com/dewet22/givenergy-modbus/issues/265); a fuller multi-module HV
probe is needed to pin the real layout. The regression test deliberately asserts only the
**validated** inverter-level and BCU-cluster fields.
