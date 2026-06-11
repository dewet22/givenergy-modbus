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

- **Model-aware write policy at the `Client` boundary.** `Client.one_shot_command()`
  / `execute()` should reject writes that aren't valid for the *detected* inverter
  model, complementing the global `WRITE_SAFE_REGISTERS` allowlist enforced in
  `pdu/write_registers.py::ensure_valid_state()`. A caller can still hand-build a
  write PDU that bypasses the model-specific command mixins; this closes that gap.
  Conservative default when capabilities are unknown. Tests must cover direct
  `WriteHoldingRegisterRequest` construction, not just the high-level helpers.
- **Dry-run validation.** A supported way to encode and validate a request list
  without transmitting — `client.validate_requests(...)` or
  `one_shot_command(..., dry_run=True)` — reporting register, value, device
  address and rejection reason. Lets downstream integrations check before
  enabling live writes.
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
bitfield) and
[#209](https://github.com/dewet22/givenergy-modbus/issues/209) (power-factor
formula).

### Pillar C — Unified data-trust layer

*New synthesis.* The principle is "never silently serve untrustworthy data".
Several signals already exist in isolation; the work is to consolidate them into
one per-device health surface that consumers act on, instead of every consumer
re-deriving its own ad-hoc checks.

| Signal | Mechanism | Status |
|---|---|---|
| Freshness | `Plant.block_age()` (#65) | shipped |
| Staleness / freeze | `Plant.content_unchanged_seconds()` (#91 primitive) → freeze *verdict* | primitive shipped; [verdict deferred](https://github.com/dewet22/givenergy-modbus/issues/91) |
| Bank dropout | Pattern A/B rejection ([#78](https://github.com/dewet22/givenergy-modbus/issues/78) / [#147](https://github.com/dewet22/givenergy-modbus/issues/147)) | shipped |
| Bounds | field-level out-of-range suppression + bank-level detection (#57); whole-bank discard still gated behind a `TODO(enforcement)` in `_commit_bank()` | detection shipped; discard deferred |
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
| §6 broaden golden-frame fixtures (have EMS, single-phase hybrid, AIO; need three-phase, gateway, write success/error) | partial |
| §7 mypy `check_untyped_defs` | partial — production on; `tests.*` deferred (58 findings) |
| §10 public API compatibility tests | partial — `test_deprecation_aliases.py` covers aliases; documented imports + command-helper signatures untested |
| §4 fail CI on async resource warnings | **done** (`pyproject.toml` filterwarnings) |
| §8 cleaner release artifact checks | **done** (ephemeral per-run `dist`) |
| §9 docs `../LICENSE` warning | moot — no such link remains |

Adjacent protocol-citizen work, tracked independently:
[#207](https://github.com/dewet22/givenergy-modbus/issues/207) (self-tuning
skip-if-fresh), [#198](https://github.com/dewet22/givenergy-modbus/issues/198)
(heartbeat-ACK dropout investigation),
[#205](https://github.com/dewet22/givenergy-modbus/issues/205) (signed
directional power sensors).

## Hardware-gated backlog

Throttled by capture availability rather than engineering time — listed so the
gating is explicit, not scheduled:
[#193](https://github.com/dewet22/givenergy-modbus/issues/193) (Gen-1 gateway),
[#169](https://github.com/dewet22/givenergy-modbus/issues/169) /
[#189](https://github.com/dewet22/givenergy-modbus/issues/189) (inverter
addressing), [#114](https://github.com/dewet22/givenergy-modbus/issues/114) /
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
- **2.4.x** — Pillar A (write safety) and Foundations §3.
- **2.5.x** — Pillar B (provenance) feeding Pillar C (data-trust consolidation),
  with Foundations §6/§7/§10 alongside.
- **3.0** — Pillar D, only once a second vendor or transport makes the extraction
  real.

The one firm constraint is the interlock order: provenance lands before
provenance-gated writes, and the individual trust signals exist before the
unified health surface that aggregates them.
