# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-05-09

### Security

- Fixed broken register value bounds check in `WriteHoldingRegister.ensure_valid_state`: the condition
  `0 > self.value > 0xFFFF` is a Python chained comparison that is always `False`, so out-of-range values
  were silently accepted. Corrected to `self.value < 0 or self.value > 0xFFFF`.
- Fixed class-level mutable `expected_responses = {}` on `Client` — shared across all instances, causing
  response futures from concurrent clients to collide. Now initialised per-instance in `__init__`.
- Fixed `NullResponse.__init__` reading decoded nulls from the wrong kwargs key (`"base_register"` instead
  of `"nulls"`), causing the decoded payload to be silently discarded and the non-null sanity check to never
  trigger.
- `RegisterCache.from_json` now logs a warning and skips unrecognised register keys instead of raising
  `ValueError`, preventing a crash on malformed JSON input.
- `ReadRegistersResponse` decoding now caps `register_count` at 60 before allocating the register values
  list, preventing buffer exhaustion from a crafted response with an oversized count field.



Complete modernisation of the library to Python 3.13+, pydantic v2, and a new asyncio-based messaging architecture.

### Added

- Asyncio-based client: long-lived connections with a network producer/consumer task pair. Incoming messages are
  dispatched via `Future`s so command results can be awaited rather than polled.
- `Plant.update(pdu)` method for incremental state updates from incoming PDUs.
- `Inverter.from_register_cache()` and `Battery.from_register_cache()` classmethods replacing `from_orm()`.
- `RegisterGetter` standalone class with `build()` and `get()` methods (replaces pydantic v1 `GetterDict`).
- `ruff` for linting and formatting (replaces `flake8`, `black`, `isort`, `autopep8`, `pydocstyle`).

### Changed

- ⚠️ Breaking change: the complete client API has been rewritten around asyncio. Dependent consumers will need to
  update — see `README.md` for updated usage examples.
- ⚠️ Minimum Python version raised to **3.13**. Python 3.7–3.12 are no longer supported.
- Migrated from **pydantic v1** to **pydantic v2**: `model_validate()`, `model_dump()`, `model_dump_json()`,
  `ConfigDict`, and `model_json_schema()` throughout. `TimeSlot` converted from `@dataclass` to a plain class with
  a custom `__get_pydantic_core_schema__` to preserve instances in `model_dump()`.
- `set_system_date_time()` now accepts `datetime.datetime` instead of `arrow.Arrow`.
- Type annotations modernised to PEP 604 (`X | None`, `X | Y`) and PEP 585 (`list[X]`, `dict[K, V]`, `tuple[X]`).
- `asyncio.get_event_loop()` replaced with `asyncio.get_running_loop()`.
- CI matrix updated to Python 3.13 and 3.14; GitHub Actions pinned to current versions.
- `setup.cfg` removed; all tool configuration now lives in `pyproject.toml`.

### Removed

- `arrow` runtime dependency — replaced by `datetime.datetime`.
- `bump2version` dev dependency — use `poetry version` instead.
- `black`, `isort`, `flake8`, `autopep8`, `pydocstyle`, `flake8-docstrings`, `flake8-typing-imports`,
  `types-tabulate` — all replaced by `ruff`.
- `aenum`, `toml`, `aiofiles` — replaced by stdlib equivalents (`enum.StrEnum`, `tomllib`, removed).
- Support for Python 3.7–3.12.

## [0.10.1] - 2022-03-03

### Fixed

- 🛠 Make `Plant` serializable.

## [0.10.0] - 2022-03-02

### Added

- 💪 Reintroduced the battery energy totals on the `Battery` model. On some firmware versions that is populated instead
  of the values from the inverter. (#7, via @britkat1980)

### Changed

- ⚠️ Breaking change: rejigged the `Plant` model to abstract away `RegisterCache`s and remove some of the toil around
  managing state. `README.md` updated with example implementation.

## [0.9.4] - 2022-02-15

### Added

- 🛠 Enable CodeQL GitHub workflow for automated code quality scans

### Fixed

- 🐛 Allow multiple serial number prefixes to map to the same inverter model name (#6, by @zaheerm)

## [0.9.3] - 2022-02-01

### Fixed

- 🧽 Update total energy registers (by @britkat1980)
- 🛠 Re-enable builds back to python v3.7 to support e.g. Raspberry Pi current version
- 🧹 Update python and pre-commit deps, including security fix for loguru

## [0.9.2] - 2022-01-24

### Fixed

- 🐛 Scaled registers to use division instead of multiplication – prevents rounding errors.
- 📖 Update README.md to match reality better
- 🧽 Update deps
- 🛠 Try to re-enable GH pages

## [0.9.1] - 2022-01-13

### Fixed

- 🐛 The `_time` fault registers don't denote a BCD-encoded timestamp, but seems to be a counter of #cycles the fault
  lasted.
- Sometimes a time slot timestamp is returned as `60` minutes. Guard by taking the modulo-60 instead.

## [0.9.0] - 2022-01-13

### Added

- 💪 Create `RegisterCache` and `RegisterGetter` to contain the custom register data structures in one place. Also
  started a `Plant` model to be a container for all devices in a given system.
- 🛠 Add JSON processing for the RegisterCache – mostly to help with testing but also expecting debugging other plants
  to benefit from it.
- 👷 Add some more test cases with actual register data.
- 🚨 Added some recovery logic to the framer – try to scan ahead for other messages instead of truncating the entire
  buffer when there's unexpected data incoming. Hopefully this helps when the communication stream seems to get out of
  sync a bit.
- 🙅 Add an `ErrorResponse` PDU so we can try and cope better when the inverter throws error responses.
- 🧽 Added `absolufy-imports` and `autoflake` to pre-commit checks.

### Changed

- ⚠️ Ensure we check charge and discharge limits: current hardware cannot support >50% (i.e. >2.6kW) rates.
- ✅ Make sure we query the 180+ block of input registers too, since it contains (amongst others) battery energy
  counters.
- 🤔 Split out querying the battery/BMS registers since this will vary depending on how many batteries the user has. The
  slave address of the request determines which battery unit is targeted.
    - Also start modeling the Battery as separate from the Inverter.
- 🔎 Collapse the register cache to a single dict since we can use the `HoldingRegister`/`InputRegister` identity to
  discern between the types. It makes the data structures a lot simpler.
- 🛠 Improve the CLI – it is already a useful tool to dump registers for debugging right now.
- 😳 Changed to target slave id 0x11 by default instead of 0x32. 0x32 shadows 0x11 but seems to be the first battery,
  with subsequent batteries living at the following slave addresses.
    - ☝️ reverted that change because it seems to affect the cloud metrics quite badly when you query frequently.
- 🤫 Squelch flake8 warnings about missing constructor and magic method docstrings.
- 🩹 Update README to show usage properly.
- 🧹 Update python deps.

## [0.8.0] - 2022-01-09

### Added

- A large number of convenience methods in the client to alter the state of the inverter:
    - `enable_charge_target(target_soc: int)` & `disable_charge_target()`
    - `enable_charge()` & `disable_charge()`
    - `enable_discharge()` and `enable_discharge()`
    - `set_battery_discharge_mode_max_power()` and `set_battery_discharge_mode_demand()`
    - `set_charge_slot_n((start_time: datetime.time, end_time: datetime.time))` and `reset_charge_slot_n()`
      for slots 1 & 2. Also matching `set_discharge_slot_n((start_time, end_time))` and `reset_discharge_slot_n()`.
    - `set_mode_dynamic()` to maximise storage of generation and discharge during demand. This mirrors "mode 1"
      operation in the portal.
    - `set_mode_storage(slot_1, [slot_2], [export])` which keeps the battery charge topped-up and discharges during
      specified periods. This mirrors modes 2-4 in the portal.
    - `set_datetime(datetime)` to set the inverter date & time.
- Ensure we _always_ close the network socket after every request. Sometimes the inverter turns orange/grey in the
  portal after executing queries via this library, and this seems to mitigate against it – possible the inverter TCP
  stack isn't closing half-closed sockets aggressively enough?

### Changed

- **Potentially breaking:** Once again, pretty wholesale renaming of registers to more official designations, and
  standardising naming somewhat. Part of the motivation for adding more convenience functions is so clients never have
  to deal with register names directly, so this should hopefully make future renaming easier.

## [0.7.0] - 2022-01-05

### Added

- Another register whitelist and check in the `WriteHoldingRegisterRequest` PDU as another layer of checks to not
  inadvertently write to unsafe registers. Add a test to ensure the allow list stays in sync with the register
  definitions from `model.register_banks.HoldingRegister`.
- A bunch of convenience methods to write data to the inverter without needing any knowledge of registers.
  See `client.GivEnergyClient` which has a number of `set_*` methods.

### Changed

- Split out the end-user client functionality from the Modbus client - they were getting too entangled unnecessarily.
  Updated example code in README for reference.
- Renamed `target_soc` to `battery_target_soc` instead.

## [0.6.2] - 2022-01-04

### Fixed

- Will this fix `mindsers/changelog-reader-action@v2`?

## [0.6.1] - 2022-01-04

### Fixed

- Fix stupid pypi classifier strictness

## [0.6.0] - 2022-01-04

### Changed

- **[BREAKING CHANGE]** registers have been widely renamed for consistency and clarity. The joys of a pre-release API.
- Checked all the registers and their values to make sense. Added units for most that are self-evident. The
  `Inverter` object is shaping up nicely as a user-friendly representation of the inverter dataset – TODO is likely
  splitting out a `Battery` representation too, to account for systems with multiple battery units (and those without
  batteries at all!). The same might make sense for the PV aspect as well.

### Fixed

- Avoid loading a whole batch of input registers that seem completely unused and save a network call.
- Match prod release workflow to preview to use py3.9
- Update PyPI classifiers to specify Alpha quality :)

## 0.5.0 (2022-01-04)

- Simplify the client contract so you only work with structured data instead of register banks.
- Add example use to README

## 0.4.0 (2022-01-03)

- Implement writing values to single holding registers

## 0.3.0 (2022-01-03)

- Make register definitions a bit more flexible to cater for units and descriptions in future

## 0.2.0 (2022-01-03)

- Fix GitHub actions & codecov

## 0.1.1 (2022-01-02)

- Update deps
- Rename a few class names for consistency
- Add a few more attributes to export

## 0.1.0 (2022-01-02)

- First release on PyPI

[Unreleased]: https://github.com/dewet22/givenergy-modbus/compare/v1.0.0...HEAD

[1.0.0]: https://github.com/dewet22/givenergy-modbus/compare/v0.10.1...v1.0.0

[0.10.1]: https://github.com/dewet22/givenergy-modbus/compare/v0.10.0...v0.10.1

[0.10.0]: https://github.com/dewet22/givenergy-modbus/compare/v0.9.4...v0.10.0

[0.9.4]: https://github.com/dewet22/givenergy-modbus/compare/v0.9.3...v0.9.4

[0.9.3]: https://github.com/dewet22/givenergy-modbus/compare/v0.9.2...v0.9.3

[0.9.2]: https://github.com/dewet22/givenergy-modbus/compare/v0.9.1...v0.9.2

[0.9.1]: https://github.com/dewet22/givenergy-modbus/compare/v0.9.0...v0.9.1

[0.9.0]: https://github.com/dewet22/givenergy-modbus/compare/v0.8.0...v0.9.0

[0.8.0]: https://github.com/dewet22/givenergy-modbus/compare/v0.7.0...v0.8.0

[0.7.0]: https://github.com/dewet22/givenergy-modbus/compare/v0.6.2...v0.7.0

[0.6.2]: https://github.com/dewet22/givenergy-modbus/compare/v0.6.1...v0.6.2

[0.6.1]: https://github.com/dewet22/givenergy-modbus/compare/v0.6.0...v0.6.1

[0.6.0]: https://github.com/dewet22/givenergy-modbus/compare/v0.5.0...v0.6.0
