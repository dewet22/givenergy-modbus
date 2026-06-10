# Security Audit — givenergy-modbus

**Date:** 2026-06-10
**Scope:** full codebase at commit `936523e` (chore: release 2.1.6)
**Method:** four parallel security-focused reviews (network input parsing; client & write path;
model layer & redaction; scripts/CI/supply chain), with the highest-impact claims re-verified
directly against source before inclusion.
**Amendments:** after independent pre-publication review (PR #223): H1 and H3 were downgraded
to Medium (premises corrected inline), and H2's byte-swap sub-item was narrowed from a possible
leak to a missing test combination. Original IDs are kept stable for tracking.

**Threat model:** Modbus TCP has no authentication or TLS. The remote peer (inverter, or any
device/attacker on the LAN segment) can send arbitrary bytes. The library controls real
power-grid hardware, so write-path integrity matters as much as parse robustness. Cache
exports are intended to be share-safe (`redact_serials()`, #212/#214).

**Overall assessment:** No critical remote vulnerability found. No eval/pickle/dynamic-dispatch
sinks. `WRITE_SAFE_REGISTERS` is enforced at encode time with no bypass found. Frame sizes are
capped, fixtures are clean, publishing uses OIDC. The findings below are ranked by priority for
remediation planning.

Severity scale: **High** = fix soon, real attacker value or undercuts a stated guarantee.
**Medium** = should fix, requires more attacker capability or has bounded impact.
**Low** = hygiene/hardening.

---

## High priority

### H1 — CRC mismatches on register responses accepted, logged only at DEBUG

> **Amended 2026-06-10 (post-review): severity downgraded to Medium.** The CRC16/Modbus is
> unauthenticated — an on-path attacker who substitutes register values recomputes it exactly as
> the legitimate peer does, so the check detects accidental corruption and naive splicing, not
> competent tampering. The original tamper-visibility rationale doesn't support High; the fix
> below stands as robustness hardening.

- **Where:** `givenergy_modbus/pdu/read_registers.py:105-122` (`_validate_check_code`)
- **Status:** verified in source
- **Detail:** The CRC16/Modbus over the response payload is recomputed and compared to the wire
  `check` field; on mismatch it logs at `_logger.debug()` and the data is accepted. The docstring
  documents this as deliberate ("incoming inverter frames are the source of truth") — reasonable
  for tolerating firmware quirks, but DEBUG level gives operators zero visibility into corrupted
  or malformed frames being accepted into the cache.
- **Scenario:** A flaky dongle, RS485 noise carried into the TCP re-encapsulation, or a buggy
  middlebox produces responses whose payload no longer matches the check field; the data
  populates the plant cache silently and downstream consumers (e.g. Home Assistant) act on it.
- **Fix plan:**
  - [ ] Minimum: raise the mismatch log to `WARNING`, with a message noting the frame failed its
        integrity check.
  - [ ] Better: add a configurable strict mode that raises `InvalidPduState` on mismatch
        (lenient default preserves current firmware tolerance).

### H2 — `redact_serials()` gaps: meter serial, Plant header fields, untested AIO byte-swap path

- **Where:** `givenergy_modbus/model/register_cache.py:25-72,143-178`;
  `givenergy_modbus/model/meter.py:89`; `givenergy_modbus/model/plant.py` (serial fields,
  populated in `Plant.update()`)
- **Status:** verified in source
- **Detail:** Three gaps in the share-safe-export guarantee from #212/#214:
  1. **Meter product serial not redacted.** `MeterProductRegisterGetter` declares
     `"serial_number": Def(C.string, None, MR(60), MR(61))`. `_get_serial_groups()` walks
     `(inverter, battery, ems, gateway)` — no `meter` — and filters on
     `pre_conv is Converter.serial`, which `C.string` fails. `redact_serials()`'s `_reg_cls`
     maps only `"HR"`/`"IR"`, so `"MR"` groups are skipped regardless. A redacted export
     containing MR(60–61) leaks the meter identifier untouched.
  2. **Plant-level serial fields out of scope.** `Plant.inverter_serial_number` and
     `Plant.data_adapter_serial_number` are populated from PDU headers and live outside any
     `RegisterCache`. Redacting every cache then sharing a `Plant` dump still leaks both.
  3. **AIO byte-swapped HR(8–12): one path-combination untested.** *(Narrowed post-review,
     PR #223.)* The byte-swapped value shape is verified to redact correctly on the
     `FrameRedactor` path (`test_frame_redactor_redacts_hr8_serial_register` feeds
     `HC2114G047` → `HC2114G000`), and the HR(8–12) group is exercised through
     `RegisterCache.redact_serials()` with a standard serial
     (`test_redact_serials_inverter_hr_group`). Both paths share
     `Converter.redact_serial()`, so this is a missing test combination — byte-swapped
     value through `redact_serials()` specifically — not a verified leak risk.
- **Fix plan:**
  - [ ] Add `"MR": MR` to `_reg_cls` in `redact_serials()`, and either add `meter` to the
        module walk + change the meter serial to `C.serial`, or append an explicit
        `("MR", 60, 2)` group like the BMU/legacy entries.
  - [ ] Add `Plant.redact()` (redacts all caches + both string fields), or at minimum a
        prominent docstring warning on `Plant` and `redact_serials()`.
  - [ ] Completeness: add the missing combination — a byte-swapped AIO serial through
        `RegisterCache.redact_serials()` HR(8–12) (the `FrameRedactor` path already covers
        this value shape).
  - [ ] Consider auto-discovering serial groups by walking all `RegisterGetter` subclasses
        instead of a hardcoded module list, so future device types can't silently miss
        coverage (same failure mode as the meter gap).

### H3 — `/tmp/givenergy-coordination` inbox is a prompt-injection vector (operational, not library)

> **Amended 2026-06-10 (post-review): severity downgraded to Medium; premise corrected.** The
> directory as deployed is `0755` and owned by the operating user, so *other* local users cannot
> create or replace files inside it (the original "any local user can plant a file" claim was
> wrong). The residual risks are narrower: (a) the **fixed well-known path** means whoever
> creates the directory first after a reboot owns it — a pre-creation race, since `/tmp` is
> cleared on macOS restarts; and (b) **same-UID processes** can write into it — but they can
> equally write to `~/.local/share` or the agent's own config, so relocating the directory does
> not mitigate that attacker model. The mitigations that actually move the needle are the
> ownership check at creation time and treating inbox content as untrusted data.

- **Where:** `AGENTS.md` coordination-inbox protocol; `.claude/settings.json` Stop hook
  (`check-inbox.sh`); live dir `/tmp/givenergy-coordination`
- **Status:** verified protocol + dir permissions; `check-inbox.sh` contents not inspectable
  from this worktree (lives under `$CLAUDE_CONFIG_DIR`)
- **Detail:** The inbox protocol tells the agent to scan after every turn and decide whether to
  "immediately act" on file contents. The agent holds a `ghbot` token with repo-write and
  workflow-trigger scope, so injected instructions would have real blast radius (merge PRs,
  trigger releases). This is the one finding where an attacker would gain *agency* rather than
  data — tempered by the corrected premise above: exploiting it requires winning the
  directory-creation race on a rebooted machine, or code already running as the user (at which
  point most other avenues are open too).
- **Fix plan:**
  - [ ] Have the creating side enforce ownership/mode at creation (`mkdir -m 0700` semantics,
        refuse to use a pre-existing dir owned by another UID), and have `check-inbox.sh` skip
        files not owned by the current UID (`find -user "$(id -u)"`).
  - [ ] Reframe the protocol so inbox content is treated as untrusted data to summarise —
        acting on it requires explicit user confirmation. This is the primary mitigation, since
        it also covers the same-UID case relocation can't fix.
  - [ ] Verify what `check-inbox.sh` actually enforces today.

---

## Medium priority

### M1 — Write responses don't verify the echoed value

- **Where:** `givenergy_modbus/pdu/write_registers.py` (`_extra_shape_hash_keys` covers
  `device_address` + `register`, not `value`); `givenergy_modbus/client/client.py`
  (`send_request_and_await_response` checks only `response.error`)
- **Detail:** If the inverter silently clamps/rejects a value but echoes a different one (or a
  LAN peer forges an ack), the future resolves as success. Caller believes e.g. charge limit
  is 50 when the device wrote 0. Given the hardware-safety posture, the echoed value should be
  checked.
- **Fix plan:**
  - [ ] Compare `response.value` to the requested value in the write path; log WARNING (or
        raise, behind an option) on mismatch. (Including `value` in the shape hash is the
        stricter alternative but changes response-correlation semantics — decide explicitly.)

### M2 — Log injection via device-supplied strings; serials logged unredacted

- **Where:** `givenergy_modbus/pdu/null.py:45`, `givenergy_modbus/pdu/heartbeat.py` →
  `client.py` heartbeat warning; `givenergy_modbus/model/register.py:285`
  (`is_valid_serial` WARNING); `read_registers.py` `is_suspicious()` debug dump
- **Detail:** Serial fields are decoded latin-1 (all 256 byte values pass, including `\n`/`\r`)
  and embedded raw in f-string log messages — a spoofed frame can fabricate log lines (SIEM
  spoofing, hiding activity). Separately, `is_valid_serial` logs full real serials at WARNING,
  and the `is_suspicious()` debug dump includes HR(13–17) serial bytes.
- **Fix plan:**
  - [ ] Use `%r`/`repr()` for every device-provided string in log calls (repr escapes control
        chars).
  - [ ] Redact serials before logging in `is_valid_serial` (log prefix + length, or apply
        `Converter.redact_serial`).

### M3 — `FrameRedactor` lacks the framer's length cap

- **Where:** `givenergy_modbus/client/client.py:166-171` vs `givenergy_modbus/framer.py:185`
- **Detail:** The capture-time redactor trusts `hdr_len` up to 0xFFFF and waits for up to
  ~64 KB before processing. (Not the memory-exhaustion issue originally reported — buffering is
  bounded per frame — but a spoofed length field stalls/desyncs redacted captures.)
- **Fix plan:**
  - [ ] Apply the same `hdr_len > 300` guard; on violation, skip past the marker and resume
        scanning.

### M4 — Tampered cache JSON / adversarial register values crash consumers

- **Where:** `givenergy_modbus/model/register_cache.py:90-110` (`from_json` object hook
  validates keys, stores values unchecked); `givenergy_modbus/model/register.py`
  (`Converter.timeslot`, `Converter.datetime`); `model/__init__.py` (`TimeSlot.from_repr`)
- **Detail:** No code-execution risk (plain `json.loads`, verified). But a string value in a
  cache JSON propagates until `int("x")` / `.to_bytes` on str raises deep in converters; and
  device-supplied raw values like month=0 or hour=24 raise `ValueError` from
  `datetime()`/`time()` inside `from_register_cache()`. The enum path already degrades to
  `None` on bad values — these should match.
- **Fix plan:**
  - [ ] In `register_object_hook`, coerce values with `int(v)` and skip (with a warning) on
        failure.
  - [ ] Wrap `Converter.datetime` / `Converter.timeslot` conversions in
        `try/except ValueError: return None`, matching the enum posture.

### M5 — CI supply chain: mutable action pins, long-lived PAT, missing permissions blocks

- **Where:** `.github/workflows/release.yml`, `dev.yml`, `preview.yml`
- **Detail:**
  - Third-party actions pinned to tags; `pypa/gh-action-pypi-publish@release/v1` is a *branch*
    ref, inside the job holding `id-token: write` (PyPI trusted publishing) and secrets.
  - `peaceiris/actions-gh-pages` uses long-lived `secrets.PERSONAL_TOKEN`.
  - `dev.yml` / `preview.yml` have no `permissions:` block (inherit default token scope).
- **Fix plan:**
  - [ ] Pin third-party actions (at minimum `pypa/gh-action-pypi-publish`,
        `peaceiris/actions-gh-pages`, `softprops/action-gh-release`, `codecov-action`) to full
        commit SHAs with a version comment; Dependabot already watches `github-actions`.
  - [ ] Replace `PERSONAL_TOKEN` with `GITHUB_TOKEN` + `pages: write` (or a fine-grained,
        expiring token scoped to the Pages repo).
  - [ ] Add `permissions: contents: read` to `dev.yml` and `preview.yml`.

---

## Low priority / hygiene

### L1 — `bool` passes the write-value type guard
`write_registers.py` `isinstance(value, int)` accepts `True`/`False` (bool subclasses int).
Harmless for the boolean registers that rely on it; a bool passed to a numeric register writes
0/1 silently.
- [ ] Reject `bool` in the guard; have boolean commands pass `int(enabled)` explicitly.

### L2 — Mixin-level `WRITE_SAFE_REGISTERS` is documentation-only and has drifted
`client/commands.py` `_InverterCommands.WRITE_SAFE_REGISTERS` is never consulted; the PDU-level
set enforces. The mixin set is currently a stale subset.
- [ ] Add a test asserting the mixin set ⊆ PDU set, or delete the mixin set.

### L3 — Error-response retry path doesn't cancel the old future
`client.py` retry-on-error continues without `response_future.cancel()` (the timeout path does
cancel). Old future is already done so practical risk is low; make the paths symmetric.
- [ ] Add `response_future.cancel()` before `continue` on the error path.

### L4 — `frame_sent` timeout sized from `qsize()` after `put()`
`client.py` `timeout=self.tx_queue.qsize() + 1` can be unrealistically short under load
(producer may have already drained the queue when sampled).
- [ ] Snapshot depth before `put()` or use a fixed generous timeout.

### L5 — `RegisterCache.json()` emits unredacted serials without warning
- [ ] Docstring note pointing callers at `redact_serials().json()` for anything shared.

### L6 — Defensive-decode tidy-ups (parsing layer)
- `pdu/base.py:76-83`: the commented-out broad `except` means `decode_bytes` is only safe
  because the framer's outer catch exists; restore an `except Exception → InvalidFrame` wrap so
  the decode boundary is complete for all callers (the `FrameRedactor` already needed its own).
- `pdu/null.py:30-35`: short null frames log a size warning then die in `struct.error`; add an
  early `InvalidFrame` guard.
- `framer.py:104`: `_buffer` is a class-level default relying on `bytes` immutability; move to
  `__init__`.
- `pdu/transparent.py:114-115`: the LanConfig discriminator can false-positive on a crafted
  padding field (`…\x00\x2C`), causing a valid response to be dropped (timeout). Tighten the
  check to require the preceding six padding bytes to be zero.
- `commands.py` `set_system_date_time`: years < 2000 produce a confusing encode-time
  `InvalidPduState`; add an explicit `ValueError` guard.

---

## Confirmed non-issues / defences that work

- **No eval/exec/pickle/dynamic class lookup from wire or JSON data** anywhere; function-code
  dispatch is explicit conditionals.
- **Framer:** 300-byte frame cap enforced before accumulation (`framer.py:185`); buffer trimmed
  to 3 bytes when no marker found (garbage floods bounded); broad catch at the trust boundary
  converts all decode exceptions to `InvalidFrame` so the consumer loop can't be killed.
- **Decode:** register counts capped at 60; `struct.unpack` raises on truncation (no silent
  zero-fill); count/values consistency enforced.
- **Write path:** `WRITE_SAFE_REGISTERS` enforced in `ensure_valid_state()` called from
  `encode()` — no public path around it; 16-bit bounds check blocks wrap-around; range guards
  on all dangerous commands; enums validated at the command layer; no read-then-write TOCTOU.
- **Client:** tx queue bounded (maxsize 20); per-retry future cancellation on the timeout path;
  outgoing CRC computed on every encode.
- **Redaction that works:** all LUT-declared `C.serial` groups across inverter/battery/EMS/
  gateway, BMU groups (8× stride), legacy HR(8–12); redaction operates on a copy;
  `LanConfigBroadcast.redact()` zeroes IPs. No registers hold WiFi credentials, GPS, or
  account/cloud tokens.
- **CI/supply chain:** no `pull_request_target`/`workflow_run`/`issue_comment` triggers; no
  `${{ github.event.* }}` interpolated into `run:` blocks; untrusted values routed through
  `env:`; PyPI publishing via OIDC trusted publishing; `uv.lock` fully hash-pinned; Dependabot
  on pip + actions; release scripts use literal-arg subprocess (no `shell=True`).
- **Repo hygiene:** no committed secrets; every capture fixture checked had serials and IPs
  properly redacted, with the policy documented in the fixtures README.

---

## Suggested sequencing

1. **Quick wins (single PR):** H1 minimum fix (WARNING log), M2 repr-in-logs, M3 redactor
   length cap, L3, L4, L5 — small, low-risk, mostly one-liners.
2. **Redaction integrity (single PR + tests):** H2 in full — meter group, `Plant.redact()`,
   byte-swap regression test, auto-discovery refactor. This restores the #212 guarantee.
3. **Write-path assurance (its own PR, register-safety review required):** M1 echoed-value
   check, L1 bool guard, L2 subset test. Touches `commands.py`/`write_registers.py`, so route
   through the register-safety review process.
4. **Robustness pass:** M4 + L6 — adversarial-input crash fixes in converters and decode
   boundary tidy-ups, with fuzz-style tests for `from_json` and converters.
5. **Infra (no code):** M5 workflow hardening; H3 inbox hardening per the amended fix plan —
   creation-time ownership checks + treat-inbox-as-untrusted protocol (coordinate across the
   three sister repos' AGENTS.md).
