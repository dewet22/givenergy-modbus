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

## Phase 3 — Pydantic v2 migration ✅ DONE

**Problem:** The model layer uses Pydantic v1 APIs removed in v2, and pydantic v1 is incompatible with Python 3.14.

**Completed changes:**
- `model/register.py`: Removed `GetterDict` base from `RegisterGetter`; rewrote as standalone class with explicit `__init__`, `build()`, and `get()` methods; added `Optional` wrapping in `to_fields()`; fixed `infer_return_type` to use `get_type_hints()` for Python 3.14 PEP 749 compatibility; added string annotations `-> "bool"` and `-> "Optional[datetime]"` on `Converter` methods to avoid class-scope name shadowing in lazy annotation evaluation
- `model/__init__.py`: Replaced `@dataclass` on `TimeSlot` with a plain class implementing `__init__`, `__eq__`, `__repr__`, and `__get_pydantic_core_schema__` — pydantic v2 ignores `__get_pydantic_core_schema__` on `@dataclass` types, so this was required to preserve `TimeSlot` instances in `model_dump()`
- `model/inverter.py`: Replaced `InverterConfig(BaseConfig)` + v1 `create_model`; now uses `__config__=ConfigDict(frozen=True, use_enum_values=True)`; added `from_register_cache()` classmethod
- `model/battery.py`: Same pattern as inverter
- `model/plant.py`: Replaced inner `class Config` with `model_config = ConfigDict(frozen=False, use_enum_values=True, arbitrary_types_allowed=True)`; replaced `__init__` override with `model_post_init`; replaced `from_orm()` with `from_register_cache()`
- `tests/model/test_device.py`: Full rewrite — removed `BaseConfig`/`FooConfig`, updated `create_model`, updated all `from_orm` → `model_validate(getter.build())`, `.dict()` → `.model_dump()`, `.json()` → `json.loads(.model_dump_json())`, `.schema()` → `.model_json_schema()`, test_getter assertions updated for `Optional[X]` return types
- `tests/model/test_battery.py`, `test_inverter.py`, `test_plant.py`: Updated all `from_orm` → `from_register_cache`, `.dict()` → `.model_dump()`, `.json()` → `.model_dump_json()`

**Key Python 3.14 findings:**
- PEP 749 (accepted for 3.14) causes lazy annotation evaluation in class scope. Methods named after builtins (`Converter.bool`, `Converter.datetime`) have their `->` return annotations resolved to themselves rather than the builtin at access time. Fix: use string literals `-> "bool"` and `-> "Optional[datetime]"`.
- Pydantic v2 ignores `__get_pydantic_core_schema__` on stdlib `@dataclass` types; must use a plain class instead.

**Result:** All 182 tests pass. `ruff check` clean.

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
