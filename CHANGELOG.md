# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
  - `set_mode_storage(slot_1, [slot_2], [export])` which keeps the battery charge topped-up and discharges
    during specified periods. This mirrors modes 2-4 in the portal.
  - `set_datetime(datetime)` to set the inverter date & time.
- Ensure we _always_ close the socket after every network socket. Sometimes the inverter turns orange/grey
  in the portal after executing queries via this library, and this seems to mitigate against it.

### Changed
- **Potentially breaking:** Wholesale renaming of registers to more official designations, and standardising
  naming somewhat. Part of the motivation for adding more convenience functions is so clients never have to deal
  with register names directly, so this should hopefully make future renaming easier.

## [0.7.0] - 2022-01-05
### Added
- Another register whitelist and check in the `WriteHoldingRegisterRequest` PDU as another layer of checks
  to not inadvertently write to unsafe registers. Add a test to ensure the allow list stays in sync with
  the register definitions from `model.register_banks.HoldingRegister`.
- A bunch of convenience methods to write data to the inverter without needing any knowledge of registers.
  See `client.GivEnergyClient` which has a number of `set_*` methods.

### Changed
- Split out the end-user client functionality from the Modbus client - they were getting too entangled
  unnecessarily. Updated example code in README for reference.
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
  `Inverter` object is shaping up nicely as a user-friendly representation of the inverter dataset – TODO is
  likely splitting out a `Battery` representation too, to account for systems with multiple battery units (and
  those without batteries at all!). The same might make sense for the PV aspect as well.

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

[Unreleased]: https://github.com/dewet22/givenergy-modbus/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/dewet22/givenergy-modbus/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/dewet22/givenergy-modbus/compare/v0.6.2...v0.7.0
[0.6.2]: https://github.com/dewet22/givenergy-modbus/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/dewet22/givenergy-modbus/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/dewet22/givenergy-modbus/compare/v0.5.0...v0.6.0
