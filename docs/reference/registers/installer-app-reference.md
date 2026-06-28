# GivEnergy installer app — register & protocol reference

Companion to [`installer_1.154.3_inventory.json`](installer_1.154.3_inventory.json), a register
& protocol reference cross-referenced against the GivEnergy **Installer** app (v1.154.3).

## Why this exists

GivEnergy entered administration with no published Modbus specification. The values here are
cross-referenced against the GivEnergy **Installer** app (v1.154.3), which exposes a more
complete view of the register surface than the consumer app does (see `app_4.0.7_inventory.json`)
— register maps with decode scales, named enums, the local-Modbus transport, the write path, and
the destructive-operation set. Treat it as the most complete GivEnergy register reference
available, pending hardware confirmation.

## Transport & addressing

- **Dongle** at `10.10.100.254:8899` over either a `ws://` WebSocket or **Bluetooth LE**
  (service `000000ff…`, characteristic `ff05` = Modbus, `ff01` = config/auth).
- **Framing**: the GivEnergy 18-byte transparent frame (magic `0x5959` "YY", 10-char dongle
  serial), inner Modbus CRC-16 (init `0xFFFF`, poly `0xA001`, byte-swapped on wire).
- **Transport function codes**: HEARTBEAT=1, TRANSPARENT=2, READ_DATALOG=3, WRITE_DATALOG=4,
  FAULT=5. Inner Modbus: FC03 (read holding), FC04 (read input), FC06 (write single), FC16
  (write multiple — dev console only).

**Device-address map** (the authoritative version — cross-check `Plant._getter_for_device_address`):

| Subsystem | Address |
|---|---|
| Inverter / EMS | 17 (0x11) |
| Meters | 1–8 |
| EMS version | 33 |
| PCS / managed inverters | 35–42 |
| BMS cluster | 32 + clusterId |
| LV battery | 49 + id |
| **HV BMU** (per module) | **80–111 (0x50–0x6F)** |
| **HV BCU** (per stack) | **112+ (0x70+)** |
| **HV BAMS** | **144+ (0x90+)** |

The HV BMU band (`0x50–0x6F`) resolves the long-standing per-module decode question — see below.

## Write model

Installer settings are written as **FC06 single-register, fire-and-forget** — no retry, no
verify-by-reread, and crucially **no commit/save step**. `SET_COMMAND_SAVE` (HR1001) exists for
read-back only and is never written; multi-write sequences just pace each write ~5 s apart. The
**write scale is the inverse of the decode `divideBy`** (a register decoded ÷10 is written ×10),
so the decode-scale metadata in the inventory doubles as the write-scale reference. Writability
is decided in per-screen form code, not flagged on the register definitions.

## Per-cell HV battery — the read recipe (resolves #265)

Per-cell HV voltages/temperatures **are** on the Modbus wire; prior probes missed them by
sweeping the BCU band (`0x70+`) when the per-cell array lives one band lower on the BMU addresses.

- **FC04 (read input), device `0x50–0x6F` (one per module), start register 60, count 60.**
- `IR60–83` = `CELL_VOLTAGE_1..24` — raw **mV ÷ 1000 → V**.
- `IR90–113` = `MODULE_TEMPERATURE_1..24` — **deci-°C ÷ 10, signed**, 16-bit big-endian.
- Topology counts: **device `0xA0`, `IR60–64`** = `BAMS_COUNT` / `BCU_COUNT` / `BMU_COUNT` /
  `CELL_COUNT_PER_MODULE` / `TEMPERATURE_SENSOR_COUNT`.

The library's old `Bmu(base=120·k)` decode was addressing the wrong *device* (a stride within
the BCU cache), not the wrong offset. **Wire-confirmed** against a 6-module HV stack
(givenergy-hass#174): `FC04 / 0x50 / start 60 / count 60` and the same at `0x51` both decode
cleanly through `BmuRegisterGetter` — 24 cells ~3.30 V, 24 temperatures ~36.5 °C, and distinct
per-module serials at each address (proving the separate-address layout, not a single echoed cache).

## Grid protection (HR63–83)

The installer `HOLD_REGISTER` enum confirms the library's HR63–83 addresses exactly (HR63
`VAC_LOW_PROTECT_OUT_VALUE` … HR83 `VOLTAGE_PROTECTION_10_MINUTES`). The deci-V / centi-Hz scales
are corroborated by the app's measured-quantity decodes (`AC_VOLTAGE ÷10`, `FAC ÷100`). GE's
structure is three *functions*, not three severity levels: trip (`HR63–70`), **reconnect** band
(`HR71–78`), **grid** band (`HR79–82`). Per-grid-code limit *values* are firmware-managed (not in
the app); the grid code itself is written as a packed `[safetyStandard, region]` u16 to HR2.

## Destructive operations / footguns

All bare FC06, gated only in the UI:

| Operation | Register / value |
|---|---|
| Factory reset **and** restart inverter | `reg163 = 100` (firmware distinguishes by state) |
| Reset user info | `reg162` |
| SOC calibration | `reg29` (0=off … 6=set-full-capacity, 7=finish) |
| Off-grid / black-start (3-phase) | `OFF_GRID_ENABLE 1105` + nominal V `1106` / Hz `1107` |

## Using the inventory file

`installer_1.154.3_inventory.json`:

- `register_maps` — 27 maps (`HOLD_REGISTER`, `INPUT_REGISTER`, `THREE_PHASE_*`, `EMS_*`,
  `HV_BCU/BMU/BAMS_*`, `PCS_*`, `METER_*`, `GATEWAY_*`, `DATALOG_*`, the BMS cluster-detail
  V/T blocks). Each map is `{count, registers: {number: {name, scale?}}}` — iterate
  `register_maps[map].registers` keyed by register address (`count` is the integrity check).
  `scale` carries `divide_by` / `signed` / `byte_count` / `offset` where the app defines one
  (231 registers across the maps).
- `enums` — 68 code/value/bitfield enums: `DEVICE_TYPE_CODE` + the per-family `*_MODEL` tables,
  `SAFETY_STANDARD`, `BATTERY_TYPE`, `SOC_CALIBRATION_SETTING`, `WORKING_MODE`, `INVERTER_STATUS`,
  `MODBUS_FUNCTION_CODE`/`ERROR_CODE`, the single- and three-phase fault-code bit tables
  (`INVERTER_FAULT_CODE`, `THREE_PHASE_HYBRID_FAULT_CODE_WORD_0..7`), `BATTERY_FAULT_CODE`,
  `BMS_*_ALARM`, etc. A few enums whose own name wasn't recoverable carry a `?`-suffixed inferred
  label.

## Reconciliation notes for the library

- The `inverter.py` "skip" zones are now **decoded** as raw read-back (scales app-unconfirmed,
  the HR300-359 posture): HR84–93 (ISO/GFCI/DCI protection), HR99–107 (string/grid voltage +
  power adjustments), HR129–156 (PF-curve / CEI021 / LVFRT). Left undecoded: HR157–161 (unnamed
  in the installer map), HR162 `RESET_USER_INFORMATION` (momentary write-trigger), and HR115
  (the installer's `IS_LAN` contradicts the old `island_check_continue` guess — unconfirmed).
- HR101–104 are **address-reused across product lines**. The installer's single shared
  (three-phase-centric) name table calls them `GRID_R/S/T_VOLTAGE_ADJUSTMENT` + `GRID_POWER_ADJUSTMENT`
  — the per-line-phase meaning. On single-phase hardware the firmware repurposes them, and both the
  consumer app v4.0.7 *and* the library's own write surface agree on the 1ph semantics: `grid_import_limit`
  (101), `grid_import_limit_enabled` (102), `enable_lora` (103), `enable_battery_self_heating` (104, app
  `type=boolean`). So `SinglePhaseInverter` decodes the 1ph names and `ThreePhaseInverter` overrides the
  four with the R/S/T names. Naming the read fields to match the write surface (`GRID_IMPORT_LIMIT` /
  `_ENABLED`) also makes read-after-write consistent. Values read `0x0000` on an unconfigured single-phase
  capture, so they aren't yet wire-confirmed.
- The fault bit tables (currently britkat-sourced, "not verified") are **validated** against GE's
  enums once the MSB-first vs LSB-first convention is accounted for — with one real fix: bit 11 is
  the **Hall** current sensor, not "Hail Sensor".
- `BATTERY_FAULT_CODE` decodes the single-phase inverter's IR(57) (the library's raw
  `charger_warning_code`) — a 16-bit storage-warning word, now surfaced decoded as
  `charger_warning_messages`. The meter-comms bit (15) confirms it is an inverter-level word, not a
  battery-pack register.
- `BCU_STATUS` decodes the HV BCU's IR(70) (`status` → typed `status_label`). The BCU's polled
  IR(107–119) diagnostic tail (`fan_fault_code`, `self_check_status`, `pack_warning/protection/
  fault_status`) is now surfaced as raw read-back — bit-level semantics are not yet enum-confirmed.
- `BMS_LEVEL_ALARM` / `BMS_MAINTENANCE_ALARM` belong to the `bms_cluster` device band (`0x20+`),
  which the library does not model; the extract carries no device/function-code/start metadata for
  those maps, so decoding them needs a new device model plus a wire capture. Tracked as follow-up.
- EMS names HR111/112 `BATTERY_*_MAX_C_RATING` — confirming they're a %-of-rated C-rating ceiling.
- HR199: the app's generic `MODE_ENABLE_SWITCH` vs the library's `enable_inverter_parallel_mode`
  — worth verifying against a real single-phase capture before any rename.

> Provenance caveat: this is GE's own installer tooling, the best non-hardware source — but the
> app can carry its own mislabels/typos (e.g. `GRID_VOLTAGE_FALUT`). Treat as authoritative-pending
> a wire capture, not gospel.
