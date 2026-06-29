# Architecture

## Overview

`givenergy-modbus` is a layered library for communicating with GivEnergy inverters and peripherals over Modbus TCP. It handles framing, PDU encoding/decoding, register caching, and data model construction, exposing a high-level async `Client` and a `Plant` data model to application code.

## Physical topology

A GivEnergy installation exposes two network endpoints:

- **Inverter gateway** (port 8899) — the primary endpoint, using GivEnergy's proprietary transparent framing over TCP. All inverter-adjacent devices share this connection via Modbus device addresses (formerly known as slave addresses; Modbus.org adopted client/server terminology in 2020).
- **GivEVC charger** (port 502, separate IP, future) — a standard Modbus TCP device polled via a second connection.

```mermaid
graph LR
    app1(["givenergy-cli"])
    app2(["givenergy-hass"])
    app3(["GivTCP"])

    lib(["givenergy-modbus
    library"])

    subgraph conn["Network connections"]
        gw["Inverter gateway
        (Modbus TCP, port 8899)"]
        evc_tcp["EV Charger gateway
        (Modbus TCP, port 502)
        (future)"]
    end

    subgraph modbus_devices["Modbus devices (via gateway)"]
        inv["Inverter
        (addr 0x32)"]
        bat["LV Batteries
        (addr 0x32–0x37)"]
        bcu["HV BCU stacks
        (addr 0x70+)"]
        meter["Meters
        (addr 0x01–0x08)"]
        ems["Plant controller (EMS models only)
        (addr 0x11 / 0x32)"]
        gateway["Gateway (Gateway product)
        (addr 0x32)"]
    end

    evc(["EV Charger
    (future)"])

    app1 --> lib
    app2 --> lib
    app3 --> lib

    lib --> gw
    lib -.->|future| evc_tcp
    gw --> inv & bat & bcu & meter & ems & gateway
    evc_tcp -.-> evc
```

All devices except the EVC share a single TCP connection to the gateway. The EVC requires a second connection to a different host.

## Software layers

```mermaid
graph TB
    subgraph app["Application layer"]
        user(["givenergy-hass\ngivenergy-cli\ncustom code"])
    end

    subgraph client["givenergy_modbus.client"]
        detect["detect()\ndiscover topology"]
        loadcfg["load_config()\nread HR banks"]
        refresh["refresh()\nread IR banks"]
        cmds["commands\nwrite operations"]
    end

    subgraph pdu["givenergy_modbus.pdu / .framer"]
        pdus["ReadHoldingRegisters\nReadInputRegisters\nReadMeterProduct\nWriteHoldingRegister"]
        framer["GivEnergy transparent\nframing over TCP"]
    end

    subgraph model["givenergy_modbus.model"]
        plant["Plant\nregister_caches · capabilities"]
        caps["PlantCapabilities\ndevice_type · inverter_address\nlv_battery_addresses · meter_addresses\nbcu_stacks · evc_host (future)"]

        subgraph devices["Device models (lazy accessors)"]
            sp["SinglePhaseInverter"]
            tp["ThreePhaseInverter"]
            battery["Battery (LV)"]
            hvstack["HvStack\nBcu + Bmu"]
            mtr["Meter + MeterProduct"]
            ems["Ems"]
            gw["GatewayV1 / GatewayV2"]
            evc["Evc (future)"]
        end

        subgraph reg["Register infrastructure"]
            cache["RegisterCache\ndict[HR|IR|MR → int]"]
            getter["RegisterGetter\nbounds · coherence · decode"]
            defn["RegisterDefinition\nconverters · min/max bounds"]
        end
    end

    user --> detect & loadcfg & refresh & cmds
    detect & loadcfg & refresh & cmds --> pdus
    pdus --> framer
    framer -->|"TCP"| user

    detect -->|"writes"| caps
    loadcfg & refresh -->|"updates"| cache
    plant --> caps
    plant --> cache
    cache --> getter --> defn
    getter -->|"decoded"| sp & tp & battery & hvstack & mtr & ems & gw & evc
```

## Client lifecycle

```
client.connect()       establish TCP connection(s)
       │
client.detect()        read HR(0)/HR(21) to resolve model; probe peripherals
       │               → writes PlantCapabilities to plant.capabilities
       │
client.load_config()   fetch HR configuration banks (slots, targets, limits)
       │               extra banks dispatched per device type (three-phase,
       │               extended slots, EMS)
       │
       ╔══ polling loop ══════════════════════════════════════╗
       ║  client.refresh()   fast poll: IR measurement banks  ║
       ║                     extra banks per device type      ║
       ╚══════════════════════════════════════════════════════╝
       │
client.load_config()   re-read after any write to confirm the change landed
```

`detect()` is intentionally slow — a correct topology is more important than fast startup. It uses a two-tier timeout: full retries for known devices, short probe retries for speculative addresses (meters, batteries, BCU stacks) where absence is the common case.

### Inside `detect()`: strategise / probe / derive

After resolving the model, `detect()` runs a loop over the peripheral steps (BCU, AIO, HV BMU, meters, LV batteries, LV BCU, EMS). Each step is split into three roles, separated by whether they touch the wire:

![The detect() strategise, probe and derive loop](img/detect-strategise-probe-derive.png)

- **`_strategise(caps, prior, step)`** — pure policy. Given the model and an optional `prior` hint, it returns the `ProbeRange`s to read for that step. Cold (no hint) yields a broad candidate sweep; hinted restricts to the addresses `prior` already knows. No I/O, so it is exhaustively unit-testable.
- **`_probe_ranges(ranges)`** — the shared I/O seam for the `_strategise`-routed probe steps (AIO modules, HV BMUs, meters, LV BCU). It issues each read at its tier (fast `probe_timeout` for speculative probes, full `timeout` for known devices) and, on a probe that does not answer, calls `mark_absent()` and evicts the stale cache entry.
- **`_derive_capabilities(caches, prior, on_reject)`** — pure validation. It reads the now-populated register caches, applies each device's `is_valid()` gate, and builds the authoritative `PlantCapabilities`. Rejections thread back through `on_reject` to `mark_absent()`.

This split is what makes the offline `Plant.from_caches()` path possible (#268): `_derive_capabilities` is the same pure function whether the caches came from a live probe or a saved register dump.

!!! note
    Several reads still touch the wire outside `_probe_ranges`: the initial model read, BCU stack discovery, LV-battery enumeration, and the EMS rollup cross-check (BCU and LV-battery probing carry the cold-start splice-guard re-probe, #233/#289). The loop above shows the shared-seam pattern that the AIO, HV-BMU, meter and LV-BCU steps follow — not every read in `detect()`.

#### Why three functions

Before #345, `detect()` fanned out to a per-device-type helper for each peripheral, and every helper independently tangled all three concerns — pick candidates, probe, then validate-and-mutate `caps`:

![Before and after: per-type helpers transposed into per-concern functions](img/detect-refactor-before-after.png)

The refactor transposes that grid: instead of five helpers each doing all three jobs, there is one function per job. Candidate generation lives once (shared by `_strategise` and `_derive_capabilities`) and validation lives once in `_derive_capabilities`, both spanning every device type; the probe I/O routes through `_probe_ranges` for the AIO, HV-BMU, meter and LV-BCU steps. A change to a candidate range or a validation gate is now a one-site edit rather than a five-site sweep.

### How `refresh()` decomposes

The polling path mirrors `detect()`'s split — pure policy decides *what* to read, a single seam does the I/O:

![The refresh() decomposition: _refresh_banks, _refresh_ranges and _execute_reads](img/refresh-decomposition.png)

- **`_refresh_banks(caps)`** — pure topology. Turns `PlantCapabilities` into the ordered list of IR banks the plant exposes (inverter measurement blocks, per-battery, per-meter, BCU / AIO / HV-BMU pages). No I/O, no policy.
- **`_refresh_ranges(caps, max_age, plant)`** — pure policy. Walks the bank list and applies two skip gates per bank: drop it if `detect()` marked it absent (`block_present(...) is False`, #268), then drop it if `max_age` says it is still fresh (`block_age(...) <= max_age`, #196/#207). Whatever survives becomes a `ReadInputRegistersRequest`.
- **`_execute_reads(...)`** — the I/O seam. Issues the batch and tolerates partial failure (`RefreshPartiallySucceeded` / `RefreshFailed`).

`refresh()` itself is a thin shell around these: check that capabilities exist, map the deprecated `ir0_max_age` onto `max_age`, then `_execute_reads(_refresh_ranges(...))`.

Unlike `detect()`, there is no validate stage. `refresh()` decides only what to *ask* for; whether to *believe* a response is the cache layer's call — the keep-last-good guards (CRC #255, sub-bus splice #256, bank holds) validate each frame as it commits. The skip-if-fresh gate also makes `refresh()` cooperative with the dongle fan-out: GivEnergy dongles echo responses to every connected client, so a bank another poller just refreshed can be left alone (#196).

## Plant data model

`Plant` is passive — it stores data, drives no I/O. Its two responsibilities are:

1. **`register_caches`** — `dict[int, RegisterCache]` keyed by Modbus device address, populated by `Client` as responses arrive.
2. **`capabilities`** — a `PlantCapabilities` dataclass describing the topology discovered by `Client.detect()`.

All plant properties are lazy decoders: they read from `register_caches` and construct the appropriate concrete model class, dispatching on `capabilities.device_type` where needed.

| Accessor | Returns | Condition |
|---|---|---|
| `plant.inverter` | `SinglePhaseInverter \| ThreePhaseInverter` | always |
| `plant.batteries` | `list[Battery]` | LV systems only |
| `plant.hv_stacks` | `list[HvStack]` | HV systems only |
| `plant.meters` | `dict[int, Meter]` | when meters detected |
| `plant.ems` | `Ems \| None` | `Model.EMS` / `EMS_COMMERCIAL` only |
| `plant.gateway` | `GatewayV1 \| GatewayV2 \| None` | `Model.GATEWAY` only |
| `plant.evc` | `Evc \| None` | future |

## Register infrastructure

Each device model is backed by a `RegisterGetter` subclass that holds a `REGISTER_LUT` — a dict mapping field names to `RegisterDefinition` instances. Each definition specifies:

- **Converter(s)** — how to decode raw `uint16` register values (e.g. `C.deci` divides by 10, `C.timeslot` reconstructs a `TimeSlot`, `C.bitfield` extracts bit ranges).
- **Post-converter** — optional second-stage transform or enum lookup.
- **Register address(es)** — one or more `HR`/`IR`/`MR` addresses; multi-register fields (e.g. `uint32`, strings) list all constituent registers.
- **Bounds** — optional `min`/`max` in real-world units (post-conversion), used to detect physically impossible values and log violations before committing a bank.

`RegisterCache` is a plain `defaultdict[HR|IR|MR, int]` — just storage. Coherence (serial-number validity) and bounds validation live on the `RegisterGetter`, applied by `Plant._commit_bank` as each bank arrives. Several classes of bad bank are already **rejected** outright: an invalid serial, a CRC failure, an all-zero dropout of a previously-populated bank, and a battery sub-bus splice. Bounds violations are the remaining exception — they're logged (at DEBUG) and the bank is still committed, pending the enforcement step tracked by a `TODO` in `_commit_bank`.

## References

### Protocol layering

The TCP surface this library talks to is two layers above the actual battery: `library → TCP → dongle → internal serial → inverter → RS485 → BMS`. The inverter caches BMS state and re-exposes it via the dongle's TCP server. This matters when interpreting failure modes — a "stuck" battery on TCP usually means a stale inverter-side cache, not necessarily a wedged BMS. See `givenergy_modbus/framer.py`'s module docstring for the wire-format details and the cache-freeze / exception-origin caveats.

### External

- **[open-giv/bms-analysis](https://github.com/open-giv/bms-analysis)** — authoritative reference for the RS485 BMS↔inverter dialect, including:
    - The "absent device" response pattern that this library's `Client.detect()` relies on for LV battery probing (zero-filled responses for unpopulated `0x32..0x37` slots, plus the `0xF556 = -273.0 °C` temperature sentinel that our `Battery` bounds incidentally reject).
    - Static analysis of the BMS firmware confirming that the BMS Modbus dispatcher only implements FC=03/04/06; max register count per request is 128; CRC failures are silently dropped without an exception response.
    - Capture tooling (`tools/serial_hexdump_logger.c`, `tools/parse_log.py`) useful for paired RS485+TCP investigations of the sort discussed in [#78](https://github.com/dewet22/givenergy-modbus/issues/78).
- **[Modbus.org spec](https://modbus.org/specs.php)** — the underlying wire protocol; GivEnergy's framing extends it with the `0x59590001` magic header and the Transparent (`0x02`) function-code envelope.
