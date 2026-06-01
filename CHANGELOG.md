# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0b7] - 2026-06-01

### 🐛 Fixed

- response CRC integrity + frame-aware capture redactor (#158) ([a06f97a](https://github.com/dewet22/givenergy-modbus/commit/a06f97a1ca88af91ef1dd5e7b2fdcec2836ed0d6))

## [2.1.0b6] - 2026-06-01

### 🐛 Fixed

- treat residential All-in-One as single-phase (#105) ([0bb591b](https://github.com/dewet22/givenergy-modbus/commit/0bb591bdcfdf5d5087cd445565de2aad094d0452))

## [2.1.0b5] - 2026-06-01

### 🐛 Fixed

- include device address + byte-swap in request CRC (#105) ([b85b33a](https://github.com/dewet22/givenergy-modbus/commit/b85b33a270088a54ab7d3fed3060ba67eca244b2))

### 🔧 Maintenance

- drop now-redundant FC 0x16 CRC override ([421f92b](https://github.com/dewet22/givenergy-modbus/commit/421f92b1134d8f5e2f03286c7a3a7c4d4395e276))

## [2.1.0b4] - 2026-06-01

### 🐛 Fixed

- refuse to poll without capabilities instead of guessing 0x32 (#105) ([ae0502c](https://github.com/dewet22/givenergy-modbus/commit/ae0502c6e6dcb9e02621150901842bf604e98041))
- warn when refresh_plant max_batteries is passed (now ignored) ([d1d6cf8](https://github.com/dewet22/givenergy-modbus/commit/d1d6cf899f96f48aef0dbf1c76aed3b3e2ccb550))
- keep refresh_plant_data as a deprecated raising stub ([e044541](https://github.com/dewet22/givenergy-modbus/commit/e0445414192301b74b7693cd464078e4dcc29ed5))

### 🔧 Maintenance

- consolidate CLAUDE.md into AGENTS.md as single source of truth (#155) ([55c411c](https://github.com/dewet22/givenergy-modbus/commit/55c411c87390d341e06655ddae0f4da0e2d8f2b7))
- pin detect-before-poll order in refresh_plant no-caps test ([16c2768](https://github.com/dewet22/givenergy-modbus/commit/16c2768bbc4f1b653c33e45b4a510f5d554f4af6))

## [2.1.0b3] - 2026-06-01

### ✨ Added

- add export_priority (HR311) and enable_eps (HR317) for AC inverters ([732643c](https://github.com/dewet22/givenergy-modbus/commit/732643c73d5e9be6e95b64d8f966cf03d2096a2d))

### 🐛 Fixed

- clamp zero month/day in to_datetime to prevent crash (#153) ([30f4a5f](https://github.com/dewet22/givenergy-modbus/commit/30f4a5f523a08b8e119e9d8326a8da2b725aefed))
- add HR311/317 to PDU write allowlist; validate AC setters ([d1c3634](https://github.com/dewet22/givenergy-modbus/commit/d1c3634ed0dc7e4fd05eb599ee50d7a35d1b5cb9))

## [2.1.0b2] - 2026-05-31

### ✨ Added

- add is_ac_coupled topology discriminator ([376e87b](https://github.com/dewet22/givenergy-modbus/commit/376e87b2bb52c1776ca1ff5ac0ad577e2ab7f16c))

### 🔧 Maintenance

- pin AC-limit register consistency, document 3ph gap (#75) ([9a8ee7b](https://github.com/dewet22/givenergy-modbus/commit/9a8ee7b050a2b1c1fc31062b5ff09ffe5aedde66))

## [2.1.0b1] - 2026-05-31

### ✨ Added

- route battery-energy registers by model, not live values (#76) ([85f49ce](https://github.com/dewet22/givenergy-modbus/commit/85f49ce09429e461ffd28acac5ebecc858b08de5))

### 🐛 Fixed

- re-apply low-risk model-layer fixes reverted from v2.0 (#74) ([a83f314](https://github.com/dewet22/givenergy-modbus/commit/a83f31465e8b8b6571910cef50d696189efd4c74))
- redact serials split across capture-frame boundaries (#117) ([1cecc03](https://github.com/dewet22/givenergy-modbus/commit/1cecc0396b809335ef5ae02d67ad9c3365624e02))

### 🔧 Maintenance

- clear actionable in-code TODOs ([a92818f](https://github.com/dewet22/givenergy-modbus/commit/a92818f49547136974f72c9ec8a42a57cf4e56ca))
- reconcile v2.1 roadmap with shipped reality (a3→a11) ([d3458e1](https://github.com/dewet22/givenergy-modbus/commit/d3458e1e4a06f30ab6ae6b7b1c359c19781ec5a7))

## [2.1.0a11] - 2026-05-31

### ✨ Added

- add plant_enabled boolean read-back for Flexi EMS control ([a4386d5](https://github.com/dewet22/givenergy-modbus/commit/a4386d51b1f1c787ba5cac15b9158746f060ac3b))

## [2.1.0a10] - 2026-05-30

### ✨ Added

- add EMS-named export slot setters for API parity ([341a595](https://github.com/dewet22/givenergy-modbus/commit/341a59590fc8927d0cd2ff647c5e1514b0c7a16e))

## [2.1.0a9] - 2026-05-30

### 🐛 Fixed

- raise refresh default budget to 2.0s/1 retry for contended buses ([7318590](https://github.com/dewet22/givenergy-modbus/commit/7318590979b0bbf01366541d02255ef184bf984a))

### 🔧 Maintenance

- bump uv to 0.11.17 to clear file-write advisory ([83ffa2d](https://github.com/dewet22/givenergy-modbus/commit/83ffa2d13c7048e259c4b4474f12ad45e6dff4cb))
- clarify physical measurement points for single-phase grid power registers ([961af80](https://github.com/dewet22/givenergy-modbus/commit/961af804e3b4df50ea70196e93b5632ee5d08f0d))

## [2.1.0a8] - 2026-05-30

### ✨ Added

- add per-endpoint EMS slot setters for API parity ([eea1e78](https://github.com/dewet22/givenergy-modbus/commit/eea1e78bdf29e961b357a50a526530306b79842a))

## [2.1.0a7] - 2026-05-30

### ✨ Added

- EMS plant-level charge/discharge/export write support ([925cdc2](https://github.com/dewet22/givenergy-modbus/commit/925cdc2478e1fca3d3b457050e8d8e2c87be694b))

### 🐛 Fixed

- recognise EMS serial format in is_valid_serial ([014095d](https://github.com/dewet22/givenergy-modbus/commit/014095d2ca5eeb1eaa5cf1c48e94d87801ee8bf6))

### 🔧 Maintenance

- golden-master classification/topology checks over captures ([8d55372](https://github.com/dewet22/givenergy-modbus/commit/8d55372b7a087dea9111aaae28e705c262e41f07))

## [2.1.0a6] - 2026-05-30

### ✨ Added

- expose per-attribute display precision derived from register scaling (#129) ([2dda112](https://github.com/dewet22/givenergy-modbus/commit/2dda1128d9dad66c2ff6dfec1bb6814e8955c70d))

## [2.1.0a5] - 2026-05-29

### ✨ Added

- read EMS rollup at detect time + sanity-check it (#109) ([918a33a](https://github.com/dewet22/givenergy-modbus/commit/918a33a00fc8356fb5e771526eeb76463f41ae58))
- preserve manufacture-date digits in serial redaction (#116) ([4661483](https://github.com/dewet22/givenergy-modbus/commit/4661483a6251583ef6b0205d7119ce2a9d95eb37))

### 🔄 Changed

- ⚠️ Breaking: raise RefreshPartiallySucceeded/RefreshFailed on partial/total poll failure (#125) ([3493dd1](https://github.com/dewet22/givenergy-modbus/commit/3493dd1656e98be4c39e264b1608ddf337fb58b9))

### 🐛 Fixed

- detect missing EMS rollup registers, not just missing cache (#111) ([9fb8786](https://github.com/dewet22/givenergy-modbus/commit/9fb8786a15cb59592d1ad11dbc394f1e91f11615))
- address inverter at its model-specific device address, not 0x32 (#119) ([0200292](https://github.com/dewet22/givenergy-modbus/commit/0200292d238cf2a6dbf86e0612631d389ea31848))

### 🔧 Maintenance

- add EMS/hybrid/AIO topology captures + per-plant READMEs (#120) ([1476beb](https://github.com/dewet22/givenergy-modbus/commit/1476beb82b49a08eafc3fb84093c692f3f8c46fe))
- run per-PR checks on Linux only, cross-OS on a weekly schedule ([c2bd2e1](https://github.com/dewet22/givenergy-modbus/commit/c2bd2e193858a01fbb6f564b9d23485bc1ce7553))
- add live device-address probe diagnostics (#119/#124) ([fb001cb](https://github.com/dewet22/givenergy-modbus/commit/fb001cb6027d1d6e5b49a435fee3eac9f90fd26b))

## [2.1.0a4] - 2026-05-28

### ✨ Added

- unified Inverter facade for EMS-managed plant topology (#98) ([4cb40b0](https://github.com/dewet22/givenergy-modbus/commit/4cb40b02948ef6d466b48c7ff84ca661f575c514))
- seed tests/fixtures/captures with real EMS-plant wire data (#103) ([5376582](https://github.com/dewet22/givenergy-modbus/commit/53765823fb7d4bc3a04987a91193465ed9e51ab4))

### 🐛 Fixed

- skip inverter-style HR/IR reads on EMS plant controllers (#93) ([cecd06d](https://github.com/dewet22/givenergy-modbus/commit/cecd06dbf54e47753f6929d177b169763f83711c))
- drop empty meter slots in detect() via Meter.is_valid() (#96) ([1c21bfa](https://github.com/dewet22/givenergy-modbus/commit/1c21bfa806a5130b7cdb25924cecce896ac7175a))
- exercise strip path with partial-padding serial in EMS rollup test (#102) ([57a6dcc](https://github.com/dewet22/givenergy-modbus/commit/57a6dccf784536a45c308e7d8256dd2183c11c86))
- extend redact() for EMS serials and IPv4 addresses (#99) ([ae4f84d](https://github.com/dewet22/givenergy-modbus/commit/ae4f84dc7b8831be62d7d08f2dcac377ce72b079))

### 🔧 Maintenance

- add §2 back-reference on a5 to mirror the a4 stretch note ([721d904](https://github.com/dewet22/givenergy-modbus/commit/721d9042cecd66364bb9a252592e25f4eeffe1aa))

## [2.1.0a3] - 2026-05-27

### 🔄 Changed

- enable mypy check_untyped_defs for production code ([ace9701](https://github.com/dewet22/givenergy-modbus/commit/ace970188008a5617b0a7bad9dc48536ebdff81d))

### 🔧 Maintenance

- fetch full git history in release workflow so CHANGELOG generator works ([2f446b7](https://github.com/dewet22/givenergy-modbus/commit/2f446b7c1554b2bb9028c1ca2e5e6d965d8f10b7))
- sketch v2.1 release roadmap as a chain of small alphas ([43ec1c4](https://github.com/dewet22/givenergy-modbus/commit/43ec1c479bdcb72cb89f3e3b03eb5523da8e253d))
- use absolute LICENSE URL so include-markdown resolves it under docs/ ([e11b298](https://github.com/dewet22/givenergy-modbus/commit/e11b29843898063ea81523a7442dcdada071e496))
- build into envtmpdir so twine checks only the current run's artifacts ([f6ae7a7](https://github.com/dewet22/givenergy-modbus/commit/f6ae7a72aeef0c35fc8c6bcfe855076e4ad3d17a))
- escalate unawaited-coroutine and unraisable warnings to errors ([c169c02](https://github.com/dewet22/givenergy-modbus/commit/c169c023ccef49cb2c934f15921bd64b8927c371))
- update roadmap to reflect what shipped in 2.1.0a3 ([afc8526](https://github.com/dewet22/givenergy-modbus/commit/afc852626bcf09bb4dae3ad8f46997d2e3a8854f))

## [2.1.0a2] - 2026-05-27

First 2.1 alpha. Spans all work on the `v2.1` branch since it diverged
from `main` at the v2.0.0 release, so includes equivalents of every
patch shipped in the v2.0.1–v2.0.4 maintenance line as well as the v2.1
feature work.

### ✨ Added

- Client.detect(prior=) for fast restarts; serialisable PlantCapabilities ([811a143](https://github.com/dewet22/givenergy-modbus/commit/811a1438b5db59a806327bf6e265707021689827))
- add tx_jitter knob to disperse producer bursts (#71) ([d5f4337](https://github.com/dewet22/givenergy-modbus/commit/d5f433771f2d52071f8c8197bfa239f1512813ad))

### 🔄 Changed

- ⚠️ Breaking: rename work_time_total to work_time_total_hours ([9b737d9](https://github.com/dewet22/givenergy-modbus/commit/9b737d9af40953e5dea39203ceffaac1c5553dc8))
- ⚠️ Breaking: migrate PlantCapabilities to Pydantic v2 (#72) ([52caaf0](https://github.com/dewet22/givenergy-modbus/commit/52caaf058ddbebd58e0ae6ebc9ced80f9f7828bf))
- ⚠️ Breaking: migrate RegisterDefinition to Pydantic v2 (#73) ([f83928e](https://github.com/dewet22/givenergy-modbus/commit/f83928ed6d0c84815e714a0300e37206c0f2eabc))

### 🐛 Fixed

- address #81 review feedback (BCU drift, address coercion, docs) ([46ddfae](https://github.com/dewet22/givenergy-modbus/commit/46ddfaec6c6d4154cae2b0865b9fe6c2974ef9a4))
- document and bound work_time_total unit (#84) ([757c2c9](https://github.com/dewet22/givenergy-modbus/commit/757c2c9ed33cb7b9595fae3f73cc78ece87c0430))
- suppress out-of-bounds register values instead of passing through (#82) ([151d7ff](https://github.com/dewet22/givenergy-modbus/commit/151d7ff8dc5af648313e1102f31abea4100653ee))
- discard Pattern A IR(0,60) responses before they reach the cache (#78) ([9b3c490](https://github.com/dewet22/givenergy-modbus/commit/9b3c4908940b4cb84fd69dcf56c6838a2a74733f))
- accept v2.0.0 PlantCapabilities payloads in from_dict() ([2c8327d](https://github.com/dewet22/givenergy-modbus/commit/2c8327deb6ca30931b8bfb0b221ada99145bffbe))
- coerce bcu_stacks tuple entries to int in from_dict() ([00152b6](https://github.com/dewet22/givenergy-modbus/commit/00152b66b69fee40e2d054c7ee4ba8bfaa467cf7))
- harden from_dict against int device_type and null list fields ([3cb7cf9](https://github.com/dewet22/givenergy-modbus/commit/3cb7cf91f8f59451b6cefef86981f777eb29ea02))
- include error flag in WriteHoldingRegister equality (with unskipped tests) ([e8f289c](https://github.com/dewet22/givenergy-modbus/commit/e8f289cd7e8967dd0eab7a7c78c34f5d3a3e219c))
- harden against malformed-frame DoS cases (#88) ([6555bea](https://github.com/dewet22/givenergy-modbus/commit/6555bea11f98cc0666a24c390ebb479d5f177d57))
- refine review feedback on #88 hardening ([a82f432](https://github.com/dewet22/givenergy-modbus/commit/a82f432386998cd149c0f304f9f40296d9edba49))
- guard p_pv()/e_pv_day() against None inputs (#85) (#92) ([962951a](https://github.com/dewet22/givenergy-modbus/commit/962951a60da0c0a009d8738cf6c4ea8fa222a81f))
- address gemini-code-assist feedback on PR #94 ([aee7990](https://github.com/dewet22/givenergy-modbus/commit/aee79900405e48c9abc196864fc2503a8b882dab))

### 🔧 Maintenance

- add post-v2.0 improvement plan + correct stale #66 reference ([39c14d4](https://github.com/dewet22/givenergy-modbus/commit/39c14d464f274ca07cf5d4596723aca925fe2919))
- reframe section 1 of plan as model-aware vs PDU-level ([198a86f](https://github.com/dewet22/givenergy-modbus/commit/198a86f7b7678bb0c6fb674ad3324ea5087f7dcf))
- add offline wire-capture replay harness (#82) ([7f72c97](https://github.com/dewet22/givenergy-modbus/commit/7f72c97b5ae492ea0cb85287c1361b3c5f2b6396))
- cover Model-instance passthrough in from_dict() _device_type ([1719521](https://github.com/dewet22/givenergy-modbus/commit/17195210e8dd94a5832b9a41e3387371c6b6a017))
- clarify write PDU hashability scope ([6c0f808](https://github.com/dewet22/givenergy-modbus/commit/6c0f808d45951cc61b3868b6278cbae0bc7ac398))
- bump the uv group across 1 directory with 2 updates (#77) ([79c46ad](https://github.com/dewet22/givenergy-modbus/commit/79c46adf45859102a55404de3de38bf47fc8a206))
- cross-reference open-giv/bms-analysis and document TCP-cache layering ([08b0195](https://github.com/dewet22/givenergy-modbus/commit/08b0195d942f086a91449e9bf1de8f5a6af51822))
- close leaked Queue.put coroutine in tx-queue-full timeout test ([cba5f7a](https://github.com/dewet22/givenergy-modbus/commit/cba5f7afaf1304e28bccac0f90a3e9e5a68fc9dd))
- pin actions-gh-pages to v4.1.0 for Node 24 runtime ([b3c0fd5](https://github.com/dewet22/givenergy-modbus/commit/b3c0fd5006fe64ea1698ecb43eea35923b8caacc))
- hoist ValidationError import to module top per coderabbit nit ([58f1504](https://github.com/dewet22/givenergy-modbus/commit/58f1504e52bb4b0fa290571a47503cfb1013d87d))

## [2.0.0] - 2026-05-22

### 🔧 Maintenance

- enrich cli section of v2.0 release notes with v1.0 ecosystem story ([e87c8fe](https://github.com/dewet22/givenergy-modbus/commit/e87c8fe3ad730fc488feb2e6df55130a7b891f13))

## [2.0.0rc1] - 2026-05-19

### ✨ Added

- support prerelease stage transitions in release.py bump ([00ce5c3](https://github.com/dewet22/givenergy-modbus/commit/00ce5c3069faa16d3c772eb38cef768e6044970e))

## [2.0.0a6] - 2026-05-15

### 🔧 Maintenance

- address Gemini review on Converter.int32 and Converter.bitfield ([67af9c8](https://github.com/dewet22/givenergy-modbus/commit/67af9c80b82c9986cd4c2aa487849984faa422ce))

## [2.0.0a5] - 2026-05-15

### 🔧 Maintenance

- bring Codacy-equivalent coverage in-house; suppress noise ([945641a](https://github.com/dewet22/givenergy-modbus/commit/945641a5c1d1b56ecc62d1a05eec4291b60f754e))

## [2.0.0a4] - 2026-05-15

### ✨ Added

- add retry_delay knob and complete late-arrival wire-skip optimisation ([522795d](https://github.com/dewet22/givenergy-modbus/commit/522795d1c9ebd4727b71bc4c0762c61480ad4626))

## [2.0.0a3] - 2026-05-15

### 🐛 Fixed

- drop incoherent-bank discard log from WARNING to DEBUG ([1238975](https://github.com/dewet22/givenergy-modbus/commit/1238975cd96342d65dc5052d3adfb3bdbc047245), @dewet22)

## [2.0.0a2] - 2026-05-15

### 🐛 Fixed

- quieten bounds-violation logs and exempt all-zero raw banks ([a4501d7](https://github.com/dewet22/givenergy-modbus/commit/a4501d78a6bc78979126cbd18b66ae8587251b42), @dewet22)
- thread timeout/retries through refresh_plant() post-detect ([260af42](https://github.com/dewet22/givenergy-modbus/commit/260af4272817aaf77bab2f1f609babd969d2374a), @dewet22)
- use address-prefixed byte-swapped CRC for FC 0x16 requests ([a5b0b2c](https://github.com/dewet22/givenergy-modbus/commit/a5b0b2c036eeb26445e2ddf2085a11c66e8c1fa6), @dewet22)
- make Client.connect() idempotent and reset _shutting_down ([6c56889](https://github.com/dewet22/givenergy-modbus/commit/6c56889c68c63d323b5ce70ddf15b86345e1c61d), @dewet22)

### 🔧 Maintenance

- switch PyPI publishing to OIDC; add publish-tag.yml recovery workflow ([27a1dc4](https://github.com/dewet22/givenergy-modbus/commit/27a1dc4ad2604e72ed63feb10715bc11127d2917), @dewet22)
- fold republish-tag mode into release.yml ([759a04e](https://github.com/dewet22/givenergy-modbus/commit/759a04e357a280bf255b71b9f486b1a2371aebfc), @dewet22)

## [2.0.0a1] - 2026-05-14

A chunky update, incorporating a lot of the differences that GivTCP developed and introduced during the extended time being forked away. Kudos and credit to @britkat1980 for all the effort that I could crib from.

### ✨ Added

**New device models** — all modelled as siblings of `SinglePhaseInverter` / `Battery`, with `from_register_cache()` constructors and typed fields:

- `ThreePhaseInverter` for three-phase models (HR/IR 1000–1420), including grid protection limits, derating curves, per-phase measurements, EPS/backup mode, energy counters, slot registers, and `force_charge_enable` / `battery_maintenance_mode` ([09e37f0](https://github.com/dewet22/givenergy-modbus/commit/09e37f07174faa437e3d2cb236422c95b265112a), [95aba95](https://github.com/dewet22/givenergy-modbus/commit/95aba95), @dewet22)
- `Bcu` and `Bmu` model classes for HV battery stacks (AIO / HV Gen3 / AIO-Hybrid systems) ([ee15702](https://github.com/dewet22/givenergy-modbus/commit/ee1570282ecdc170347fec4cb09ece6f6f78a980), @dewet22)
- `Meter` and `MeterProduct` model classes for external meter slaves at addresses `0x01`–`0x08`, read via FC 0x04 and FC 0x16 respectively ([c6d3a0a](https://github.com/dewet22/givenergy-modbus/commit/c6d3a0a9aef54c7518daa32cb98f929465ea7468), @dewet22)
- `Ems` model for EMS plant status and configuration registers ([3621938](https://github.com/dewet22/givenergy-modbus/commit/36219386c8b40d08c6c0b1106faa2a8e10e53b96), @dewet22)
- `Gateway` and `Gateway2` models with `select_gateway()` for automatic firmware-version-based dispatch ([752160a](https://github.com/dewet22/givenergy-modbus/commit/752160afd6826a1233df7a9e8e6d997dfc65c764), @dewet22)
- `select_inverter(model, register_cache)` returns `SinglePhaseInverter | ThreePhaseInverter` based on device type ([071c755](https://github.com/dewet22/givenergy-modbus/commit/071c755), @dewet22)

**Plant and client lifecycle:**

- `PlantCapabilities` dataclass captures full device topology from `detect()`: device type, inverter address, LV battery / meter / HV BCU device addresses ([ffa78fc](https://github.com/dewet22/givenergy-modbus/commit/ffa78fc), @dewet22)
- `Client.detect()` for one-time device and peripheral discovery; `Client.refresh()` for fast IR measurement polling; `Client.load_config()` for HR configuration reads — replacing the old `refresh_plant_data()` monolith ([ffa78fc](https://github.com/dewet22/givenergy-modbus/commit/ffa78fc), [9936e98](https://github.com/dewet22/givenergy-modbus/commit/9936e98), @dewet22)
- Typed plant accessors — `plant.inverter`, `plant.batteries`, `plant.hv_stacks`, `plant.meters`, `plant.ems`, `plant.gateway` — all dispatch via `capabilities` rather than hardcoded device-address arithmetic ([9936e98](https://github.com/dewet22/givenergy-modbus/commit/9936e98), @dewet22)

**Commands:**

- `SlotMap` frozen dataclass for model-driven slot register routing; all slot setters now accept `slot_map: SlotMap = SINGLE_PHASE_SLOTS` — three-phase callers pass `plant.inverter.slot_map` ([a0c50e3](https://github.com/dewet22/givenergy-modbus/commit/a0c50e3), @dewet22)
- New command helpers: `set_battery_pause_mode`, `set_pause_slot`, `set_ac_charge`, `set_force_charge`, `set_force_discharge`, `set_enable_rtc`, `set_active_power_rate`, `set_battery_charge_limit_ac`, `set_battery_discharge_limit_ac`, `set_ems_plant`, `set_export_slot` ([8ca0b75](https://github.com/dewet22/givenergy-modbus/commit/8ca0b75), @dewet22)

**Register coverage and converters:**

- `MR` register namespace and `ReadMeterProductRegisters` PDU (FC 0x16) for meter product identification registers ([ef89324](https://github.com/dewet22/givenergy-modbus/commit/ef89324adc19996cbdb2f621ed848649ab822449), @dewet22)
- `resolve_model(dtc, arm_fw)` for firmware-version-aware device model resolution ([09dea7b](https://github.com/dewet22/givenergy-modbus/commit/09dea7b436fb2df11827c6d11c1f65646b6cd623), @dewet22)
- Extended `Model` enum: `HYBRID_GEN1/2/3/4`, `HYBRID_HV_GEN3`, `ALL_IN_ONE_HYBRID`, `POLAR`, `EMS_COMMERCIAL`, `AIO_COMMERCIAL`; existing single-character `Model(dtc)` lookups are unchanged ([09dea7b](https://github.com/dewet22/givenergy-modbus/commit/09dea7b436fb2df11827c6d11c1f65646b6cd623), @dewet22)
- New converters: `C.int32`, `C.bitfield`, `C.hexfield`, `C.gateway_version`, `C.nominal_voltage`, `C.nominal_frequency`, `C.inverter_fault_code` ([80a457d](https://github.com/dewet22/givenergy-modbus/commit/80a457da7ee3295e6a5d569fd890ea4c88b37b89), [5b43be4](https://github.com/dewet22/givenergy-modbus/commit/5b43be4), @dewet22)
- New enums: `WorkMode`, `Certification`, `InverterType`, `Generation`, `Phase`, `MeterStatus`, `BatteryMaintenance` ([80a457d](https://github.com/dewet22/givenergy-modbus/commit/80a457da7ee3295e6a5d569fd890ea4c88b37b89), [95aba95](https://github.com/dewet22/givenergy-modbus/commit/95aba95), @dewet22)
- `inverter_fault_messages` field on `SinglePhaseInverter` decodes the HR(223/224) bitmask into a list of active fault name strings ([5b43be4](https://github.com/dewet22/givenergy-modbus/commit/5b43be4), @dewet22)
- `min`/`max` physical bounds on `RegisterDefinition` for out-of-range detection across all register LUTs ([5e55be0](https://github.com/dewet22/givenergy-modbus/commit/5e55be0), @dewet22)
- accept mode parameter in set_calibrate_battery_soc ([8139304](https://github.com/dewet22/givenergy-modbus/commit/8139304b373625fcf13e52a90328e0eb50876c1c), @dewet22)
- add slots 3-10 write commands and model-aware SlotMap dispatch ([e7a88d0](https://github.com/dewet22/givenergy-modbus/commit/e7a88d02e01c4d101c145a3d2d49fcedf5c51f3f), @dewet22)
- per-model register block dispatch in load_config() and refresh() ([1568038](https://github.com/dewet22/givenergy-modbus/commit/1568038c7243a49ef410033210690b7445bbf822), @dewet22)
- per-commit and per-push overrides for the changelog bot ([2eb890a](https://github.com/dewet22/givenergy-modbus/commit/2eb890adc8e81dc2df93df3eadee913efc3b13a4), @dewet22)
- support prerelease and finalize bumps in release workflow ([743f0e5](https://github.com/dewet22/givenergy-modbus/commit/743f0e5bba9a54a89cc004093c1bde126499289c), @dewet22)

### 🔄 Changed

- `Inverter` renamed to `SinglePhaseInverter`; `select_inverter()` is now the recommended constructor — it returns the right concrete type based on device model. `Inverter` remains importable as a deprecated alias ([071c755](https://github.com/dewet22/givenergy-modbus/commit/071c755), @dewet22)
- Renamed `slave_address` → `device_address` across PDUs, and the matching capability fields on `PlantCapabilities` (`inverter_slave` → `inverter_address`, `meter_slaves` → `meter_addresses`, `lv_battery_slaves` → `lv_battery_addresses`, `bcu_slaves` → `bcu_stacks`) and `HvStack` (`slave_address` → `device_address`), aligning with Modbus.org's 2020 terminology update. Legacy names remain as deprecation-warning aliases ([#61](https://github.com/dewet22/givenergy-modbus/pull/61), @dewet22)
- `Plant.update()` validates each incoming register bank before committing; banks with an invalid serial number (e.g. all-zero padding from an absent battery slot) are silently discarded rather than written into the cache ([82ba7fc](https://github.com/dewet22/givenergy-modbus/commit/82ba7fc), @dewet22)
- Bounds violations on physical measurements are logged at ERROR level and currently still committed — enforcement (discard-on-violation) follows in a future release once the bounds have been validated in production (see [#57](https://github.com/dewet22/givenergy-modbus/issues/57)) ([5e55be0](https://github.com/dewet22/givenergy-modbus/commit/5e55be0), @dewet22)

### 🐛 Fixed

- `Converter.timeslot` now returns `None` for raw register value `60` — a hardware sentinel for an unset slot that previously caused `ValueError: minute must be in 0..59` ([f93f872](https://github.com/dewet22/givenergy-modbus/commit/f93f872), @dewet22)
- `Client.one_shot_command()` no longer calls `connect()` internally — calling it on an already-connected client was opening a second TCP connection, spawning duplicate consumer/producer tasks, and causing both tasks to race for reads on the same `StreamReader`, permanently breaking the connection ([2b33e61](https://github.com/dewet22/givenergy-modbus/commit/2b33e61), @dewet22)
- use dict.get() in nominal_voltage/nominal_frequency to avoid IndexError on unknown option ([b5446a2](https://github.com/dewet22/givenergy-modbus/commit/b5446a2c9b560fe9cf8a2b727b73fb7209da0329), @dewet22)
- remove implicit connect() from one_shot_command ([87d42bf](https://github.com/dewet22/givenergy-modbus/commit/87d42bfdfc3e08388a3679a2769efafa5bea31c8), @dewet22)
- whitelist battery pause registers 318-320 in WRITE_SAFE_REGISTERS ([9824e3b](https://github.com/dewet22/givenergy-modbus/commit/9824e3b825dfa693eb326b36fc199277a5aafc46), @dewet22)
- add docstrings to deprecated slot wrappers; narrow types in slot tests ([0038349](https://github.com/dewet22/givenergy-modbus/commit/0038349737204615bf5a92b357267e73f4f94c5d), @dewet22)
- split three-phase HR 1060-1124 load into two ≤60-register reads ([31bce62](https://github.com/dewet22/givenergy-modbus/commit/31bce6216505150050a7159bb1bf5729fe6cbb08), @dewet22)
- read/write CHANGELOG.md as UTF-8 explicitly ([e4296d0](https://github.com/dewet22/givenergy-modbus/commit/e4296d01ebaad9cdca4830d7666471e01a310c86), @dewet22)
- tighten loose ends spotted by Codacy + CodeRabbit + Gemini ([f2e4013](https://github.com/dewet22/givenergy-modbus/commit/f2e401398bd12c62f7b1724f9c9e646d50ed161a), @dewet22)

### ⚠️ Deprecated

- `Inverter` — use `SinglePhaseInverter` directly, or `select_inverter()` to get the correct type for a given device
- `commands.enable_charge()` / `disable_charge()` — use `set_enable_charge(bool)` instead
- `commands.enable_discharge()` / `disable_discharge()` — use `set_enable_discharge(bool)` instead
- `slave_address` kwarg/attribute on PDUs and `slave_address` on `HvStack` — use `device_address`. `PlantCapabilities.inverter_slave` / `meter_slaves` / `lv_battery_slaves` / `bcu_slaves` — use `inverter_address` / `meter_addresses` / `lv_battery_addresses` / `bcu_stacks`. All emit `DeprecationWarning` on access

### 🔧 Maintenance

- add AGENTS.md with accurate architecture and dependency info ([d7bc6a2](https://github.com/dewet22/givenergy-modbus/commit/d7bc6a26af689ed66e8d5453105cc3a6c172e642), @dewet22)
- add logo; rationalise badges; fix Python capitalisation in blurb ([6c4ef4d](https://github.com/dewet22/givenergy-modbus/commit/6c4ef4d234213196c4fd95d4eca130fa7c8e319d), @dewet22)
- add coverage for deprecation alias, slot maps, getter branches, and BatteryMaintenance ([f3c3842](https://github.com/dewet22/givenergy-modbus/commit/f3c3842963d928aeba72b135af50328c1aae0c9e), @dewet22)
- add .bandit INI file to exclude tests/ from bandit scan ([f153a30](https://github.com/dewet22/givenergy-modbus/commit/f153a30fa7917827a9364a75bbd3524d3bda0630), @dewet22)
- update usage guide, README, CONTRIBUTING, and add CLAUDE.md ([f4f0ee4](https://github.com/dewet22/givenergy-modbus/commit/f4f0ee469c7089ee605cc0b660f6a44bbf37482d), @dewet22)
- purify Converter class and backfill three-phase/EMS register fields ([851d4a9](https://github.com/dewet22/givenergy-modbus/commit/851d4a9e6d2cd42dc85ae5e66d7095577b30876e), @dewet22)
- add architecture overview with topology and component diagrams ([7a7eca4](https://github.com/dewet22/givenergy-modbus/commit/7a7eca43b05210e937a96d073c277033cad6109e), @dewet22)
- add load_config/refresh dispatch tests; drop email from CLAUDE.md ([da4d218](https://github.com/dewet22/givenergy-modbus/commit/da4d218322232173b491f715f21ff51fbd1e04d8), @dewet22)

## [1.3.0] - 2026-05-13

### 🔧 Maintenance

- notify downstream consumers on release via repository_dispatch (#53) ([2a03623](https://github.com/dewet22/givenergy-modbus/commit/2a036231236f681451eb395ce87fe89ad3377488), @dewet22)

### 🐛 Fixed

- prevent deadlock after inverter maintenance disconnect (#54) ([4469b7a](https://github.com/dewet22/givenergy-modbus/commit/4469b7af7713c9cfffef95e072acf9f3c38f5ca5), @dewet22)

## [1.2.0] - 2026-05-11

### 🔄 Changed

- rewrite with commit attribution and full history backfill ([1fbf3c2](https://github.com/dewet22/givenergy-modbus/commit/1fbf3c2009a4c0b63b0ab9017c6c926c9686cf00), @dewet22)
- Update givenergy_modbus/model/battery.py ([128e3ba](https://github.com/dewet22/givenergy-modbus/commit/128e3ba83ec7be4e5fa3f52462c0a80d37dd6cec), @dewet22)
- fix off-by-one and replace assert in Plant.number_batteries ([75f8425](https://github.com/dewet22/givenergy-modbus/commit/75f842524105936f0e3b7d5d8b64ef137171e465), @dewet22)

### 🐛 Fixed

- stop ValueError on battery decode aborting number_batteries (#49, #51) ([27e97b3](https://github.com/dewet22/givenergy-modbus/commit/27e97b36130f938d0d2c2fa1f921fe034c9be16e), @dewet22)
- downgrade CRITICAL shutdown logs on intentional client.close() (#50) ([d21cf66](https://github.com/dewet22/givenergy-modbus/commit/d21cf665011a1ab954c2db1eb2898a3aa10b105d), @dewet22)
- drop battery_soc_reserve=100 from set_mode_storage (#27) ([a6e5a1f](https://github.com/dewet22/givenergy-modbus/commit/a6e5a1f3f8860e90e01791ac776ee143dcc5e8a8), @dewet22)
- keep parens around multi-exception except for py313 compatibility ([cd40d2f](https://github.com/dewet22/givenergy-modbus/commit/cd40d2f2a4773686f89139de729acf574b0db531), @dewet22)
- append every commit on push to [Unreleased], not just head_commit ([5ea934d](https://github.com/dewet22/givenergy-modbus/commit/5ea934dcc224fdcd101dff627c461cb410a3fbcd), @dewet22)

### 🔧 Maintenance

- align with usb_device_inserted field name retained by Codacy revert ([a471c9a](https://github.com/dewet22/givenergy-modbus/commit/a471c9a49e115aa9902d28cef6899dd30d53fd90), @dewet22)

## [1.1.2] - 2026-05-11

### 🔧 Maintenance

- replace tag-triggered release with workflow_dispatch ([dc78952](https://github.com/dewet22/givenergy-modbus/commit/dc789525805118aa881736ea4564cb61d207d188), @dewet22)
- add Dependabot GitHub Actions version tracking ([e1680f9](https://github.com/dewet22/givenergy-modbus/commit/e1680f9cb597b4cea7d5f9f1526890d0c67ceae6), @dewet22)

## [1.1.1] - 2026-05-11

### 🔧 Maintenance

- downgrade codecov upload failure to warning ([12a3085](https://github.com/dewet22/givenergy-modbus/commit/12a30859f38966d3b9c82d32e3cf9769d8919661), @dewet22)

### 🔄 Changed

- migrate from Poetry to uv for dependency management ([c8c6156](https://github.com/dewet22/givenergy-modbus/commit/c8c615619f869bbc1f615f5fc992554cd7778a49), @dewet22)

### 🐛 Fixed

- handle ConnectionResetError when closing client connection ([b7109f1](https://github.com/dewet22/givenergy-modbus/commit/b7109f1f11d4330ef872108aa191c429de3e144d), @dewet22)

## [1.1.0] - 2026-05-09

### 🔄 Changed

- modernise type annotations and fix bandit/prek hooks ([6d8c50f](https://github.com/dewet22/givenergy-modbus/commit/6d8c50f99779bf744e1473cef4b2094a023aa95b), @dewet22)
- bump inverter model to 1.1.0: new registers, computed battery_capacity_kwh, enum fix ([23b9cb8](https://github.com/dewet22/givenergy-modbus/commit/23b9cb80bd1446ef1d00d2f9f3af59bab7d10ce5), @dewet22)

## [1.0.2] - 2026-05-09

### 🔄 Changed

- remove unnecessary fail-fast: false from release workflow ([2b65001](https://github.com/dewet22/givenergy-modbus/commit/2b6500157737ec58606979d3bb2e1c5b4f47ac15), @dewet22)
- use Python 3.14 as default; fix __version__ when package not installed ([f46a4a4](https://github.com/dewet22/givenergy-modbus/commit/f46a4a41b7cf3dd21fe5e0ec9015f14e297272a2), @dewet22)
- update ruff target-version to py314 ([867b90a](https://github.com/dewet22/givenergy-modbus/commit/867b90a69e7cb2b76ed7824debeb468977fde805), @dewet22)
- update docs for v1.0.0 API ([bd21ab5](https://github.com/dewet22/givenergy-modbus/commit/bd21ab5833962797516b26f237845ef0d531a87e), @dewet22)
- update root-level docs and config ([3935f9d](https://github.com/dewet22/givenergy-modbus/commit/3935f9d2efb12ac3b0557b2e6745943f728ca848), @dewet22)

## [1.0.1] - 2026-05-09

### 🔄 Changed

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

### ✨ Added

- New asyncio `Client` with long-lived connections, producer/consumer task pair, and `Future`-based response tracking — replaces the old synchronous `GivEnergyClient`.
- Passive monitoring mode: listen-only client that observes traffic without sending commands.
- `Plant.update(pdu)` for incremental state updates from incoming PDU responses; `Plant` now dynamically discovers the number of attached batteries.
- Comprehensive holding register coverage: all HR(0–300+) mapped and typed, including `charge_slot_2`, `battery_discharge_mode`, `battery_calibration_stage`, `modbus_address`, `modbus_version`, `system_time`, `enable_60hz_freq_mode`, `enable_drm_rj45_port`, `inverter_reboot`, and ~30 additional fields.
- Virtual aggregates: `p_pv_power`, `e_pv_total`, and related computed fields.
- Custom exception hierarchy for richer, typed error handling.
- Community contributions: inverter register additions from @holdestmade and @dominic.

### 🔄 Changed

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

### 🗑️ Removed

- `pymodbus` runtime dependency — the Modbus protocol is now implemented entirely in-library.
- Old synchronous CLI (spun out to a separate package).

### 🔒 Security

- fix five issues identified in audit ([2e38d5e](https://github.com/dewet22/givenergy-modbus/commit/2e38d5e010a61216faed357a73b088fe4f323137), @dewet22)

## [0.10.1] - 2022-03-03

### 🐛 Fixed

- 🛠 Make `Plant` serializable.

## [0.10.0] - 2022-03-02

### ✨ Added

- 💪 Reintroduced the battery energy totals on the `Battery` model. On some firmware versions that is populated instead
  of the values from the inverter. (#7, via @britkat1980)

### 🔄 Changed

- ⚠️ Breaking change: rejigged the `Plant` model to abstract away `RegisterCache`s and remove some of the toil around
  managing state. `README.md` updated with example implementation.

## [0.9.4] - 2022-02-15

### ✨ Added

- 🛠 Enable CodeQL GitHub workflow for automated code quality scans

### 🐛 Fixed

- 🐛 Allow multiple serial number prefixes to map to the same inverter model name (#6, by @zaheerm)

## [0.9.3] - 2022-02-01

### 🐛 Fixed

- 🧽 Update total energy registers (by @britkat1980)
- 🛠 Re-enable builds back to python v3.7 to support e.g. Raspberry Pi current version
- 🧹 Update python and pre-commit deps, including security fix for loguru

## [0.9.2] - 2022-01-24

### 🐛 Fixed

- 🐛 Scaled registers to use division instead of multiplication – prevents rounding errors.
- 📖 Update README.md to match reality better
- 🧽 Update deps
- 🛠 Try to re-enable GH pages

## [0.9.1] - 2022-01-13

### 🐛 Fixed

- 🐛 The `_time` fault registers don't denote a BCD-encoded timestamp, but seems to be a counter of #cycles the fault
  lasted.
- Sometimes a time slot timestamp is returned as `60` minutes. Guard by taking the modulo-60 instead.

## [0.9.0] - 2022-01-13

### ✨ Added

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

### 🔄 Changed

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

### ✨ Added

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

### 🔄 Changed

- **Potentially breaking:** Once again, pretty wholesale renaming of registers to more official designations, and
  standardising naming somewhat. Part of the motivation for adding more convenience functions is so clients never have
  to deal with register names directly, so this should hopefully make future renaming easier.

## [0.7.0] - 2022-01-05

### ✨ Added

- Another register whitelist and check in the `WriteHoldingRegisterRequest` PDU as another layer of checks to not
  inadvertently write to unsafe registers. Add a test to ensure the allow list stays in sync with the register
  definitions from `model.register_banks.HoldingRegister`.
- A bunch of convenience methods to write data to the inverter without needing any knowledge of registers.
  See `client.GivEnergyClient` which has a number of `set_*` methods.

### 🔄 Changed

- Split out the end-user client functionality from the Modbus client - they were getting too entangled unnecessarily.
  Updated example code in README for reference.
- Renamed `target_soc` to `battery_target_soc` instead.

## [0.6.2] - 2022-01-04

### 🐛 Fixed

- Will this fix `mindsers/changelog-reader-action@v2`?

## [0.6.1] - 2022-01-04

### 🐛 Fixed

- Fix stupid pypi classifier strictness

## [0.6.0] - 2022-01-04

### 🔄 Changed

- **[BREAKING CHANGE]** registers have been widely renamed for consistency and clarity. The joys of a pre-release API.
- Checked all the registers and their values to make sense. Added units for most that are self-evident. The
  `Inverter` object is shaping up nicely as a user-friendly representation of the inverter dataset – TODO is likely
  splitting out a `Battery` representation too, to account for systems with multiple battery units (and those without
  batteries at all!). The same might make sense for the PV aspect as well.

### 🐛 Fixed

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
