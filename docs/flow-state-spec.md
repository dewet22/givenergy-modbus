# Power-flow state — shared classification spec

Status: **cli + hass signed off; ready to implement**. No implementation yet — this
pins the semantics so the eventual `givenergy_modbus.model.flows` primitive, the cli
TUI, and the hass dashboard all classify instantaneous power flow the same way. Both
frontends have confirmed the decisions below; the enum member names settle the agreed
naming. hass will also call `headline(decompose(...))` coordinator-side to back a
translated flow-state enum sensor, so the headline member names are user-facing there.

## Why this exists

Two frontends already classify "what is the system doing right now" from the same
three power readings, and they do it differently:

- **givenergy-cli** (`givenergy_cli/glance.py::flow_status`): one mutually-exclusive
  headline — 8 states, grid-over-battery precedence, stateless, 50 W idle threshold.
- **givenergy-hass** (`givenergy-glance` custom element, `feat/dashboard-glance-mode`):
  five *independent* flow booleans composed into ~13 natural-language sentences, with
  stateful Schmitt-trigger hysteresis (200 W on / 80 W off). It is JavaScript and
  cannot import a Python library.

Because hass is JS, the convergence is a **shared specification with a Python
reference implementation** (used directly by the cli; mirrored in JS by hass), not a
shared import. A single `FlowState` enum would serve only the cli — it cannot express
hass's simultaneous "exporting *and* charging" composites. So the canonical primitive
is the **stateless decomposition** below; each frontend collapses it to its own
headline, and hysteresis stays a frontend concern.

## Inputs and sign conventions

All three readings come straight off the inverter registers (single-phase shown;
three-phase exposes the same concepts):

| Input | Register | Sign convention |
|---|---|---|
| `pv` | IR(18)+IR(20) `p_pv1`+`p_pv2` | ≥ 0 (generation) |
| `grid` | IR(30) `p_grid_out` (external CT) | **+ = export, − = import** |
| `battery` | IR(52) `p_battery` | **+ = discharge, − = charge** |

`load` (IR(42) `p_load_demand`) is not an input to the decomposition — it is derived
from the incoming edges so the displayed home figure equals the sum of the rendered
flows (avoids drift between the independent load sensor and the source sensors). Note
IR(42) already **includes** the EPS branch IR(31) — consumers must not add EPS on top
(see the IR(42) Def docstring and `tests/debug/eps_in_load_demand.py`).

**Units:** the primitive takes **kW** floats (both frontends display kW; hass converts
its W readings at the boundary). The idle threshold is a kW argument (`idle=0.05`).

## Canonical stateless output

`decompose(pv, grid, battery, *, idle=0.05)` returns, for one instant:

**Flow facts** (booleans, each `magnitude > idle`):
`solar_on`, `exporting`, `importing`, `charging`, `discharging`.

**Per-edge magnitudes** (kW ≥ 0), with **solar as the priority source**. This refines
hass's greedy allocation: every edge is capped by `min(remaining source, remaining
sink)` so no edge can exceed the power measured on *either* side, and the slack between
the independently-sensed sources and sinks is surfaced as an explicit residual rather
than absorbed into an edge (these are separate sensors; small drift is expected and
must not be allowed to invent power):

```
batt_charge    = max(0, -battery)      grid_import = max(0, -grid)
batt_discharge = max(0,  battery)      grid_export = max(0,  grid)
solar_gen      = max(0,  pv)

# Allocate sources to the MEASURED sinks (battery charge, grid export), each edge
# capped by min(remaining source, remaining sink). Solar serves first; battery and
# grid backfill. Every term is >= 0 and <= the measured value on both sides.
solar_to_batt = min(solar_gen, batt_charge)
grid_to_batt  = min(grid_import, batt_charge - solar_to_batt)
solar_to_grid = min(solar_gen - solar_to_batt, grid_export)
batt_to_grid  = min(batt_discharge, grid_export - solar_to_grid)

# Home is the DERIVED sink: each source's remainder after the measured sinks.
solar_to_home = solar_gen      - solar_to_batt - solar_to_grid
batt_to_home  = batt_discharge - batt_to_grid
grid_to_home  = grid_import    - grid_to_batt
home          = solar_to_home + batt_to_home + grid_to_home

# Drift: a measured sink no source could cover (sensors disagree). Surfaced, never
# folded into an edge. |residual| above ~0.1 kW (100 W) is the agreed "sensors
# disagree" flag; multi-sensor skew runs tens of watts, so 100 W clears noise.
residual_charge = batt_charge - solar_to_batt - grid_to_batt
residual_export = grid_export - solar_to_grid - batt_to_grid
```

This output is **stateless and unfiltered** — no hysteresis, no idle smoothing beyond
the boolean threshold. Frontends layer their own smoothing on top (e.g. hass folds a
sub-100 W residual into the dominant edge for display tidiness; that's a presentation
choice, not part of the core).

## How each frontend collapses it

**cli — single headline (`FlowState`), grid > battery > solar precedence:**

The source-split states (`EXPORTING_SOLAR` vs `EXPORTING_BATTERY`, `CHARGING_FROM_SOLAR`
vs `CHARGING`) are decided by the dominant *edge*, not merely by whether solar is present
— otherwise a trickle of solar would mislabel a battery-led export. Ties go to solar.
(The member names use "solar" throughout, matching the `solar_to_*` edges, rather than
mixing in "pv".)

| Condition | State |
|---|---|
| `grid_export > idle` and `solar_to_grid >= batt_to_grid` | EXPORTING_SOLAR |
| `grid_export > idle` and `solar_to_grid <  batt_to_grid` | EXPORTING_BATTERY |
| `grid_import > idle` | IMPORTING |
| `batt_discharge > idle` | DISCHARGING |
| `batt_charge > idle` and `solar_to_batt >= grid_to_batt` | CHARGING_FROM_SOLAR |
| `batt_charge > idle` | CHARGING |
| `solar_gen > idle` | SOLAR_COVERING_HOUSE |
| otherwise | IDLE |

**hass — composite sentence** from the boolean combination (e.g. `solar_on &
exporting & charging` → "Solar covering the house and charging the battery, exporting
the surplus"). hass keeps its **Schmitt-trigger hysteresis** (enter at 200 W, leave at
80 W, with prior-state memory) by feeding the smoothed booleans — this is a frontend
concern and deliberately **not** in the stateless core. hass also uses the per-edge
magnitudes directly to drive its animated SVG.

## Planned implementation (sketch — not built yet)

`givenergy_modbus/model/flows.py`, following the model-package idioms (module-level
pure functions like `resolve_model`; `StrEnum`/`IntEnum` per `model/inverter.py`):

```python
from dataclasses import dataclass
from enum import StrEnum

class FlowState(StrEnum):
    EXPORTING_SOLAR = "exporting_solar"
    EXPORTING_BATTERY = "exporting_battery"
    IMPORTING = "importing"
    DISCHARGING = "discharging"
    CHARGING_FROM_SOLAR = "charging_from_solar"
    CHARGING = "charging"
    SOLAR_COVERING_HOUSE = "solar_covering_house"
    IDLE = "idle"

@dataclass(frozen=True)
class FlowDecomposition:
    solar_on: bool
    exporting: bool
    importing: bool
    charging: bool
    discharging: bool
    solar_to_home: float
    solar_to_grid: float
    solar_to_batt: float
    grid_to_home: float
    grid_to_batt: float
    batt_to_home: float
    batt_to_grid: float
    home: float
    residual_charge: float
    residual_export: float

def decompose(pv: float, grid: float, battery: float, *, idle: float = 0.05) -> FlowDecomposition: ...
def headline(d: FlowDecomposition) -> FlowState: ...   # the cli collapse above
```

The cli swaps its local `flow_status` for `headline(decompose(...))` plus its own
display strings; hass mirrors `decompose` + the headline table in JS and keeps its
hysteresis and sentence composition.

## Resolved decisions (cli + hass)

1. **Units — kW.** The core takes kW; hass converts its W readings at the boundary.
2. **Edge set — the seven edges, no EPS edge.** EPS is already inside IR(42) `home`
   (the inclusion finding below), so a distinct EPS edge would re-introduce a
   double-count. A frontend that wants to *show* EPS does so as a sub-figure, not an edge.
3. **Residual — surfaced, tolerance 0.1 kW (100 W).** `residual_charge` /
   `residual_export` are surfaced raw and never attributed to an edge; |residual| above
   0.1 kW is the shared "sensors disagree" flag. Folding a sub-tolerance residual into
   the dominant edge is a frontend display choice (hass does; the core does not).
4. **Hysteresis — frontend-side.** The core is stateless; cli smooths via its snapshot
   history, hass via its 200/80 W Schmitt. No shared hysteresis helper.
5. **Headline state set — the 8 states, source-split by edge.** Matches the cli TUI 1:1;
   hass also consumes `headline(decompose(...))` coordinator-side for a flow-state enum
   sensor, so the member names are user-facing on both sides.

## References

- cli reference: `givenergy_cli/glance.py::flow_status`
- hass reference: `givenergy-glance` element, `feat/dashboard-glance-mode` branch of givenergy-hass
- EPS-in-load finding: IR(42) Def docstring + `tests/debug/eps_in_load_demand.py`
