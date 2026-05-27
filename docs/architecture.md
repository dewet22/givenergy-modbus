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

`RegisterCache` is a plain `dict[HR|IR|MR, int]` with coherence checking (serial-number validity) and bounds validation on each incoming bank. Violations are currently logged at ERROR and the bank committed; a future enforcement step will discard the whole bank on any violation.

## References

### Protocol layering

The TCP surface this library talks to is two layers above the actual battery: `library → TCP → dongle → internal serial → inverter → RS485 → BMS`. The inverter caches BMS state and re-exposes it via the dongle's TCP server. This matters when interpreting failure modes — a "stuck" battery on TCP usually means a stale inverter-side cache, not necessarily a wedged BMS. See `givenergy_modbus/framer.py`'s module docstring for the wire-format details and the cache-freeze / exception-origin caveats.

### External

- **[open-giv/bms-analysis](https://github.com/open-giv/bms-analysis)** — authoritative reference for the RS485 BMS↔inverter dialect, including:
    - The "absent device" response pattern that this library's `Client.detect()` relies on for LV battery probing (zero-filled responses for unpopulated `0x32..0x37` slots, plus the `0xF556 = -273.0 °C` temperature sentinel that our `Battery` bounds incidentally reject).
    - Static analysis of the BMS firmware confirming that the BMS Modbus dispatcher only implements FC=03/04/06; max register count per request is 128; CRC failures are silently dropped without an exception response.
    - Capture tooling (`tools/serial_hexdump_logger.c`, `tools/parse_log.py`) useful for paired RS485+TCP investigations of the sort discussed in [#78](https://github.com/dewet22/givenergy-modbus/issues/78).
- **[Modbus.org spec](https://modbus.org/specs.php)** — the underlying wire protocol; GivEnergy's framing extends it with the `0x59590001` magic header and the Transparent (`0x02`) function-code envelope.
