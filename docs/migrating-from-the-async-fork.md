# Migrating from the `givenergy_modbus_async` fork

This guide is for projects that consume the community `givenergy_modbus_async`
fork — typically vendored, as GivTCP does — and want to move to this library
(`givenergy-modbus` 2.2+ on PyPI). The two codebases share ancestry, so the
module layout maps almost one-to-one and most of the port is mechanical
renames. There is exactly one structural change: the polling lifecycle.

The deltas below were derived by comparing the fork as vendored on GivTCP's
`modbusv2` branch against 2.2.0. Other descendants of the fork may differ
slightly.

## Installing

The library is published to PyPI — no vendoring or submodule needed:

```bash
pip install givenergy-modbus
```

## Import map

The top-level package renames from `givenergy_modbus_async` to
`givenergy_modbus`; nearly everything keeps its path under that:

| Fork | 2.2+ |
|---|---|
| `from givenergy_modbus_async.client.client import Client` | `from givenergy_modbus.client.client import Client` |
| `from givenergy_modbus_async.client.client import commands` | `from givenergy_modbus.client import commands` |
| `from givenergy_modbus_async.model.register import Model` | `from givenergy_modbus.model.inverter import Model` |
| `from givenergy_modbus_async.model.register import Enable` | removed — these fields are plain `bool`s now (see below) |
| `from givenergy_modbus_async.model.register import HR, IR` | `from givenergy_modbus.model.register import HR, IR` |
| `from givenergy_modbus_async.model import TimeSlot` | `from givenergy_modbus.model import TimeSlot` |
| `from givenergy_modbus_async.model.plant import Plant` | `from givenergy_modbus.model.plant import Plant` |
| `from givenergy_modbus_async.exceptions import CommunicationError` | `from givenergy_modbus.exceptions import CommunicationError` |
| `from givenergy_modbus_async.pdu import TransparentRequest, …` | `from givenergy_modbus.pdu import TransparentRequest, …` |

Throughout the API, the fork's `slave_address` terminology is
`device_address` here (parameter names, PDU attributes, repr output).

## The polling lifecycle (the one structural change)

The fork's `detect_plant()` / `refresh_plant()` / `commands.refresh_plant_data()`
orchestration is replaced by three primitives:

```python
# once, after connecting — discovers device type, address, meters, batteries:
caps = await client.detect()

# occasionally — non-volatile configuration (slots, targets, limits):
await client.load_config()

# hot loop — volatile measurements:
await client.refresh()
```

| Fork | 2.2+ |
|---|---|
| `await client.detect_plant(...)` | `await client.detect()` → returns `PlantCapabilities` |
| `await client.refresh_plant(full_refresh=True, ...)` | `await client.load_config()` then `await client.refresh()` |
| `await client.refresh_plant(full_refresh=False, ...)` | `await client.refresh()` |
| `commands.refresh_plant_data(...)` | removed — raises `PlantNotDetected` with migration pointers |

Notes:

- `detect()` has no `additional=` or `lite=` parameters. Additional register
  blocks are probed automatically per model. A consumer-controlled reduced
  refresh ("lite mode") is being designed in
  [#242](https://github.com/dewet22/givenergy-modbus/issues/242) — input
  welcome if you rely on the fork's `lite=True`.
- `detect(prior=...)` accepts a previously persisted `PlantCapabilities`
  (e.g. from `caps.to_dict()` / `PlantCapabilities.from_dict()`), so restarts
  can skip the full probe.
- `refresh(ir0_max_age=...)` opts in to skipping the IR(0,60) read when a
  fresh copy was already received (dongles fan responses out to all connected
  clients), reducing bus load — much of what lite mode was for.
- `refresh()`/`load_config()` raise `RefreshPartiallySucceeded` /
  `RefreshFailed` rather than returning silently on partial reads; the
  partial-failure policy belongs to the consumer.
- A deprecated `refresh_plant()` shim exists for the transition but will be
  removed in 3.0.

## Plant attributes

Topology facts discovered at detect time live on `plant.capabilities` rather
than directly on `Plant`:

| Fork | 2.2+ |
|---|---|
| `plant.slave_address` | `plant.capabilities.inverter_address` |
| `plant.device_type` | `plant.capabilities.device_type` |
| `plant.isHV` | `plant.capabilities.is_hv` |
| `plant.meter_list` | `plant.capabilities.meter_addresses` |
| `plant.number_batteries` | unchanged on LV plants (also `plant.capabilities.lv_battery_addresses`). **HV plants: semantics changed** — the fork summed BCU module counts here, but this property now counts LV batteries only, so it is 0 on HV. For the fork's total-module count use `sum(n for _, n in plant.capabilities.bcu_stacks)`, or work with `plant.hv_stacks` directly |
| `plant.HVStack` | `plant.hv_stacks` |
| `plant.inverter_serial_number` | `plant.inverter_serial` |
| `plant.additional_input_registers` / `..._holding_registers` | gone — handled internally by capability-aware polling |
| `plant.inverter`, `plant.gateway`, `plant.ems`, `plant.batteries`, `plant.meters`, `plant.register_caches` | unchanged |

`plant.capabilities` also exposes convenience predicates the fork lacked
(`is_three_phase`, `is_ac_coupled`, `is_gateway`, `is_ems`,
`has_extended_slots`, …), which replace most `device_type`-string sniffing.

## Commands

The fork threads an `inv_type: str` parameter through many `set_*` helpers
and branches on substrings like `"3ph"`. Here the model-specific behaviour
is explicit instead:

- 3-phase variants are separate helpers: `set_charge_target_3ph()`,
  `set_battery_soc_reserve_3ph()`, `disable_charge_target_3ph()`, …
- Slot commands take a `SlotMap` (`SINGLE_PHASE_SLOTS`, `EXTENDED_SLOTS`,
  `THREE_PHASE_SLOTS`) instead of an `inv_type` string — pass
  `inverter.slot_map` rather than choosing one by hand:

```python
from givenergy_modbus.client import commands

reqs = commands.set_charge_slot(1, TimeSlot(start, end), inverter.slot_map)
await client.execute(reqs, timeout=2.0, retries=3)
```

| Fork | 2.2+ |
|---|---|
| `set_enable_charge(v, inv_type)` | `set_enable_charge(v)` (3-phase: also `set_ac_charge()` / `set_force_charge()` as appropriate) |
| `set_enable_discharge(v, inv_type)` | `set_enable_discharge(v)` |
| `set_enable_rtc(v, inv_type)` | `set_enable_rtc(v)` |
| `set_battery_charge_limit_ac(v, inv_type)` | `set_battery_charge_limit_ac(v)` |
| `set_battery_discharge_limit_ac(v, inv_type)` | `set_battery_discharge_limit_ac(v)` |
| `set_battery_soc_reserve(v, inv_type)` | `set_battery_soc_reserve(v)` / `set_battery_soc_reserve_3ph(v)` |
| `_set_charge_slot(discharge, idx, slot, inv_type)` | `set_charge_slot(idx, slot, slot_map)` / `set_discharge_slot(idx, slot, slot_map)` |
| `set_charge_target(v, inv_type)` | `set_charge_target(v)` / `set_charge_target_3ph(v)` |
| `set_charge_target_only(v, inv_type)` | no equivalent yet — [#243](https://github.com/dewet22/givenergy-modbus/issues/243) |
| `set_soc_target(discharge, idx, v, inv_type)` | EMS models: `set_ems_charge_target_soc(idx, v)` etc.; non-EMS per-slot targets: [#243](https://github.com/dewet22/givenergy-modbus/issues/243) |

EMS, export and smart-load slots all have first-class helpers
(`set_ems_charge_slot()`, `set_export_slot()`, `set_smart_load_slot()`, …) —
see the full table in [Usage](usage.md).

## Model attributes

### `Enable` enum removed

The fork modelled several flags as an `Enable` enum (`ENABLE` / `DISABLE` /
`UNKNOWN`); here they are plain `bool`s. Comparisons like
`inverter.enable_charge == Enable.ENABLE` become just
`inverter.enable_charge`. An attribute whose backing registers haven't been
read yet returns `None`, so `== Enable.UNKNOWN` checks become `is None`.

### Renamed inverter attributes

Same registers, clearer names (register numbers shown as the join key):

| Fork | 2.2+ | Registers |
|---|---|---|
| `battery_percent` | `battery_soc` | IR(59) |
| `e_inverter_in_day` | `e_ac_charge_today` | IR(35) |
| `e_inverter_out_day` | `e_pv_generation_today` (deprecated alias kept for one release) | IR(44) |
| `e_inverter_out_total` | `e_pv_generation_total` | IR(45,46) |
| `e_battery_throughput_total` | `e_battery_throughput` | IR(6,7) |
| `e_battery_charge_today` | `e_battery_charge_today_alt1` | IR(36) |
| `e_battery_discharge_today` | `e_battery_discharge_today_alt1` | IR(37) |
| `e_battery_charge_today_2` | `e_battery_charge_today_alt2` | IR(183) |
| `e_battery_discharge_today_2` | `e_battery_discharge_today_alt2` | IR(182) |
| `e_battery_charge_total_2` | `e_battery_charge_total_alt1` | IR(181) |
| `e_battery_discharge_total_2` | `e_battery_discharge_total_alt1` | IR(180) — the fork reads HR(180), which looks like a typo |
| `e_battery_charge_today3` | `e_battery_charge_today_alt3` | HR(4114) |
| `e_battery_discharge_today3` | `e_battery_discharge_today_alt3` | HR(4113) |
| `e_battery_charge_total3` | `e_battery_charge_total_alt2` | HR(4111,4112) |
| `e_battery_discharge_total3` | `e_battery_discharge_total_alt2` | HR(4109,4110) |
| `eco_mode` | `battery_power_mode` | HR(27) |
| `soc_force_adjust` | `battery_calibration_stage` | HR(29) |
| `rtc_enable` | `enable_rtc` | HR(166) |
| `enable_standard_self_consumption_logic` | `enable_inverter_parallel_mode` | HR(199) |
| `inverter_countdown` | `countdown` | IR(38) |
| `p_inverter_out` | `p_grid_out_ph1` | IR(24) — inverter AC terminal, distinct from the grid clamp at IR(30) |
| `p_eps_backup` | `p_backup` | IR(31) |
| `v_eps_backup` | `v_ac1_output` | IR(53) |
| `f_eps_backup` | `f_ac1_output` | IR(54) |
| `temp_charger` | `t_charger` | IR(55) |
| `temp_battery` | `t_battery` | IR(56) |
| `temp_inverter_heatsink` | `t_inverter_heatsink` | IR(41) |
| `work_time_total` | `work_time_total_hours` | IR(47,48) |

Computed values like `battery_max_power` and `inverter_max_power` are
properties on the inverter model rather than register definitions, but keep
their names. Battery, meter and gateway attribute surfaces are unchanged
(the gateway additionally gained the firmware-gated `GatewayV1`/`GatewayV2`
split and the parallel-AIO registers that GivTCP patched into its fork).

### Time slots

`charge_slot_1` … `charge_slot_10`, `discharge_slot_*` and
`battery_pause_slot_1` are `TimeSlot`-valued attributes exactly as in the
fork (`inverter.charge_slot_1.start`, `.end`).

## Where to ask

If a port surfaces something this guide misses — an attribute, a command, or
behaviour that changed — please open an issue. Two are already tracked from
GivTCP's port: reduced "lite" refresh
([#242](https://github.com/dewet22/givenergy-modbus/issues/242)) and the two
missing command helpers
([#243](https://github.com/dewet22/givenergy-modbus/issues/243)).
