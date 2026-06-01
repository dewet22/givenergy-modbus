# Wire capture fixtures

Real-world frame captures from GivEnergy installations, produced by
`givenergy-cli capture` (which redacts serial numbers at the byte level
during capture — the `XX0000X000` pattern preserves the family prefix
and middle letter while zeroing the unit identifier digits).

These are valuable because GivEnergy has gone bust and no further
upstream firmware/protocol documentation is forthcoming; every real
capture we accumulate is irreplaceable ground truth.

## Redaction surface

Redaction is handled by the `FrameRedactor` class (`givenergy_modbus.client.client`)
and applied automatically during `givenergy-cli capture`. It decodes each complete
GivEnergy frame and zeroes exactly the fields whose register type (`C.serial`) or
PDU class (`LanConfigBroadcast`) mark them as sensitive, then re-encodes with a
freshly-computed CRC. This covers:

- **Envelope serials** — `data_adapter_serial_number` and `inverter_serial_number`
  on every Transparent PDU.
- **Payload register serials** — register groups tagged `C.serial` in the model
  LUTs: inverter `HR(8-12)/HR(13-17)`, battery `IR(110-114)`, EMS rollup
  `IR(2066-2085)` (×4), and gateway AIO serials. Cross-frame EMS-rollup splits
  are handled automatically because the `FrameRedactor` always redacts complete
  frames, not raw byte chunks.
- **LAN-config broadcasts** (`#100`) — WO-prefix dongle heartbeats carrying
  `,ip,netmask,gateway` as a CSV payload are recognised as `LanConfigBroadcast`
  frames and the IP fields are digit-zeroed.

Serial redaction preserves the family prefix, the `YYWW` manufacture date, and
the middle letter, zeroing only the trailing three-digit unit identifier (see
[#113](https://github.com/dewet22/givenergy-modbus/issues/113)). So a redacted
serial reads like `CE2242G000` (week 42 of 2022, unit zeroed) rather than
`CE0000G000`.

### Manufacture dates in fixture bytes

All current fixtures predate the date-preserving redactor
([#113](https://github.com/dewet22/givenergy-modbus/issues/113)) and were
originally captured with a version that zeroed *every* serial digit —
so serials initially read `XX0000X000`. In #158, the known `YYWW` dates
were **backported** into the fixture bytes so they match what the current
`FrameRedactor` would produce for those devices: a serial like `CE2231G000`
rather than `CE0000G000`. The trailing three unit digits remain zeroed.

Devices whose dates we didn't have at backport time (batteries, the `AB`
response-source) still carry `XX0000X000`. A few devices had dates preserved
by the old redactor already (EMS controller `EMS2522000`, and inverter #2's
`CE2242G000` which survived a cross-frame split) — those were left untouched.

Each plant README's "Known manufacture dates" table records which serials
were backported vs which survived vs which remain all-zeros.

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
   automatic — the `FrameRedactor` handles all serial types including
   cross-frame EMS-rollup splits and LAN-config broadcasts).
2. Drop the log into the appropriate plant directory, or create a new
   one named per the layout scheme above (`<type>[_<N>_inv]_<M>_bat_<letter>`)
   for a new topology shape.
3. Run `python scripts/regen_fixture_crcs.py` if the CRCs need recomputing
   after any post-capture edits (no-op if already consistent).
4. Add or update that directory's `README.md` with topology, origin,
   and any anomalies (decoder errors, unusual frames). Don't include
   contributor-identifying information. Extend the battery-model table
   above if a new battery family appears.
5. **Add golden-master coverage.** A new topology scenario must also gain
   at least one test case in `tests/model/test_fixture_golden_master.py`
   that replays it through the decode machinery and pins the expected
   classification + topology (model, inverter address, EMS rollup, HV
   stack, batteries — whatever the plant exercises). This is the whole
   point of committing real captures: they're a standing regression
   net, so a fixture without a golden-master assertion is dead weight
   that can't catch drift. (Register-landing assertions in
   `test_addressing_from_captures.py` are complementary, not a
   substitute.)
