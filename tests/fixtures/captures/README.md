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

- Standard 10-char GE serials (`XXYYWWXNNN`) — covers inverter,
  dongle, battery, meter serials.
- EMS-style serials (`EMSYYWWNNN`) — the EMS controller's
  serial format, which doesn't match the standard pattern.
- IPv4 dotted-quads — caught at source so the WO-prefix dongle
  heartbeat (see [#100](https://github.com/dewet22/givenergy-modbus/issues/100))
  doesn't leak LAN topology even into raw captures.

Serial redaction preserves the family prefix, the `YYWW` manufacture
date, and the middle letter, zeroing only the trailing three-digit unit
identifier (see [#113](https://github.com/dewet22/givenergy-modbus/issues/113)
for why the date is kept — it's a coarse, diagnostically useful cohort
marker, not a per-unit identifier). So a redacted serial reads like
`CE2242G000` (week 42 of 2022, unit zeroed) rather than `CE0000G000`.

One residual case still needs a fixture-side pass — `_redact_extra.py`
next to this README applies it, idempotently:

- **Serials split across frame boundaries** — consecutive inverter
  serials in the EMS rollup at `IR(2066..2085)` can straddle a capture
  frame boundary, so the leading fragment (`…CE22`) lands in one frame
  and the unit-bearing continuation (`42G612…`) in the next. Per-frame
  redaction sees neither as a complete serial, so the unit digits leak
  when the rollup is reassembled. `_redact_extra.py` is **reassembly-
  aware**: it concatenates the frame payloads, redacts the whole stream
  (date-preserving, matching the library policy), then re-slices back to
  the original frame lengths. The broader `[A-Z]{2}\d{2,}` matching it
  uses has too much false-positive risk to codify in the library-wide
  redactor, hence it lives here.

Run before committing new captures (no-op on captures with no
cross-frame serial splits):

```bash
uv run python tests/fixtures/captures/_redact_extra.py path/to/*.log
```

### Known manufacture dates are *not* backported

All current fixtures predate the date-preserving redactor
([#113](https://github.com/dewet22/givenergy-modbus/issues/113)) and were
taken with a library version that zeroed *every* serial digit at capture
time — so most serials read `XX0000X000`, with the `YYWW` manufacture
date gone from the bytes. We do know the real dates for several devices
(from contributor disclosures), but **we deliberately don't edit them
back into the captured bytes**: the fixture stays exactly as it came off
the wire, redaction and all. Restoring digits we happen to know
out-of-band would make the bytes partly hand-authored, and the dates
don't affect anything the fixtures are *for* (decoder parsing, addressing,
prefix-based model identification).

Instead, each plant's README records the `YYWW` values we know (prefix +
week only — never the trailing unit digits) so the data can still be
reasoned about later. A few dates do survive *in the bytes* where the old
redactor missed a serial shape (EMS-format serials, cross-frame splits)
and the current redactor preserved them — those are genuine wire data,
not backported.

Forward note: if `YYWW`-based logic ever lands (a hardware-revision or
`BatteryModel` resolver that reads the date), these pre-#113 fixtures
won't carry dates in their bytes and would need re-capturing or a
purpose-built synthetic fixture — a decision to revisit then, by which
point there should be a stock of natively date-preserving captures to
draw on.

## What's in scope here

Wire captures only. Plant exports (`*-plant.json`) and any
contributor-supplied supplementary material (cloud-integration PDFs,
photos, topology descriptions) stay private — JSON exports are an
artifact of how the CLI export command works today and should be
forever regeneratable from the wire captures, so there's no point
committing the regeneratable form.

## Layout

One directory per plant — a whole installation. The directory name
describes the plant's topology: `<type>[_<N>_inv]_<M>_bat_<letter>`,
where the inverter count is included when there's more than one
(omitted for a single-inverter hybrid) and the trailing letter
distinguishes different samples of the same shape rather than naming
the contributor. Within a plant, one file per capture vantage point —
an EMS dongle is one vantage, each inverter dongle on the same plant is
another. Filenames encode the captured device:
`<device-model>_arm<arm_fw>` plus a battery descriptor where applicable
(`<count>x_<batterymodel>`, or the battery models in series) plus the
observation duration.

```text
tests/fixtures/captures/
├── ems_2_inv_3_bat_a/                            # EMS controller + 2 managed inverters, 3 batteries
│   ├── ems_arm1036_60s.log                       # EMS dongle, ~1 min observation
│   ├── ems_arm1036_30min.log                     # EMS dongle, 30 min
│   ├── ac_arm282_2x_givbat52_30min.log           # AC inverter dongle, 2× Giv-Bat 5.2, 30 min
│   └── ac_arm282_1x_givbat512gen3_30min.log      # AC inverter dongle, 1× Giv-Bat 5.12 Gen3, 30 min
├── hybrid_2_bat_a/                               # single-phase hybrid, direct (no EMS), 2 batteries
│   └── hybrid_gen1_arm449_givbat82_givbat95gen3_60min.log  # HYBRID_GEN1 dongle, Giv-Bat 8.2 + 9.5 Gen3, ~1 hr
└── aio_a/                                         # All-in-One (integrated inverter + HV battery)
    └── aio_arm612_5min.log                        # ALL_IN_ONE dongle, HV BCU stack, ~5 min
```

(AIO carries no `_<M>_bat` token — the battery is integral to the
chassis, the way `hybrid` implies a single inverter.)

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

Inverter + battery + BMS in one unit (`Model.ALL_IN_ONE` /
`Model.ALL_IN_ONE_HYBRID` in `givenergy_modbus/model/inverter.py`). The
integral battery is an **HV BCU stack, separately addressed** — BAMS at
`0xA0`, BCU at `0x70`, BMU modules at `0x50`–`0x53` — *not* embedded in
the inverter's register space (an earlier note here claimed otherwise;
the `aio_a` capture shows the separate addressing). The inverter itself
answers at `0x11`. See `aio_a/` for the first AIO fixture.

| Marketing name | Inverter `Model` | Integrated capacity | Observed at | Filename token |
|---|---|---|---|---|
| All-in-One 13.5 | `Model.ALL_IN_ONE` | 13.5 kWh | `0x11` + HV BCU `0x70`/`0xA0`/`0x50`–`0x53` | `aio` |

## Per-plant provenance

Each plant directory carries its own `README.md` with that plant's
topology, origin, and known artifacts — kept next to the data so a new
plant is self-documenting rather than growing a section here:

- [`ems_2_inv_3_bat_a/README.md`](ems_2_inv_3_bat_a/README.md)
- [`hybrid_2_bat_a/README.md`](hybrid_2_bat_a/README.md)
- [`aio_a/README.md`](aio_a/README.md)

## Adding new captures

1. Run `uvx givenergy-cli capture` against the device (redaction is
   automatic).
2. Drop the log into the appropriate plant directory, or create a new
   one named per the layout scheme above (`<type>[_<N>_inv]_<M>_bat_<letter>`)
   for a new topology shape.
3. Run `_redact_extra.py` over the new file (catches cross-frame serial
   splits that the per-frame CLI redactor misses).
4. Add or update that directory's `README.md` with topology, origin,
   and any anomalies (decoder errors, unusual frames). Don't include
   contributor-identifying information. Extend the battery-model table
   above if a new battery family appears.
