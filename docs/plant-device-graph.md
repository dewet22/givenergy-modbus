# Graph-shaped Plant abstraction (#106)

Tracking design for the `Plant` model refactor. This is a living document —
phases land independently and the integration keeps working throughout.
See [#106](https://github.com/dewet22/givenergy-modbus/issues/106).

## The problem

`Plant` currently models the world as *one inverter with peripherals hanging
off it*:

- a flat `register_caches: dict[int, RegisterCache]` keyed by Modbus address,
- a single scalar `PlantCapabilities` (one `inverter_address`, global
  `meter_addresses` / `lv_battery_addresses` / `bcu_stacks` lists),
- a 1:1 `Client` ↔ `Plant` relationship.

Real installs break this shape:

- an **EMS plant controller is a peer** of the inverters it manages, not their
  parent — yet `Plant.inverter` (singular) decodes the controller *as* an
  inverter ([hass#52](https://github.com/dewet22/givenergy-hass/issues/52));
- a **Gateway** aggregates partner AIOs and CT meters of its own;
- **batteries belong to their parent inverter**, not directly to the plant;
- some devices have their own communication path (separate dongles), some are
  "blinded" (visible only through a controller's rollup);
- direct-data and rollup views of the same inverter need **reconciliation by
  serial number**.

## Target architecture

A graph: `Plant` → `Device` subclasses → `Transport` (abstract I/O), with a
`serial_index` for cross-device reconciliation.

```
Plant
 ├─ serial_index: {serial → Device}
 ├─ Inverter (direct | blinded | merged)
 │    └─ Battery, Battery, …            (owned by their inverter)
 ├─ Ems            (peer controller, manages N inverters)
 ├─ Gateway        (aggregator, owns partner AIOs + CT meters)
 └─ Meter, HvStack, …
        ↓ each reachable via
      Transport (abstract: ModbusTcpTransport today; HTTP/MQTT/… later)
```

### Design discipline — kept hoist-ready

The `Plant` / `Device` / `Transport` metaphor is a **generic energy-topology
abstraction** — not GivEnergy-specific, not Modbus-specific. The same shape
describes a mixed-vendor install (heat pump + Powerwall + Zappi + GivEnergy
inverter). We keep it hoistable so a future extraction is a code-org refactor,
not a redesign:

1. no concrete GivEnergy or Modbus types leak into the generic shapes
   (`givenergy_modbus/model/devices.py` stays import-clean);
2. generic names (`Inverter`, `DeviceType`) — the GE-specific concretes get a
   `GivEnergy…` prefix only on extraction;
3. `Transport` is abstract; Modbus TCP is one concrete implementation;
4. `RegisterCache` is a Modbus implementation detail, never on the generic
   surface;
5. identity is by **serial**, not wire address.

## Phased rollout

Each phase merges independently and keeps the integration working.

### Phase 1 — typed-device enumeration API ✅ (this increment)

A strictly **additive, non-breaking** read surface: `Plant.devices` returns a
list of `PlantDevice` rows, each tagged with a generic `DeviceType`
discriminator (`INVERTER` / `EMS` / `GATEWAY` / `BATTERY` / `METER` /
`HV_STACK`), a serial (where the device exposes a valid one), the plant model
where meaningful, and the already-decoded typed model.

- Composes the existing accessors (`inverters`, `ems`, `gateway`, `batteries`,
  `meters`, `hv_stacks`) — the EMS-rollup-vs-direct decision (from the #98
  `UnifiedInverter` facade) is honoured once, so an **EMS or Gateway controller
  can never appear as an `INVERTER` row**.
- Gateway plants suppress the spurious direct-inverter row (the singular
  `Plant.inverter` decodes the gateway's own cache as an inverter).
- Every existing `Plant` accessor is untouched.

Consumers (Home Assistant) can now enumerate typed devices to name and scope
entities per device-type instead of assuming a single inverter.

> **Superseded by Phase 2:** Phase 1 emitted batteries and HV stacks as
> top-level `BATTERY` / `HV_STACK` rows. Phase 2 nests them under their owning
> inverter instead (see below). The `DeviceType.BATTERY` / `HV_STACK` members
> remain the vocabulary; `Plant.devices` now surfaces them via
> `inverter_row.device.batteries` / `.hv_stacks`.

### Phase 2 — per-inverter battery & HV-stack ownership ✅ (this increment)

Batteries and HV stacks **belong to an inverter**, not directly to the plant, so
`Plant.devices` now nests them under their owning `INVERTER` row
(`inverter_row.device.batteries` / `.hv_stacks`) instead of emitting flat rows.
The `Inverter` facade's `batteries` / `hv_stacks` (a `[]` stub in Phase 1) are
populated by `Plant`, which decodes the sub-devices and injects them — keeping
`devices.py` import-clean of concrete `Battery` / `HvStack` / `RegisterCache`
types.

- **The model layer stays additive.** `Plant.batteries` / `Plant.hv_stacks` (and
  every other legacy accessor) are unchanged and still return their flat lists.
  Only the `Inverter` facade gained populated sub-devices, and `Plant.devices`
  changed its row shape.
- **Ownership is unambiguous today.** A plant has exactly one *directly-reachable*
  inverter, which owns every battery / stack in the plant cache. Blinded
  (EMS-rollup) inverters honestly carry `[]` — the rollup exposes no per-battery
  data.
- **Orphan guard.** A gateway plant suppresses its (spurious) inverter row, so
  there's no inverter to nest under; any stack the plant decoded there is kept as
  a flat row rather than dropped.

**What's deferred to Phase 3 (the original spec's "reconciliation by serial").**
The spec framed this phase as breaking, behind a capability flag, *with serial
reconciliation*. That reconciliation only bites once a plant has **multiple
direct inverters or a merged direct+rollup view** — which needs the multi-Client
work below. On today's single-Client plants there is nothing to reconcile, so
this increment ships the honest additive slice and defers reconciliation to
Phase 3. The `Plant.devices` row-shape change is breaking versus 2.1.5 but had no
production consumer yet; it lands on the v2.2 line.

### Phase 3 — Serial reconciliation + `Plant.serial_index` ✅ shipped (v2.2)

`Plant.add_direct_source(caches)` stores direct-inverter register caches
separately (avoiding the EMS address-collision at 0x11). `Plant.inverters`
reconciles EMS-rollup summaries with direct-source caches by serial number:
matching serials yield `Inverter.merge()` (``data_source="merged"``); EMS-only
slots stay blinded; orphan direct sources appear as ``data_source="direct"``
entries. `Plant.serial_index` surfaces the reconciled view as
`dict[str, Inverter]`. `Client(host, port, plant=p)` accepts an optional
pre-built plant for single-owner scenarios (e.g. restoring a persisted
PlantCapabilities without re-running `detect()`). Do not share one `Plant`
across two active `Client` instances — both call `plant.update()` into the same
`register_caches`, so devices at the same Modbus address would overwrite each
other. For multi-Client EMS + direct-inverter topologies use separate Plants
and pass the direct caches in via `add_direct_source()`.

**What's still deferred (original "Transport abstraction" intent).**
Extract the Modbus-specific I/O behind a `Transport` interface so a plant can
span multiple connections without `add_direct_source` wiring, and so
non-Modbus transports can slot in later. Reconciles with
[#75](https://github.com/dewet22/givenergy-modbus/issues/75).

### Phase 4 — model-aware write-routing ✅ shipped (v2.2)

Route `set_*` write commands through the typed device so model-specific
register differences (three-phase vs single-phase) are enforced at write time.
Reconciles with [#203](https://github.com/dewet22/givenergy-modbus/issues/203).

## Out of scope (deliberately deferred)

`register_caches` stays flat; `RegisterCache` stays a Modbus detail; no
serial-product (FC 0x16) reads are added for controller rows — EMS and Gateway
controller rows carry `serial_number=None` until a later phase. Serial
reconciliation, multi-transport, and write-routing are Phases 3–4 above.

**Known Phase 1 limitation — meter identity.** `Meter` carries no `device_address`
field; the address is the dict key in `Plant.meters` and is lost when iterating
`.values()`. MR(60-61) serials are absent on all known hardware, so two meter rows
both have `serial_number=None` and are indistinguishable via `Plant.devices`.
Consumers needing to distinguish meters by address should use `Plant.meters`
(keyed by address) directly for now. Stable per-device identity for address-only
devices will be addressed in Phase 2/3 when the transport abstraction makes the
address a typed transport detail rather than a leaked Modbus integer.
