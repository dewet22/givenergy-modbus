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

### Phase 2 — per-inverter battery ownership

Move batteries under their owning inverter (`Inverter.batteries`) with
reconciliation by serial. **Breaking** for consumers that enumerate a flat
`Plant.batteries` at setup time, so it ships behind a capability flag with a
consumer migration. Depends on serial reconciliation maturing.

### Phase 3 — `Transport` abstraction / multi-Client

Extract the Modbus-specific I/O behind a `Transport` interface so a plant can
span multiple connections (free-standing inverters + an EMS on one plant) and
so non-Modbus transports can slot in later. Reconciles with
[#75](https://github.com/dewet22/givenergy-modbus/issues/75).

### Phase 4 — model-aware write-routing

Route `set_*` write commands through the typed device so model-specific
register differences (three-phase vs single-phase) are enforced at write time.
Reconciles with [#203](https://github.com/dewet22/givenergy-modbus/issues/203).

## Out of scope (deliberately deferred)

`register_caches` stays flat; `RegisterCache` stays a Modbus detail; no
serial-product (FC 0x16) reads are added for controller rows — EMS and Gateway
controller rows carry `serial_number=None` until a later phase. Per-inverter
battery ownership, multi-transport, and write-routing are Phases 2–4 above.

**Known Phase 1 limitation — meter identity.** `Meter` carries no `device_address`
field; the address is the dict key in `Plant.meters` and is lost when iterating
`.values()`. MR(60-61) serials are absent on all known hardware, so two meter rows
both have `serial_number=None` and are indistinguishable via `Plant.devices`.
Consumers needing to distinguish meters by address should use `Plant.meters`
(keyed by address) directly for now. Stable per-device identity for address-only
devices will be addressed in Phase 2/3 when the transport abstraction makes the
address a typed transport detail rather than a leaked Modbus integer.
