# Security Policy

This is an open-source library maintained in personal time. I take security
seriously and will respond on a best-effort basis — but please understand there
is no SLA, and I can't promise a fixed turnaround.

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** rather than opening a
public issue:

- Use GitHub's **["Report a vulnerability"](https://github.com/dewet22/givenergy-modbus/security/advisories/new)**
  button (the **Security** tab → **Advisories**). This opens a private security
  advisory only the maintainer can see, and lets us coordinate a fix before any
  public disclosure.

If you'd rather not use GitHub, raise a normal issue asking me to get in touch
and I'll arrange a private channel — but don't put exploit detail in the public
issue.

When reporting, the most useful things to include are: the affected version, a
description of the impact, and enough detail to reproduce (a frame capture, a
register sequence, or a short script). Redact any real serial numbers or IP
addresses first.

## Supported versions

| Version | Status |
|---|---|
| 2.2.x (pre-release) | Active development — fixes land here first |
| 2.1.x | Current stable — security fixes backported |
| 2.0.x | Support branch — security/critical fixes only |
| < 2.0 | Unsupported |

## Scope and threat model

This library speaks Modbus TCP to GivEnergy inverters. A few properties shape
what counts as a vulnerability:

- **The protocol has no authentication or transport encryption.** Any device or
  process on the same LAN segment can send arbitrary bytes to a listening client,
  and an on-path attacker can substitute response contents. Parse robustness
  against hostile input is in scope; the lack of protocol-level auth itself is a
  property of Modbus, not a bug in this library.
- **The library writes to real grid hardware.** Write-path integrity (the
  `WRITE_SAFE_REGISTERS` allowlist, bounds checks, command validation) matters as
  much as parse safety. Reports that bypass those guards are high value.
- **Cache exports are intended to be share-safe.** `RegisterCache.redact_serials()`
  exists so a cache dump can be shared for debugging without leaking identifiers.
  Gaps in that redaction are in scope.

## Known hardening backlog

A point-in-time security review is committed at
[`SECURITY-AUDIT-2026-06-10.md`](SECURITY-AUDIT-2026-06-10.md), and the
remediation work is tracked openly in the security hardening issue. None of the
items found were critical remote vulnerabilities; they are being addressed in the
open as ordinary hardening.
