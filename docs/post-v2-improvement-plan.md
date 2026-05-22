# Post-v2.0 Improvement Plan

This plan captures concrete follow-up work after the v2.0 release. The focus is
hardware safety, protocol reliability, and maintainability rather than new user
features.

## Existing GitHub coverage

The repository currently tracks v2.1 work with a `v2.1` issue label rather than
a GitHub milestone. Some items below overlap existing issues:

| Plan item | Existing coverage |
|---|---|
| Execution-time write policy | Partly covered by [#75](https://github.com/dewet22/givenergy-modbus/issues/75), which moves commands onto inverter models so model-specific command contracts are enforceable. The extra client-boundary rejection remains distinct. |
| Dry-run write validation | Not currently captured. |
| Internal refresh serialization | Not currently captured. |
| Fail CI on async resource warnings | Not currently captured. |
| Register provenance and confidence | Partly covered by [#48](https://github.com/dewet22/givenergy-modbus/issues/48), which tracks field-validation of inherited mappings. Provenance metadata remains distinct. |
| Broader golden-frame fixtures | Adjacent to closed [#66](https://github.com/dewet22/givenergy-modbus/issues/66), which shipped the in-cli capture mechanism, and open [#78](https://github.com/dewet22/givenergy-modbus/issues/78), the active corruption-pattern investigation that produces sample captures as a byproduct. Committing those captures as durable, redacted test fixtures across device families remains distinct work. |
| Stricter type checking | Not currently captured. |
| Cleaner release artifact checks | Not currently captured. |
| Documentation warning cleanup | Not currently captured. |
| Public API compatibility tests | Not currently captured. |

The remaining v2.1-labelled issues are tracked independently of this plan:
[#65](https://github.com/dewet22/givenergy-modbus/issues/65),
[#71](https://github.com/dewet22/givenergy-modbus/issues/71),
[#72](https://github.com/dewet22/givenergy-modbus/issues/72),
[#73](https://github.com/dewet22/givenergy-modbus/issues/73),
[#74](https://github.com/dewet22/givenergy-modbus/issues/74), and
[#76](https://github.com/dewet22/givenergy-modbus/issues/76). They're
roadmap items rather than the infrastructure focus of this document.

## 1. Execution-time write policy

Add a write policy check at the client execution boundary, not only at command
construction time.

Current protection is centered on `WriteHoldingRegisterRequest` and the global
`WRITE_SAFE_REGISTERS` allowlist. Model-specific command mixins also define
smaller safe-write sets, but callers can still manually construct write PDUs.

Target outcome:

- `Client.one_shot_command()` and `Client.execute()` can reject writes that are
  not valid for the detected inverter model.
- The default remains conservative when model capabilities are unknown.
- Tests cover direct `WriteHoldingRegisterRequest` construction, not just
  high-level command helpers.

## 2. Dry-run write validation

Add a supported way to validate write requests without sending frames to
hardware.

Target outcome:

- A caller can encode and validate request lists before transmission.
- Validation reports the register, value, device address, and reason for any
  rejection.
- Downstream integrations can use this before enabling live writes.

Possible API shapes:

- `client.validate_requests(requests)`
- `client.one_shot_command(requests, dry_run=True)`

## 3. Internal refresh serialization

Move refresh serialization into `Client` instead of relying only on downstream
consumers to lock around polling.

Current documentation correctly says callers should avoid overlapping
`refresh_plant()` calls. An internal `asyncio.Lock` would make accidental
overlap safer.

Target outcome:

- `detect()`, `load_config()`, `refresh()`, and `refresh_plant()` cannot mutate
  `plant` concurrently.
- Writes can still interleave where safe.
- Tests cover overlapping refresh calls and detect/refresh interaction.

## 4. Fail CI on async resource warnings

Keep async test leaks visible by treating unawaited coroutine and unraisable
exception warnings as failures.

Target outcome:

- CI fails on `PytestUnraisableExceptionWarning`.
- CI fails on unawaited coroutine `RuntimeWarning`.
- The existing timeout test remains warning-clean.

Suggested pytest flags:

```bash
pytest -W error::pytest.PytestUnraisableExceptionWarning -W error::RuntimeWarning tests
```

## 5. Register provenance and confidence

Make provisional register knowledge explicit in the model definitions.

Some LUT entries come from field captures or related projects rather than
official documentation. That is normal for this domain, but the source and
confidence should be visible.

Target outcome:

- `RegisterDefinition` can optionally carry provenance metadata.
- Docs can distinguish verified, field-observed, and provisional registers.
- High-risk writes require stronger provenance before being added to safe-write
  sets.

Possible metadata:

- `source="field-capture"`
- `source="GivTCP"`
- `verified=True`
- `risk="provisional"`

## 6. Broader golden-frame fixtures

Add redacted binary TX/RX fixtures for representative device families and use
them in decoder/framer/client tests.

Target fixture coverage:

- Single-phase inverter
- Three-phase inverter
- EMS
- Gateway
- HV BCU/BMU stack
- External meter
- Write response success and error cases

Target outcome:

- Protocol changes can be checked against real frame shapes.
- Redaction remains guaranteed for captured serial numbers.
- Edge cases are represented by durable fixtures rather than only constructed
  PDUs.

## 7. Stricter type checking

Gradually enable `mypy --check-untyped-defs`.

Current mypy output notes that several untyped function bodies are not checked.
This is not urgent, but it is a useful way to catch mistakes in protocol and
test helper code.

Target outcome:

- Enable `check_untyped_defs = true` after fixing the first wave of findings.
- Keep generated or intentionally dynamic Pydantic model code scoped with local
  ignores where needed.
- Avoid weakening public types to satisfy mypy.

## 8. Cleaner release artifact checks

Ensure release validation checks only freshly built artifacts.

Current local `twine check dist/*` can include older files in `dist/`, which is
harmless but noisy.

Target outcome:

- Release scripts clean `dist/` before building, or check only the files built
  in the current run.
- CI output shows only the version being released.

## 9. Documentation warning cleanup

Fix the MkDocs warning for the relative `../LICENSE` link in `docs/index.md`.

Target outcome:

- `mkdocs build` emits no project-specific warnings.
- The license link works both in GitHub-rendered Markdown and the published
  docs site.

## 10. Public API compatibility tests

Add explicit tests for documented imports, deprecated aliases, and common
downstream usage patterns.

Target outcome:

- `Client` remains importable from documented paths.
- Deprecated aliases keep emitting `DeprecationWarning` until intentionally
  removed.
- Public command helpers remain importable and callable with documented
  signatures.
- Public API changes require matching changelog updates.
