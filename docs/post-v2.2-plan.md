# Post-v2.2 unified roadmap

A working document. Expected to change as consumers (`givenergy-hass`,
`givenergy-cli`) report back and as contributors send hardware captures. It
supersedes the [Post-v2.0 improvement plan](post-v2-improvement-plan.md) —
folding that document's still-live items forward and marking the shipped ones —
and brings the scattered open-issue backlog under a small set of pillars so the
direction is legible in one place.

> **Why now.** The v2.1/v2.2 *structural* roadmap is largely cleared: the
> flagship [#106](https://github.com/dewet22/givenergy-modbus/issues/106)
> (graph-shaped Plant), [#75](https://github.com/dewet22/givenergy-modbus/issues/75)
> (commands onto Inverter), [#57](https://github.com/dewet22/givenergy-modbus/issues/57)
> (bounds *detection* — its whole-bank-discard tail is folded into Pillar C) and
> #166 all landed. What's left is a pile of
> register-audit and data-integrity issues plus four strategic threads that were
> only ever discussed, never written down. This consolidates them.

## What shaped these priorities

GivEnergy has gone bust. There will be no further official protocol
documentation and no new firmware, and there is no warranty path if a bad write
bricks an inverter. Three consequences run through everything below:

- **The register map is provisional in perpetuity.** Much of it is inherited
  from forks and field captures and can never be reconciled against an
  authoritative spec. Honesty about confidence has to be built in, not implied.
- **Writes carry real risk with no safety net.** Hardening the write path is
  worth more, not less, than it was when there was a vendor to fall back on.
- **Hardware-dependent work is throttled by data, not by code.** Anything that
  needs a capture from a device family the maintainer doesn't own advances only
  when a contributor sends one.

This is therefore a **theme-priority document, not a dated plan**. The pillars
are ordered by value and by their interlocks; the hardware-gated work floats.

## The four pillars

### Pillar A — Provable write safety

*Carries forward [post-v2 §1 and §2](post-v2-improvement-plan.md).* The
highest-value hardening left: writes hit real inverters, and the only protection
today is register-level.

- ~~**Model-aware command routing (#203)**~~ — **shipped PR #215 (2026-06-07).**
  `_ThreePhaseCommands` now overrides `set_mode_storage`, `set_battery_soc_reserve`,
  `set_charge_target`, and `set_battery_reserve_soc` to target the correct three-phase
  registers; `_ThreePhaseCommands.WRITE_SAFE_REGISTERS` is defined. `set_battery_reserve_soc`
  (HR 1078) moved off the universal mixin where it didn't belong.
- ~~**Model-aware write policy at the `Client` boundary.**~~ — **shipped 2026-06-17.**
  `one_shot_command()` now validates every `WriteHoldingRegisterRequest` against
  `_ThreePhaseCommands.WRITE_SAFE_REGISTERS` (three-phase) or
  `_InverterCommands.WRITE_SAFE_REGISTERS` (single-phase / undetected), raising
  `InvalidPduState` before any frame hits the wire. Closes the bypass path where
  a hand-built PDU skipped the command-mixin checks.
- ~~**Dry-run validation.**~~ — **shipped 2026-06-17.**
  `one_shot_command(..., dry_run=True)` validates but does not transmit; lets
  downstream integrations check a request list without a live connection.
- **Interlock:** high-risk writes gate on register provenance (Pillar B).

### Pillar B — Register provenance and confidence

*Carries forward [post-v2 §5](post-v2-improvement-plan.md); the umbrella over the
register-audit backlog.* Because the map will never be officially documented,
source and confidence should be first-class in the model rather than implicit in
a comment.

- Optional provenance metadata on the `Def` class (`model/register.py`) — e.g.
  `source` (verified / field-observed / GivTCP / fork) and a `risk` flag. No
  field carries this today.
- Docs can then distinguish verified, field-observed and provisional registers.
- A register must clear a provenance bar before joining a safe-write set — the
  concrete feed into Pillar A.

This pillar is what turns the audit backlog from a scatter of "to investigate"
issues into one coherent effort:
[#48](https://github.com/dewet22/givenergy-modbus/issues/48) (field-validate
inherited mappings),
[#182](https://github.com/dewet22/givenergy-modbus/issues/182),
[#183](https://github.com/dewet22/givenergy-modbus/issues/183),
[#184](https://github.com/dewet22/givenergy-modbus/issues/184),
[#185](https://github.com/dewet22/givenergy-modbus/issues/185) (scale/unit
corrections),
[#200](https://github.com/dewet22/givenergy-modbus/issues/200) (BMS fault
bitfield), and
~~[#209](https://github.com/dewet22/givenergy-modbus/issues/209) (power-factor
formula) — shipped 2026-06-12~~.

### Pillar C — Unified data-trust layer

*New synthesis.* The principle is "never silently serve untrustworthy data".
Several signals already exist in isolation; the work is to consolidate them into
one per-device health surface that consumers act on, instead of every consumer
re-deriving its own ad-hoc checks.

| Signal | Mechanism | Status |
|---|---|---|
| Freshness | `Plant.block_age()` (#65) | shipped |
| Staleness / freeze | `Plant.content_unchanged_seconds()` (#91 primitive) → freeze *verdict* | primitive shipped (v2.2.0; #91 closed); verdict deliberately not auto-thresholded — healthy batteries hold static content for 7–26 polls; one freeze capture is insufficient to calibrate a threshold that won't false-fire on healthy-but-static hardware |
| Bank dropout | Pattern A/B rejection ([#78](https://github.com/dewet22/givenergy-modbus/issues/78) / [#147](https://github.com/dewet22/givenergy-modbus/issues/147)) | shipped |
| CRC guard | three-state policy: default=skip-commit, `strict_crc`=raise, `lenient_crc_commit`=opt-in ([#255](https://github.com/dewet22/givenergy-modbus/issues/255)) | shipped 2.3.1 |
| Sub-bus splice guard | valid-CRC windowed splice rejection + singleton escrow ([#256](https://github.com/dewet22/givenergy-modbus/issues/256)) | shipped 2.3.2 |
| Bounds | field-level OOB suppression shipped (#57 closed); bank-level whole-bank discard still gated behind `TODO(enforcement)` in `_commit_bank()` — prerequisites (#65 freshness, #91 primitive) now met; flip is the residual open work | field-level shipped; discard deferred |
| Present-but-unavailable | placeholder for transiently-absent devices ([#213](https://github.com/dewet22/givenergy-modbus/issues/213)) | open |
| Transient zeros | home-load debounce ([#199](https://github.com/dewet22/givenergy-modbus/issues/199)) | open |

The target is a single consumer-facing surface — e.g. a `health`/availability
rollup on `PlantDevice` — so the `givenergy-hass` agent maps one signal onto HA
availability rather than stitching several together. The shape gets handed across
via the coordination inbox once it stabilises. The #91 freeze verdict stays
deferred until there are enough firmware-update freeze captures to set a
threshold that doesn't fire on healthy-but-static batteries; the #57 whole-bank
discard (flipping the `TODO(enforcement)` in `_commit_bank()` from log-only to a
rejecting `return False`) is the other concrete unit of work this pillar carries.

### Pillar D — Generic-topology hoist (flagship, parked)

*Realises the long-stated direction — and deliberately isn't actioned yet.* The
`Plant` / `Device` / `Transport` graph is already a
[generic energy-topology abstraction](plant-device-graph.md#design-discipline-kept-hoist-ready):
manufacturer- and protocol-agnostic, with no concrete GivEnergy or Modbus types
leaking into the generic shapes. The big move is extracting those shapes into a
base package so the library becomes a coordination layer above a single vendor
(myenergi, Tesla, …) over multiple transports (Modbus, HTTP, MQTT).

The discipline is to **stay hoist-ready, not to hoist speculatively**. Extracting
a base package before a real second-manufacturer or second-protocol case exists
would be abstraction for its own sake — exactly the trap the graph work was
careful to avoid. So this is the 3.0 horizon, triggered by a concrete second
case. Near-term, the only standing rule is regression-grade: keep `GivEnergy*` /
Modbus concretes out of the generic layer.

## Foundations (carry-forward infrastructure)

The remaining [post-v2.0 plan](post-v2-improvement-plan.md) items that aren't a
pillar in their own right:

| Item | Status |
|---|---|
| §3 internal refresh serialization (`asyncio.Lock` around detect/load_config/refresh) | not started |
| §6 broaden golden-frame fixtures (have EMS, single-phase hybrid, AIO, three-phase [#270/2.4.0]; still need gateway, write success/error) | partial |
| §7 mypy `check_untyped_defs` | partial — production on; `tests.*` deferred (58 findings) |
| §10 public API compatibility tests | partial — `test_deprecation_aliases.py` covers aliases; documented imports + command-helper signatures untested |
| §4 fail CI on async resource warnings | **done** (`pyproject.toml` filterwarnings) |
| §8 cleaner release artifact checks | **done** (ephemeral per-run `dist`) |
| §9 docs `../LICENSE` warning | moot — no such link remains |

Adjacent protocol-citizen work, tracked independently:
[#207](https://github.com/dewet22/givenergy-modbus/issues/207) (self-tuning
skip-if-fresh), [#198](https://github.com/dewet22/givenergy-modbus/issues/198)
(heartbeat-ACK dropout investigation),
~~[#205](https://github.com/dewet22/givenergy-modbus/issues/205) (signed
directional power sensors) — shipped 2026-06-12~~.

## Hardware-gated backlog

Throttled by capture availability rather than engineering time — listed so the
gating is explicit, not scheduled:
[#193](https://github.com/dewet22/givenergy-modbus/issues/193) (Gen-1 gateway),
[#169](https://github.com/dewet22/givenergy-modbus/issues/169) (inverter
addressing — HYBRID_GEN2/GEN3 verification; ~~[#189](https://github.com/dewet22/givenergy-modbus/issues/189) 0x31 retire shipped 2.3.0~~),
[#114](https://github.com/dewet22/givenergy-modbus/issues/114) /
[#115](https://github.com/dewet22/givenergy-modbus/issues/115) (undecoded
function codes), [#141](https://github.com/dewet22/givenergy-modbus/issues/141)
(three-phase grid-power nodes),
[#186](https://github.com/dewet22/givenergy-modbus/issues/186) (HR4600
relocation), [#197](https://github.com/dewet22/givenergy-modbus/issues/197)
(ACBC field-evidence tracking).

## Sequencing

Priority order, not dates — and the hardware-gated items float across all of it
as captures arrive.

- **2.2.0 final** — ship the current rc line. No hard blockers remain; the #91
  freeze verdict is deferred, not blocking.
- **2.3.0** — shipped 2026-06-12. Diverged from the slated theme: field evidence
  delivered register-correctness and addressing work instead (0x11 unification
  [#189](https://github.com/dewet22/givenergy-modbus/issues/189), meter
  PF/apparent scales
  [#246](https://github.com/dewet22/givenergy-modbus/issues/246), the
  fork-migration guide, provenance accessors
  [#248](https://github.com/dewet22/givenergy-modbus/issues/248)). Pillar A
  moves down a line.
- **2.4.0** — shipped 2026-06-17. Diverged again from slated Pillar A: compact
  probe-dump serialiser `to_compact`/`parse_compact` (#269, new public API) and
  the first real three-phase capture fixture (#270). Proper semver from here —
  roadmap items are prioritised, not version-pinned.
- **2.4.x** — Pillar A remaining (client-boundary model-aware write rejection +
  dry-run validation) and Foundations §3 (asyncio.Lock refresh serialisation).
- **2.5.x** — Pillar B (provenance) feeding Pillar C (data-trust consolidation,
  including the `_commit_bank` discard flip and freeze verdict once threshold is
  calibrated), with Foundations §6/§7/§10 alongside.
- **3.0** — Pillar D, only once a second vendor or transport makes the extraction
  real.

The one firm constraint is the interlock order: provenance lands before
provenance-gated writes, and the individual trust signals exist before the
unified health surface that aggregates them.
