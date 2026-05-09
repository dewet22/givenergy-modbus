# Modernisation Plan: givenergy-modbus 1.0

## Context

The `getting-ready-for-1.0` branch contains a large refactoring that has been dormant for ~3 years. The codebase had accumulated significant technical debt: a Python version mismatch that broke 3 test modules, Pydantic v1 usage, a redundant linting stack, and outdated dependencies.

**Goal:** Bring the codebase to a modern Python/packaging standard, suitable for publishing as 1.0.

**Baseline:** Python 3.14 (local development), targeting `>=3.13`.

---

## Phase 1 — Fix the Python version mismatch ✅ DONE

**Problem:** `inverter.py` imported `StrEnum` from `enum` (stdlib only on 3.11+), but `pyproject.toml` declared `python = ">=3.9,<3.12"` and the venv ran Python 3.9.6. This prevented 3 test files from even being collected.

**Completed changes:**
- `pyproject.toml`: bumped `python = ">=3.13"`, classifiers updated to 3.13/3.14
- `pyproject.toml`: removed `aenum` — `StrEnum`/`IntEnum` are stdlib on 3.11+
- `pyproject.toml`: removed `toml` — replaced by stdlib `tomllib` on 3.11+
- `pyproject.toml`: removed `aiofiles` (only in commented-out code) and `types-aiofiles` *(pulled forward from Phase 4)*
- `pyproject.toml`: removed `pytkdocs` from docs deps *(pulled forward from Phase 4)*; updated all docs deps to current versions
- `pyproject.toml`: bumped `pytest` → `^9.0.0`, `pytest-asyncio` → `^1.0.0`, `pytest-cov` → `^7.0.0`, `pytest-timeout` → `^2.4.0` — required for Python 3.14 (`ast.Str` was removed)
- `pyproject.toml`: pinned `pyyaml = ">=6.0.2"` in dev deps to unblock build on Python 3.14
- `setup.cfg`: updated `min_python_version`, tox matrix, and gh-actions matrix to 3.13/3.14
- `.pre-commit-config.yaml`: updated `pyupgrade` target to `--py313-plus`
- `black` target versions updated to `py313`/`py314`

**Remaining blocker:** Pydantic v1 is incompatible with Python 3.14 — `typing_extensions` tries to subclass `typing.TypeVar` which became a non-subclassable builtin in 3.14. **Tests cannot run until Phase 3 (Pydantic v2) is complete.** Phases 1 and 3 are effectively coupled for this Python baseline.

---

## Phase 2 — Replace linting/formatting stack with `ruff`

**Problem:** Four separate tools (`black`, `isort`, `flake8`, `autopep8`) do what `ruff` handles alone, faster and with a single config.

**Changes:**
- `pyproject.toml` test deps: add `ruff`, remove `black`, `isort`, `flake8`, `flake8-docstrings`, `flake8-typing-imports`, `autopep8`, `pydocstyle`, `types-tabulate`
- `pyproject.toml`: add `[tool.ruff]` and `[tool.ruff.lint]` sections migrating all rules from `setup.cfg [flake8]`
- `setup.cfg`: migrate `[mypy]`, `[coverage:run]`, `[coverage:report]`, `[tox:tox]`, `[tool:pytest]` into `pyproject.toml`, then delete `setup.cfg`
- `.pre-commit-config.yaml`: replace `black`, `isort`, `flake8`, `autopep8` hooks with `ruff` and `ruff-format`; bump all other hook revisions
- Fix any lint errors surfaced by ruff

**Risk:** Low–medium. Ruff is a superset of the old rules; there may be a handful of new lint hits to fix.

---

## Phase 3 — Pydantic v2 migration

**Problem:** The model layer uses Pydantic v1 APIs removed in v2, and pydantic v1 is incompatible with Python 3.14.

Specific v1 APIs in use:
- `pydantic.utils.GetterDict` — removed
- `BaseConfig` with `orm_mode`, `allow_mutation`, `frozen` — replaced by `ConfigDict`
- `create_model(..., __config__=...)` — API changed
- `Model.from_orm(register_cache)` — renamed to `Model.model_validate(..., from_attributes=True)`

**Approach:**

The `RegisterGetter` (a `GetterDict` subclass) resolves field values from a `RegisterCache` by walking the `REGISTER_LUT`. Since `GetterDict` is gone in v2, replace the ORM protocol entirely with an explicit classmethod:

```python
# Before (v1)
Inverter.from_orm(register_cache)

# After (v2)
InverterRegisterGetter.build(register_cache)  # returns Inverter instance
```

`build()` iterates `REGISTER_LUT`, calls the same pre/post conversion logic, produces a plain `dict`, and passes it to `Inverter.model_validate(values)`.

**File-by-file changes:**
- `givenergy_modbus/model/register.py`: remove `GetterDict` import and `RegisterGetter` base; rewrite `RegisterGetter` as a standalone class with a `build(cache) -> dict` method; remove `RegisterEncoder` (unused)
- `givenergy_modbus/model/inverter.py`: replace `InverterConfig(BaseConfig)` + `create_model` with a plain `class Inverter(BaseModel)` with `model_config = ConfigDict(frozen=True)`; add `from_register_cache` classmethod
- `givenergy_modbus/model/battery.py`: same pattern as inverter
- `givenergy_modbus/model/__init__.py`: replace `class Config` inner class with `model_config = ConfigDict(...)`; remove v1 `allow_mutation`/`frozen` usage
- `givenergy_modbus/model/plant.py`: replace `from_orm` calls with `from_register_cache`; update `Config` inner class
- `tests/model/test_device.py`: update to use new API
- All other test files: update any `from_orm` calls

**Risk:** High. This is the most invasive change. The test suite for inverter/plant is extensive (`test_inverter.py`: 684 lines, `test_plant.py`: 1191 lines) and will act as a good regression guard. Also unblocks running any tests on Python 3.14.

---

## Phase 4 — Remove unused/outdated dependencies

**Remaining items** (several pulled forward into Phase 1):
- Remove `arrow` — used only as the type of the `dt` parameter in `commands.set_system_date_time()`; replace with `datetime.datetime`; update `tests/client/test_commands.py` accordingly
- Remove `bump2version` — replaced by `bump-my-version` or `poetry version`
- Verify `crccheck` is still actively used in `codec.py`
- Run `poetry lock` and commit updated lockfile

**Risk:** Low. Each removal is isolated and testable.

---

## Phase 5 — Type annotation modernisation

**Changes (mechanical, file by file):**
- `Optional[X]` → `X | None`
- `Dict[K, V]` / `List[X]` / `Tuple[X, ...]` → `dict`, `list`, `tuple`
- `Union[X, Y]` → `X | Y`
- `Type[X]` → `type[X]`
- `asyncio.get_event_loop()` → `asyncio.get_running_loop()` in `client/client.py` (deprecated since 3.10)
- Remove `from __future__ import annotations` where no longer needed
- Remove quotes around type annotations where they were needed only for forward refs

Files requiring attention: `client/client.py`, `client/commands.py`, `framer.py`, `model/register.py`, `model/register_cache.py`, `pdu/base.py`

**Risk:** Low. Purely cosmetic from a runtime perspective; `mypy` will catch any mistakes.

---

## Phase 6 — CI/CD update

**Changes:**
- `.github/workflows/dev.yml`, `release.yml`, `preview.yml`: pin to current action versions (`actions/checkout@v4`, `actions/setup-python@v5`, `actions/cache@v4`)
- Update Python matrix to `['3.13', '3.14']`
- Replace `flake8`/`black`/`isort` CI steps with `ruff check` and `ruff format --check`
- Add `mypy` as an explicit CI step if not already present
- Verify `poetry-check` and `poetry-lock` hooks pass

**Risk:** Low.

---

## Completion criteria

- All tests pass on Python 3.13 and 3.14
- `ruff check` and `ruff format --check` are clean
- `mypy givenergy_modbus tests` is clean (or has a tracked suppression list)
- `poetry build` and `twine check dist/*` succeed
- No Pydantic v1 imports remain
- No `Optional`, `Dict`, `List`, `Tuple` from `typing` remain in library code
- `setup.cfg` is deleted
