# Wire capture fixtures

Real-world frame captures from GivEnergy installations, produced by
`givenergy-cli capture` (which redacts serial numbers at the byte level
during capture — the `XX0000X000` pattern preserves the family prefix
and middle letter while zeroing the unit identifier digits).

These are valuable because GivEnergy has gone bust and no further
upstream firmware/protocol documentation is forthcoming; every real
capture we accumulate is irreplaceable ground truth.

## Redaction surface

Three identifier categories are handled by the library redactor
(`givenergy_modbus.client.redact` — see PR #99) and applied
automatically during `givenergy-cli capture`:

- Standard 10-char GE serials (`XX####X###`) — covers inverter,
  dongle, battery, meter serials.
- EMS-style serials (`EMS#######`) — the EMS plant controller's
  serial format, which doesn't match the standard pattern.
- IPv4 dotted-quads — caught at source so the WO-prefix dongle
  heartbeat (see [#100](https://github.com/dewet22/givenergy-modbus/issues/100))
  doesn't leak LAN topology even into raw captures.

One residual case still needs a fixture-side pass — `_redact_extra.py`
next to this README applies it, idempotently:

- **Truncated GE serials at frame boundaries** — wire frames sometimes
  end mid-serial inside the EMS rollup block at `IR(2066..2085)`,
  leaving a 2-letter prefix plus partial digits like `XX00`. The
  broader regex needed to catch these reliably (`[A-Z]{2}\d{2,}`) has
  too much false-positive risk to codify in the library-wide redactor.

Run before committing new captures (no-op on captures from a
post-#99 CLI that don't hit the frame-boundary edge case):

```bash
uv run python tests/fixtures/captures/_redact_extra.py path/to/*.log
```

## What's in scope here

Wire captures only. Plant exports (`*-plant.json`) and any
contributor-supplied supplementary material (cloud-integration PDFs,
photos, topology descriptions) stay private — JSON exports are an
artifact of how the CLI export command works today and should be
forever regeneratable from the wire captures, so there's no point
committing the regeneratable form.

## Layout

One directory per plant. Within a plant, one file per capture vantage
point — an EMS dongle is one vantage, each inverter dongle on the
same plant is another. Filename convention encodes the device shape so
captures are discoverable cross-scenario: `<device-model>_arm<arm_fw>`
plus a battery descriptor where applicable (`<count>x_<batterymodel>`)
plus the observation duration.

```
tests/fixtures/captures/
└── ems_plant_a/                                  # one plant
    ├── ems_arm1036_60s.log                       # EMS dongle, ~1 min observation
    ├── ems_arm1036_30min.log                     # EMS dongle, 30 min
    ├── ac_arm282_2x_givbat52_30min.log           # AC inverter dongle, 2× Giv-Bat 5.2, 30 min
    └── ac_arm282_1x_givbat512gen3_30min.log      # AC inverter dongle, 1× Giv-Bat 5.12 Gen3, 30 min
```

Plants are named with anonymising labels (`ems_plant_a`,
`hybrid_plant_b`, etc.) rather than contributor names; the redacted
wire frames themselves don't identify the source.

## Battery model mapping

Wire-observable battery fields don't directly carry GivEnergy's
marketing model name (e.g. "Giv-Bat 5.2"), so the tables below are the
canonical reference for fixture-naming until a `BatteryModel` resolver
lands in the library. Three families with different addressing
patterns; each has its own table. Extend with new rows (or fill in
`TBC` cells) as captures from new models arrive.

### Low-voltage (LV) — standalone units attached to an external inverter

Addressed as separate devices at `0x32..0x37` (battery #1 shares the
inverter's IR bank at `0x32`; #2+ at `0x33+`). Identification is via
`(serial_prefix, cap_design)` — both are inherent to the physical
unit. The `bms_firmware_version` field is updateable per unit, so it
isn't a model identifier; the column below lists firmware versions
actually seen in committed fixture captures, useful for cross-
referencing capture content but not for distinguishing models.

| Marketing name | Serial prefix(es) | `cap_design` (Ah) | Observed BMS firmwares | Filename token |
|---|---|---|---|---|
| Giv-Bat 2.6 | TBC | TBC | — | `givbat26` |
| Giv-Bat 5.2 | `BE`, `BJ` | 102.0 | 3022 | `givbat52` |
| Giv-Bat 5.12 Gen3 | `AC` | 106.0 | 4009 | `givbat512gen3` |
| Giv-Bat 8.2 | `BG` | 160.0 | 3007 | `givbat82` |
| Giv-Bat 9.5 Gen3 | `DZ` | 186.0 | 3009 | `givbat95gen3` |

### High-voltage (HV) — stackable modular batteries

Addressed via a BAMS at `0xA0` and one or more BCUs at `0x70 + offset`.
The library models these as `BcuStack` rather than `Battery`; capture-
naming should encode the stack shape (BCU count + modules per BCU)
once wire data arrives. No fixtures yet — `TBC` rows below will be
populated and split per SKU when captures come in.

| Marketing name | BCU count range | Modules per BCU | Filename token |
|---|---|---|---|
| *(stackable HV family)* | TBC | TBC | TBC |

### All-in-One (AIO) — integrated chassis

Inverter + battery + BMS in one unit. The battery isn't addressed as a
separate device; data appears in the AIO inverter's own register
space. Resolved via `Model.ALL_IN_ONE` / `Model.ALL_IN_ONE_HYBRID` in
`givenergy_modbus/model/inverter.py`. No fixtures yet — `TBC` row will
be populated when an AIO capture arrives.

| Marketing name | Inverter `Model` | Integrated capacity | Filename token |
|---|---|---|---|
| All-in-One 13.5 | `Model.ALL_IN_ONE` | 13.5 kWh | TBC |

## Provenance for `ems_plant_a`

- **Topology**: EMS plant controller (Model.EMS, ARM firmware 1036)
  plus two AC-coupled inverters (Model.AC, ARM firmware 282,
  single-phase). Three batteries total: two Giv-Bat 5.2 attached to
  inverter #1 in a primary/secondary chain, one Giv-Bat 5.12 Gen3
  attached to inverter #2. Grid and load CTs visible on the EMS bus
  at sub-addresses `0x01` and `0x03`.
- **Origin**: contributed via [dewet22/givenergy-hass#52](https://github.com/dewet22/givenergy-hass/issues/52)
  during EMS support investigation (May 2026).
- **Known artifacts**:
  - The `ac_arm282_1x_givbat512gen3_30min.log` capture surfaced
    `NotImplementedError: TransparentResponse function #57 decoder`
    ten times during the 30-minute window — useful regression bait
    once that decoder lands.
  - The same capture contains ten 70-byte CSV broadcast frames from
    the inverter's dongle (`,<ip>,<netmask>,<gateway>` payload,
    redacted to all-zeroes). Same model + ARM-firmware inverter on
    the paired `ac_arm282_2x_givbat52_30min.log` capture emits zero
    such frames — see [#100](https://github.com/dewet22/givenergy-modbus/issues/100)
    for the dongle-firmware divergence investigation.

## Adding new captures

1. Run `uvx givenergy-cli capture` against the device (redaction is
   automatic).
2. Drop into the appropriate plant directory (or create a new one if
   it's a new topology shape).
3. Note any anomalies (decoder errors, unusual frames) in a brief
   provenance section above. Don't include contributor-identifying
   information.
