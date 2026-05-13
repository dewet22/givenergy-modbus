# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- add AGENTS.md with accurate architecture and dependency info ([d7bc6a2](https://github.com/dewet22/givenergy-modbus/commit/d7bc6a26af689ed66e8d5453105cc3a6c172e642), @dewet22)
- update claude config ([6cd077e](https://github.com/dewet22/givenergy-modbus/commit/6cd077e74c08ea6fc79f4e4e69683af7127d8761), @dewet22)
- add logo; rationalise badges; fix Python capitalisation in blurb ([6c4ef4d](https://github.com/dewet22/givenergy-modbus/commit/6c4ef4d234213196c4fd95d4eca130fa7c8e319d), @dewet22)

### Maintenance

- add Claude Code automations (hooks, skills, MCP, subagent) ([00929f9](https://github.com/dewet22/givenergy-modbus/commit/00929f941733b6f27a60676c0b94a91a5ffcccdf), @dewet22)
- ignore Claude Code local settings and worktrees ([634dd08](https://github.com/dewet22/givenergy-modbus/commit/634dd08d1bebc1aac1a47d87356c57af4ae26254), @dewet22)

## [1.3.0] - 2026-05-13

### Maintenance

- notify downstream consumers on release via repository_dispatch (#53) ([2a03623](https://github.com/dewet22/givenergy-modbus/commit/2a036231236f681451eb395ce87fe89ad3377488), @dewet22)

### Fixed

- prevent deadlock after inverter maintenance disconnect (#54) ([4469b7a](https://github.com/dewet22/givenergy-modbus/commit/4469b7af7713c9cfffef95e072acf9f3c38f5ca5), @dewet22)

## [1.2.0] - 2026-05-11

### Changed

- rewrite with commit attribution and full history backfill ([1fbf3c2](https://github.com/dewet22/givenergy-modbus/commit/1fbf3c2009a4c0b63b0ab9017c6c926c9686cf00), @dewet22)
- Update givenergy_modbus/model/battery.py ([128e3ba](https://github.com/dewet22/givenergy-modbus/commit/128e3ba83ec7be4e5fa3f52462c0a80d37dd6cec), @dewet22)
- fix off-by-one and replace assert in Plant.number_batteries ([75f8425](https://github.com/dewet22/givenergy-modbus/commit/75f842524105936f0e3b7d5d8b64ef137171e465), @dewet22)

### Fixed

- stop ValueError on battery decode aborting number_batteries (#49, #51) ([27e97b3](https://github.com/dewet22/givenergy-modbus/commit/27e97b36130f938d0d2c2fa1f921fe034c9be16e), @dewet22)
- downgrade CRITICAL shutdown logs on intentional client.close() (#50) ([d21cf66](https://github.com/dewet22/givenergy-modbus/commit/d21cf665011a1ab954c2db1eb2898a3aa10b105d), @dewet22)
- drop battery_soc_reserve=100 from set_mode_storage (#27) ([a6e5a1f](https://github.com/dewet22/givenergy-modbus/commit/a6e5a1f3f8860e90e01791ac776ee143dcc5e8a8), @dewet22)
- keep parens around multi-exception except for py313 compatibility ([cd40d2f](https://github.com/dewet22/givenergy-modbus/commit/cd40d2f2a4773686f89139de729acf574b0db531), @dewet22)
- append every commit on push to [Unreleased], not just head_commit ([5ea934d](https://github.com/dewet22/givenergy-modbus/commit/5ea934dcc224fdcd101dff627c461cb410a3fbcd), @dewet22)

### Maintenance

- align with usb_device_inserted field name retained by Codacy revert ([a471c9a](https://github.com/dewet22/givenergy-modbus/commit/a471c9a49e115aa9902d28cef6899dd30d53fd90), @dewet22)

## [1.1.2] - 2026-05-11

### Maintenance

- replace tag-triggered release with workflow_dispatch ([dc78952](https://github.com/dewet22/givenergy-modbus/commit/dc789525805118aa881736ea4564cb61d207d188), @dewet22)
- add Dependabot GitHub Actions version tracking ([e1680f9](https://github.com/dewet22/givenergy-modbus/commit/e1680f9cb597b4cea7d5f9f1526890d0c67ceae6), @dewet22)

## [1.1.1] - 2026-05-11

### Maintenance

- downgrade codecov upload failure to warning ([12a3085](https://github.com/dewet22/givenergy-modbus/commit/12a30859f38966d3b9c82d32e3cf9769d8919661), @dewet22)

### Changed

- migrate from Poetry to uv for dependency management ([c8c6156](https://github.com/dewet22/givenergy-modbus/commit/c8c615619f869bbc1f615f5fc992554cd7778a49), @dewet22)

### Fixed

- handle ConnectionResetError when closing client connection ([b7109f1](https://github.com/dewet22/givenergy-modbus/commit/b7109f1f11d4330ef872108aa191c429de3e144d), @dewet22)

## [1.1.0] - 2026-05-09

### Changed

- modernise type annotations and fix bandit/prek hooks ([6d8c50f](https://github.com/dewet22/givenergy-modbus/commit/6d8c50f99779bf744e1473cef4b2094a023aa95b), @dewet22)
- bump inverter model to 1.1.0: new registers, computed battery_capacity_kwh, enum fix ([23b9cb8](https://github.com/dewet22/givenergy-modbus/commit/23b9cb80bd1446ef1d00d2f9f3af59bab7d10ce5), @dewet22)

## [1.0.2] - 2026-05-09

### Changed

- remove unnecessary fail-fast: false from release workflow ([2b65001](https://github.com/dewet22/givenergy-modbus/commit/2b6500157737ec58606979d3bb2e1c5b4f47ac15), @dewet22)
- use Python 3.14 as default; fix __version__ when package not installed ([f46a4a4](https://github.com/dewet22/givenergy-modbus/commit/f46a4a41b7cf3dd21fe5e0ec9015f14e297272a2), @dewet22)
- update ruff target-version to py314 ([867b90a](https://github.com/dewet22/givenergy-modbus/commit/867b90a69e7cb2b76ed7824debeb468977fde805), @dewet22)
- update docs for v1.0.0 API ([bd21ab5](https://github.com/dewet22/givenergy-modbus/commit/bd21ab5833962797516b26f237845ef0d531a87e), @dewet22)
- update root-level docs and config ([3935f9d](https://github.com/dewet22/givenergy-modbus/commit/3935f9d2efb12ac3b0557b2e6745943f728ca848), @dewet22)

## [1.0.1] - 2026-05-09

### Changed

- move docs publish to after pypi release in release workflow ([ffc0b13](https://github.com/dewet22/givenergy-modbus/commit/ffc0b133c814cf288f704452af05d2f91417ec81), @dewet22)
- Set package-ecosystem to 'pip' in dependabot config ([93228e6](https://github.com/dewet22/givenergy-modbus/commit/93228e6a601e15709dae7336436f6914ca4e2f0a), @dewet22)
- update poetry.lock to resolve 32 dependabot alerts ([d396420](https://github.com/dewet22/givenergy-modbus/commit/d3964209fc9c63a4e0ef67430de28bc37a78c2c3), @dewet22)
- bump all GitHub Actions to current versions ([e83b8b1](https://github.com/dewet22/givenergy-modbus/commit/e83b8b1df9ea15e2633a4312a100754521f8e418), @dewet22)
- fix release workflow: remove invalid fail_ci_if_error, use skip-existing ([075a7dd](https://github.com/dewet22/givenergy-modbus/commit/075a7dd10a050ec8d0b206e75ad227495eb14760), @dewet22)
- update README for v1.0.0 API ([f54fbcb](https://github.com/dewet22/givenergy-modbus/commit/f54fbcb8c3a2b4508cb77abc64abdad33963b62f), @dewet22)
- credit pymodbus as inspiration in README ([14103c8](https://github.com/dewet22/givenergy-modbus/commit/14103c810070bdbe1c3d25ebc8aa37d9dbd2b5f8), @dewet22)
- migrate to prek, remove stale tooling, clean up post-1.0 ([adcfe87](https://github.com/dewet22/givenergy-modbus/commit/adcfe8716559a46ec0d3d33ab6b97b8d94a42fcc), @dewet22)
- fix release workflow: Linux-only publish steps, fail-fast false ([db01aaa](https://github.com/dewet22/givenergy-modbus/commit/db01aaa9ce71ddafe726f63d89b0390ad9b2efd7), @dewet22)

## [1.0.0] - 2026-05-09

A completely different approach to this library, handling comms in an asynchronous thread to avoid the old synchronous blocking and polling strategy. That started a rabbit hole of largely re-doing the entire architecture.

### Added

- New asyncio `Client` with long-lived connections, producer/consumer task pair, and `Future`-based response tracking — replaces the old synchronous `GivEnergyClient`.
- Passive monitoring mode: listen-only client that observes traffic without sending commands.
- `Plant.update(pdu)` for incremental state updates from incoming PDU responses; `Plant` now dynamically discovers the number of attached batteries.
- Comprehensive holding register coverage: all HR(0–300+) mapped and typed, including `charge_slot_2`, `battery_discharge_mode`, `battery_calibration_stage`, `modbus_address`, `modbus_version`, `system_time`, `enable_60hz_freq_mode`, `enable_drm_rj45_port`, `inverter_reboot`, and ~30 additional fields.
- Virtual aggregates: `p_pv_power`, `e_pv_total`, and related computed fields.
- Custom exception hierarchy for richer, typed error handling.
- Community contributions: inverter register additions from @holdestmade and @dominic.

### Changed

- PDUs now encode and decode themselves; `Framer` refactored to pass raw frames to the callback and invoke it on decode failure as well as success.
- `RegisterCache` bound to an explicit slave address; sanity-check gates stale or malformed PDU updates.
- Registers refactored to plain data containers; behaviour (validation, scaling, conversion) moved into `Inverter` and `Battery` models.
- `Coordinator` renamed to `Client`; network layer folded into the same class.
- `TimeSlot` moved to the model package.
- Python 3.9+ minimum (Python 3.7 and 3.8 dropped).
- modernisation phases 1 & 2: Python 3.13+, ruff, drop legacy tooling ([18ca4dc](https://github.com/dewet22/givenergy-modbus/commit/18ca4dc1c34fb2308910a87c5250c0e2f5bed131), @dewet22 🎉)
- modernisation phase 3: pydantic v2 migration ([98b89fd](https://github.com/dewet22/givenergy-modbus/commit/98b89fde6cbe99dbed1e7458de445d736884e4a1), @dewet22)
- modernisation phase 4: remove arrow and bump2version deps ([ee6b5c0](https://github.com/dewet22/givenergy-modbus/commit/ee6b5c03319858c7595888d185270e7ac1f940cd), @dewet22)
- modernisation phase 5: type annotation modernisation ([568a722](https://github.com/dewet22/givenergy-modbus/commit/568a72260df01882a5134186a2eaf9428383196b), @dewet22)
- modernisation phase 6: CI/CD update ([142be88](https://github.com/dewet22/givenergy-modbus/commit/142be88ed296b09fb2aade5938c101c276bfe0f0), @dewet22)
- note missing Gen 2 (EA prefix) inverter model support ([cd131bb](https://github.com/dewet22/givenergy-modbus/commit/cd131bba4561941a8536d990896c61e6b5296567), @dewet22)
- fix CI failures on Python 3.13/3.14 ([450e2dc](https://github.com/dewet22/givenergy-modbus/commit/450e2dc574e41de953374ad8dfc3bea242522e64), @dewet22)
- bump outdated dev/test dependencies ([8cce166](https://github.com/dewet22/givenergy-modbus/commit/8cce166939de9309edf55786ed110c54a0b753c4), @dewet22)
- bump mypy to ^2.0.0 and fix newly surfaced type errors ([24c64ad](https://github.com/dewet22/givenergy-modbus/commit/24c64ad5c3225172c7f7b579f89e92d2acb8d3de), @dewet22)
- fix mkdocs deprecation warnings ([dd4f546](https://github.com/dewet22/givenergy-modbus/commit/dd4f54612d9e0af91310b47ada4ca04cc90510eb), @dewet22)
- add security fix tests and tidy changelog ([2a22379](https://github.com/dewet22/givenergy-modbus/commit/2a22379519840747af7c3902bcdd2c97137af56a), @dewet22)

### Removed

- `pymodbus` runtime dependency — the Modbus protocol is now implemented entirely in-library.
- Old synchronous CLI (spun out to a separate package).

### Security

- fix five issues identified in audit ([2e38d5e](https://github.com/dewet22/givenergy-modbus/commit/2e38d5e010a61216faed357a73b088fe4f323137), @dewet22)

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
