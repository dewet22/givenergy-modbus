# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/olivierlacan/keep-a-changelog/compare/v0.6.2...HEAD
[0.6.2]: https://github.com/mindsers/changelog-reader-action/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/mindsers/changelog-reader-action/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/mindsers/changelog-reader-action/compare/v0.5.0...v0.6.0
