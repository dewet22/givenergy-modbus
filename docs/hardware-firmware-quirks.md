# Hardware & firmware quirks

A catalogue of confirmed oddities in GivEnergy's register behaviour that aren't
obvious from the protocol document alone — address reuse across firmware, registers
that are specified but unimplemented on older builds, units that contradict their own
description, and similar traps. The aim is to stop these being rediscovered the hard
way.

Each entry records the **symptom**, the **evidence** it rests on, the **implication**
for the library, and **references** (issue numbers, protocol-doc sections). Where a
finding came from a single unit, that's stated — a quirk seen on one unit is a data
point, not a universal truth.

The authoritative protocol reference is the v4.1.6 hybrid Modbus RTU document
(2024-10-30); a parsed inventory lives under `docs/reference/registers/`. GivEnergy is
no longer trading, so this document set is effectively the last word and won't be
reissued — hence the value of writing findings down here.

> **Adding an entry:** lead with the symptom, cite the evidence (capture, probe, or
> doc section), and say what it means for the code. Attribute hardware-specific results
> to the unit/firmware they were proven on. Verify before generalising.

## Register address reuse across firmware (IR180-183)

**Symptom.** The same input-register addresses mean different things on different
firmware lineages.

**Evidence.** On a HYBRID_GEN1 unit, IR180/181 return battery charge/discharge lifetime
totals (e.g. discharge 1560.4 kWh, charge 1822.8 kWh at 0.1 kWh scale) and IR182/183
return daily battery energy. The v4.1.6 doc, however, defines IR180-183 as
`wEV_Voltage_L1/L2/L3` + `wEV_current_L1` — EV-charger phase voltages and current
(0.1 V / 0.1 A). A phase voltage of 1560 V is impossible, so the GEN1 reading is
genuinely battery energy, not a misread.

**Implication.** The library's `alt1` battery-total source (`IR(180)`/`IR(181)` in
`_BATTERY_ENERGY_SOURCE`) is correct for GEN1 but **firmware-fragile**: on a build that
implements the EV-charger definitions, deci-scaling a phase-voltage reading would yield
a bogus "~175 kWh" total. Battery-energy routing must stay keyed to the resolved model,
never inferred from live values, and should migrate to the dedicated registers below
when a unit supports them.

**References.** v4.1.6 §4.1.2; `model/inverter.py` `_BATTERY_ENERGY_SOURCE`.

## Firmware-gated registers — specified but absent on old builds (IR194-199, HR84-89)

**Symptom.** Registers present in the protocol doc read a hard zero (or are absent) on
older firmware.

**Evidence.** Protocol v4.1.5 (2024-10-22) added IR194-197 (dedicated battery
charge/discharge **lifetime** totals, 0.1 kWh), IR198 (CT power), IR199 (system state).
A HYBRID_GEN1 unit on ARM/DSP firmware **449** returns zero for the whole IR194-199
range, while its IR180/181 totals are populated — so the device address is correct and
the zeros are a firmware result. The same unit returns zero for HR84-89 (the §4.13 ASCII
firmware-version-string scheme), so this build predates several doc additions.

**Implication.** IR194-197 cannot be a *universal* battery-total source. The library's
`_BATTERY_ENERGY_SOURCE` is keyed by static `Model`, which has no way to express
"firmware ≥ v4.1.5". Mapping these registers needs either firmware gating or must stay
conditional until a unit is observed that actually populates them. Confirmed lower
anchor: **HYBRID_GEN1 @ ARM 449 → absent.** No upper anchor (a unit that *does* populate
them) has been observed yet.

**References.** v4.1.6 revision history (v4.1.5 entry), §4.1.2, §4.13; issue #184.

## The protocol doc has no firmware→register map

**Symptom.** There's no way, from the doc alone, to tell which firmware build implements
a given register.

**Evidence.** The revision history dates *specification* changes (authored by GivEnergy
engineers) but never ties them to firmware versions. §4.13 documents the firmware
version-string *format* (combined codes like `ZB_A1_01`), not a per-register
availability threshold, and its release-date column is blank in v4.1.6. No register
table carries an "available from firmware X" annotation.

**Implication.** Firmware/register correlation can only be established empirically:
probe a register on units of known firmware and record presence/absence. Reading a
unit's own firmware (HR21 ARM, HR19 DSP, or — where implemented — the HR84-89 strings)
gives the anchor. Version numbers are **not comparable across model families** (a GEN1
hybrid on ARM 449 and an AC-coupled unit on ARM 282 are different firmware lineages; the
larger number is not "newer").

**References.** v4.1.6 revision history, §4.13.

## Writable "Set" baselines masquerading as live counters (HR4102-4103)

**Symptom.** A register holds a large, static energy-like value that never moves.

**Evidence.** HR4102/4103 read a fixed ~3,229.6 kWh (0.1 kWh scale) on a HYBRID_GEN1 AC
unit. The v4.1.6 doc labels them "**Set** Battery ChgDischarge Energy Total" and marks
them R/W — i.e. a writable seed/baseline (e.g. to preserve cumulative counts across a
board swap), not a live accumulator. Re-probing after a charge/discharge cycle would not
show movement.

**Implication.** Don't treat HR4102/4103 as a live battery-total source. The live
counters are the IR/HR energy-total registers (firmware permitting).

**References.** v4.1.6 §4.1.1.

## Units that contradict their own description (HR111/112)

**Symptom.** A register's unit column disagrees with its description, and neither maps
cleanly onto the value range.

**Evidence.** HR111/112 (`bBatChgLimit`/`bBatDisLimit`) carry unit `0.5C` (a battery
C-rate) in the doc's unit column, but the description reads "battery charge/discharge
**power percentage**", the default is 50, and the range is 1-250 — none of which
reconcile (50 × 0.5C = 25C is not a sane charge rate; 1-250 doesn't map to 0-100%).
A separate, clean percentage pair exists: HR313/314 (`fChargePowerPercent`/
`fDischargePowerPercent`, range 1-100, unit 1%), which is what the GivEnergy app surfaces
as "Power Percentage".

**Implication.** Don't reinterpret HR111/112's scale on the doc's word — the unit field
is unreliable here. The defensible step is bounds (1-250) plus a docstring that records
the ambiguity; deriving watts from these via a rated-power table is unsafe (the
`battery_max_power` DTC table is itself incomplete). A live-hardware write test is needed
to settle the true unit.

**References.** v4.1.6 §4.1.1; issue #183.

## Doc unit corrections have shipped silently mid-protocol

**Symptom.** The same register's documented unit changes between protocol revisions.

**Evidence.** The v4.1.6 revision history records, among others: IR10 inverter current
corrected from 0.01 A to 0.1 A (v4.1.1/4.1.3); IR58 grid current split by phase count
(single 0.01 A, three-phase 0.1 A, v4.1.3); and a batch of energy registers
(IR6/7/11/12/17/19/21/22/… and HR4102/4103/4107-4114/4140-4142) restated as 0.1 kWh to
match the server (v4.1.5).

**Implication.** A unit stated in any single revision may be a correction of an earlier
error — treat the doc's unit column as a strong hint, not ground truth, and prefer
hardware/cross-reference confirmation before changing a scale. (The library already
scales the v4.1.5 energy registers correctly via `deci`; that batch was a doc catch-up,
not a library bug.)

**References.** v4.1.6 revision history.
