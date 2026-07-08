"""Declarative capability manifest — model(+firmware) → register semantics (#293, Slice A).

One place answering "what does this register/field mean on this model". Grown in
slices: A (this file's initial content) covers register SEMANTICS — value-source
routing and per-model field identity. Slice B added the capability fact tables
(`CAPABILITIES`, `has_extended_slots`); Slice C1 added the polling-range tables
(`LOAD_CONFIG_RANGES`, `REFRESH_IR_RANGES`, `gated_ranges`); Slice D added the
write surface (`WRITE_SAFE_*`, `write_safe_registers`); detect-time polling
remains in client.py/plant.py's already-shared helpers (C2 was investigated and
found already unified by #268).

Keys are the RESOLVED specific ``Model`` (from ``resolve_model``), never the coarse
family. Every accessor takes ``arm_fw`` so a firmware column exists in the contract
from day one; no Slice A row uses it (future users: slot_map's ``HYBRID_GEN3 and
arm_fw > 302`` extended-slot wrinkle, the Gateway V1/V2 layout variant — Slice B+).
"""

from dataclasses import dataclass

from givenergy_modbus.model.inverter import Model

# Per-(specific-model, metric) authoritative battery-energy source (#184; relocated
# verbatim from inverter._BATTERY_ENERGY_SOURCE in Slice A). Declared only where a
# wire capture positively confirms it; an absent model or metric routes to None
# (honest "no evidence yet" + a forcing function for which captures to chase).
# "today"/"total" each map to an altN whose register name is built as
# e_battery_{charge,discharge}_{metric}_{altN} (see SinglePhaseInverter._battery_energy).
#
#   alt1 = IR(36/37) daily, IR(180/181) total   alt2 = IR(182/183) daily, HR total (dead)
#   alt3 = HR(4113/4114) daily (dead, never polled — see #48)
#
# Evidence (tests/fixtures/captures/): GEN1 populates the alt2 daily registers as
# authoritative and IR alt1 totals; AC/AIO populate alt1 daily, totals unknown → None.
VALUE_SOURCES: dict[str, dict[Model, str]] = {
    "battery_energy_today": {
        Model.HYBRID_GEN1: "alt2",
        Model.AC: "alt1",
        Model.ALL_IN_ONE: "alt1",
    },
    "battery_energy_total": {
        Model.HYBRID_GEN1: "alt1",
    },
}


def battery_energy_source(model: Model, metric: str, arm_fw: int | None = None) -> str | None:
    """Return the authoritative altN source tag for a battery-energy metric, or None.

    ``arm_fw`` is accepted for forward-compatibility with firmware-gated rows (none
    exist in Slice A).
    """
    return VALUE_SOURCES.get(f"battery_energy_{metric}", {}).get(model)


# IR(44)/IR(45-46) identity overrides (#293): on these models the registers carry the
# inverter's battery-discharge AC OUTPUT, not PV generation — delta-evidenced against
# HV-stack counters (AberDino's 2×AIO, 2026-07-02: IR44 = 0.90× stack discharge,
# accumulates pre-dawn, flat through an 11.5 kWh PV midday) and the ems_2_inv_3_bat_a
# fixture's Model.AC units (IR44 == battery discharge). Unlisted models keep the
# status quo (e_pv_generation_* live — the #174 hybrid verdict); adding a row here is
# the entire upgrade path when new evidence lands. AIO_COMMERCIAL/ALL_IN_ONE_HYBRID
# are ThreePhase-decoded and never reach the SinglePhaseInverter validator.
FIELD_IDENTITY: dict[str, frozenset[Model]] = {
    "ir44_inverter_out": frozenset({Model.AC, Model.ALL_IN_ONE}),
}


def ir44_is_inverter_output(model: Model, arm_fw: int | None = None) -> bool:
    """True when IR44/IR45-46 carry inverter output (not PV) on this model (#293)."""
    return model in FIELD_IDENTITY["ir44_inverter_out"]


# Consumption-family evidence gate (#293): a candidate corrected-AIO consumption
# formula — pv_day + grid_import − grid_export + battery_discharge − battery_charge —
# was checked against the AberDino 2×AIO site (2026-06-29/30 delta analysis). On
# 2026-06-30 it yields 33.7 kWh, far outside the only same-site load reference (the
# Gateway rollup's e_load_today, 8.1-18.7 kWh/day) — but that reference is from OTHER
# days, so there is no same-day pair to validate the formula's tolerance against.
# Gate: FAIL. inverter.py's consumption-family deriveds (e_consumption_today,
# e_self_consumption_today/_total, e_pv_direct_today) therefore stay None on AC/AIO —
# not via a dedicated guard, but because the IR44 identity routing above already
# makes e_pv_generation_today/_total None there, and each derived's own
# None-propagation does the rest. No FIELD_IDENTITY/VALUE_SOURCES row exists for the
# repair itself because there is nothing to route yet: the gate failed, so there is no
# formula to enable. Missing evidence to close this: a same-day Gateway e_load_today +
# AIO grid/battery/PV counters snapshot — a targeted ask goes to the reporter via hass
# post-merge.
#
# Adjacent evidence, NOT sufficient to flip the gate: tests/fixtures/captures/
# gateway_2aio_a (same AberDino site, 2026-07-03) carries the Gateway's own rollup
# (IR1640-1798) — e_pv_today/e_grid_import_today/e_grid_export_today/e_aio_charge_
# today/e_aio_discharge_today alongside the Gateway's own independently-metered
# e_load_today, all from the same register poll. The candidate formula computed from
# that rollup closes within ~0.1 kWh of e_load_today in BOTH committed captures
# (daylight: 7.8 vs 7.7; night: 18.6 vs 18.7) — the formula's physics look sound at
# this site. But it validates the Gateway's own CT-metered aggregates, not the
# standalone AIO's local IR44-based e_pv_generation_today (independently confirmed
# contaminated by #293) that SinglePhaseInverter.e_consumption_today would consume for
# a directly-polled, non-gateway-fronted AIO — this capture has no per-AIO register
# bank to cross-check against. Whether that distinction matters (and whether a
# gateway-fronted plant even needs the repair, since GatewayV1 already exposes
# e_load_today natively) is a maintainer call, not resolved here.

# Per-model capability facts, one frozenset per named fact. Relocated from six
# independently-defined module constants (#293 Slice B): plant.py's _HV_MODELS,
# _THREE_PHASE_MODELS, _AC_CONFIG_BLOCK_MODELS, _SMART_LOAD_CAPABLE_MODELS,
# _HV_CABINET_MODELS, _PEAK_SHAVING_MODELS, and inverter.py's AC_COUPLED_MODELS.
# _THREE_PHASE_MODELS was independently duplicated in inverter_threephase.py under
# the public name THREE_PHASE_MODELS — same membership, two copies, nothing stopped
# them drifting apart. Both public names (AC_COUPLED_MODELS, THREE_PHASE_MODELS) are
# kept as deprecated __getattr__ shims in their original modules.
CAPABILITIES: dict[str, frozenset[Model]] = {
    # Models whose battery architecture is HV (BCU/BMU stacks rather than LV packs).
    "is_hv": frozenset(
        {
            Model.HYBRID_3PH,
            Model.AC_3PH,
            Model.ALL_IN_ONE,
            Model.HYBRID_HV_GEN3,
            Model.ALL_IN_ONE_HYBRID,
        }
    ),
    # Models with registers in the 1000-range (HR 1000-1124, IR 1000-1413), i.e.
    # genuinely three-phase units that expose the per-phase bank. The residential
    # ALL_IN_ONE (DTC family "8") is HV but SINGLE-phase — it error-responds to
    # 1000-range reads and decodes via the single-phase IR(0)/IR(180) banks instead.
    # Verified against real AIO hardware and the GE spec sheet (3.6 kW/16 A). See #105.
    "is_three_phase": frozenset(
        {
            Model.HYBRID_3PH,
            Model.AC_3PH,
            Model.AIO_COMMERCIAL,
            Model.ALL_IN_ONE_HYBRID,
            Model.HYBRID_HV_GEN3,
        }
    ),
    # AC-coupled inverters — no integrated DC battery.
    "is_ac_coupled": frozenset({Model.AC, Model.AC_3PH}),
    # Models that expose the HR(300-359) AC-output config block: export_priority
    # (HR311), battery_*_limit_ac (HR313/314), enable_eps (HR317), pause mode/slot
    # (HR318-320). Present on AC-coupled inverters AND the All-in-One. DC-coupled/
    # hybrid inverters lack the block and time out when polled for it (#162).
    "has_ac_config_block": frozenset({Model.AC, Model.AC_3PH, Model.ALL_IN_ONE}),
    # Models with a *readable* Smart Load slot block at HR(540-599). Deliberately
    # empty — no model has been confirmed to return data on real hardware; HYBRID_GEN1
    # is confirmed to time out on the read (#179). Gate off until a capture confirms.
    "has_smart_load_block": frozenset(),
    # Models with a readable HV cabinet topology block at HR(499-510). Deliberately
    # empty — no model confirmed on real hardware yet (#265).
    "has_hv_cabinet_block": frozenset(),
    # Models with a readable peak-shaving block at HR(20000-20051). Deliberately
    # empty — no model confirmed on real hardware yet.
    "has_peak_shaving_block": frozenset(),
    # EMS models — energy management systems.
    "is_ems": frozenset({Model.EMS, Model.EMS_COMMERCIAL}),
    # Gateway models.
    "is_gateway": frozenset({Model.GATEWAY}),
}


def has_capability(name: str, model: Model | None, arm_fw: int | None = None) -> bool:
    """Return True if `model` has the named capability fact.

    `model` accepts `None` because callers pass `self.model`, which is `None` when
    the device type code hasn't been read yet — `None in CAPABILITIES[name]` is a
    safe, honest `False` rather than forcing every call site to guard first.
    `name` must be a key in `CAPABILITIES` — an unknown name raises `KeyError` rather
    than silently returning False, since every call site is our own static-string
    code and a typo should fail loudly. `arm_fw` is accepted for signature consistency
    with every other manifest accessor; none of these facts are firmware-conditional.
    """
    return model in CAPABILITIES[name]


# Models using the extended 10-slot map (HR 240-299 for slots 3-10). Relocated from
# plant.py's _EXTENDED_SLOT_MODELS (#293 Slice B) — that copy listed HYBRID_GEN3
# unconditionally, which disagreed with the register-layout decision actually made by
# SinglePhaseInverter.slot_map (inverter.py), which only treats HYBRID_GEN3 as
# extended above firmware 302. slot_map.py's own EXTENDED_SLOTS comment already
# stated the correct rule; this fixes plant.py's copy to match it. ALL_IN_ONE_HYBRID
# is three-phase-decoded and always uses THREE_PHASE_SLOTS (never the literal
# EXTENDED_SLOTS object) — but THREE_PHASE_SLOTS genuinely has 10 slot pairs too, so
# it belongs in this CAPABILITY set regardless of which SlotMap object serves it.
_EXTENDED_SLOT_MODELS: frozenset[Model] = frozenset(
    {Model.HYBRID_GEN4, Model.ALL_IN_ONE, Model.ALL_IN_ONE_HYBRID, Model.HYBRID_HV_GEN3}
)
_EXTENDED_SLOT_FIRMWARE_GATE: dict[Model, int] = {Model.HYBRID_GEN3: 302}


def has_extended_slots(model: Model, arm_fw: int | None = None) -> bool:
    """True if `model` (at this firmware) uses the extended 10-slot map (HR 240-299)."""
    if model in _EXTENDED_SLOT_MODELS:
        return True
    threshold = _EXTENDED_SLOT_FIRMWARE_GATE.get(model)
    return threshold is not None and arm_fw is not None and arm_fw > threshold


@dataclass(frozen=True)
class RegisterRange:
    """A register range to poll: type, base address, and count (#293 Slice C1)."""

    reg_type: str  # "HR" | "IR"
    base_register: int
    register_count: int


# HR(1000-1124) — three-phase config block. Kept as a standalone constant (not a
# LOAD_CONFIG_RANGES entry) because load_config()'s original code checks
# is_three_phase BEFORE has_extended_slots BEFORE the five tail facts below, and
# ALL_IN_ONE_HYBRID/HYBRID_HV_GEN3 can have both is_three_phase and
# has_extended_slots true simultaneously — the relative order matters and must
# stay exactly as it was (#293 Slice C1).
LOAD_CONFIG_THREE_PHASE_RANGES: list[RegisterRange] = [
    RegisterRange("HR", 1000, 60),
    RegisterRange("HR", 1060, 60),
    RegisterRange("HR", 1120, 5),
]

# The five load_config() facts with no interleaving among themselves or with
# is_three_phase/has_extended_slots in the original code — safe to drive off one
# generic table+loop in this exact insertion order (#293 Slice C1).
LOAD_CONFIG_RANGES: dict[str, list[RegisterRange]] = {
    # HR(540-599) — Smart Load scheduling slots 1–10 (HR554-573). Gated because the
    # block was added from the app's Direct Control catalogue (writable surface only
    # — never confirmed to answer a live read) and HYBRID_GEN1 times out on it (#179).
    # The gate set is currently empty, so this is off for every model pending
    # hardware confirmation. Unmodelled registers in 540-553 and 574-599 are
    # silently ignored by Plant.update(). (#48, #179)
    "has_smart_load_block": [RegisterRange("HR", 540, 60)],
    # HR(499-510) — HV cabinet topology (12 registers: counts, ratings). Gated
    # because the block is from the GivEnergy app v4.0.7 and no model has been
    # confirmed to answer a live read. The gate set is empty until a capture
    # confirms the block responds. (#265)
    "has_hv_cabinet_block": [RegisterRange("HR", 499, 12)],
    # HR(20000-20051) — peak-shaving / valley-filling (sparse: 20000-20003,
    # 20020-20021, 20050-20051). Gated because the block is from the GivEnergy app
    # v4.0.7 and no model has been confirmed to answer a live read. The 52-register
    # window covers all defined offsets; undefined registers in the middle are
    # silently ignored by Plant.update().
    "has_peak_shaving_block": [RegisterRange("HR", 20000, 52)],
    # HR(300-359) — AC-output config: export_priority (HR311), battery_*_limit_ac
    # (HR313/314), enable_eps (HR317), pause mode/slot (HR318-320). Present on
    # AC-coupled inverters AND the All-in-One; DC-coupled/hybrid models time out on
    # this block (#162). Confirmed present on Model.AC (hass#52 portal writes) and
    # the AIO (live poll populated these fields, #105).
    "has_ac_config_block": [RegisterRange("HR", 300, 60)],
    "is_ems": [RegisterRange("HR", 2040, 36)],
}

# _refresh_banks()'s three capability-gated IR ranges — no interleaving among
# themselves in the original code, safe to drive off one generic table+loop
# (#293 Slice C1).
REFRESH_IR_RANGES: dict[str, list[RegisterRange]] = {
    "is_three_phase": [RegisterRange("IR", b, min(60, 1414 - b)) for b in range(1000, 1414, 60)],
    "is_ems": [RegisterRange("IR", 2040, 55)],
    "is_gateway": [RegisterRange("IR", b, min(60, 1860 - b)) for b in range(1600, 1860, 60)],
}


def gated_ranges(
    table: dict[str, list[RegisterRange]], model: Model | None, arm_fw: int | None = None
) -> list[RegisterRange]:
    """Every RegisterRange in `table` whose capability gate is true for `model`."""
    return [r for name, entries in table.items() if has_capability(name, model, arm_fw) for r in entries]


# ---------------------------------------------------------------------------
# Write surface (#293 Slice D): which registers each model accepts at the normal
# (non-installer) write tier. Relocated from client/commands.py's mixin ClassVars
# (_InverterCommands/_ThreePhaseCommands/_EmsCommands.WRITE_SAFE_REGISTERS) and the
# module-level _AC_CONFIG_WRITE_SAFE_REGISTERS. These are Gate 1 of the two-gate
# write-safety model — the model/capability-aware gate; Gate 2 (the universal
# pdu.write_registers supersets) and the confirm=True destructive gate are
# deliberately NOT here (danger classifications true on every model are not
# per-model capability facts). Register names in comments mirror
# client.commands.RegisterMap (not imported — commands.py sits inside the
# manifest→inverter→commands import cycle, so names live in comments).

# Universally-applicable single-phase subset — registers every single-phase inverter
# accepts. Excludes 311/313/314/317 (HR300-359 AC-config block, absent on DC hybrids —
# gated via WRITE_SAFE_AC_CONFIG below, #295/#296/#297), 318-320 (pause mode,
# firmware-gated), the 1000-range (three-phase) and 2040+ (EMS) registers.
WRITE_SAFE_SINGLE_PHASE: frozenset[int] = frozenset(
    {
        20,  # ENABLE_CHARGE_TARGET
        27,  # BATTERY_POWER_MODE
        29,  # SOC_FORCE_ADJUST
        *(31, 32),  # CHARGE_SLOT_2 (start, end)
        *range(35, 41),  # SYSTEM_TIME_YEAR/MONTH/DAY/HOUR/MINUTE/SECOND (35-40)
        *(44, 45),  # DISCHARGE_SLOT_2 (start, end)
        50,  # ACTIVE_POWER_RATE
        *(56, 57),  # DISCHARGE_SLOT_1 (start, end)
        59,  # ENABLE_DISCHARGE
        *(94, 95),  # CHARGE_SLOT_1 (start, end)
        96,  # ENABLE_CHARGE
        110,  # BATTERY_SOC_RESERVE
        111,  # BATTERY_CHARGE_LIMIT
        112,  # BATTERY_DISCHARGE_LIMIT
        114,  # BATTERY_DISCHARGE_MIN_POWER_RESERVE
        116,  # CHARGE_TARGET_SOC
        163,  # REBOOT
        166,  # ENABLE_RTC
        *(b + o for b in range(246, 269, 3) for o in (0, 1)),  # CHARGE_SLOT_3..10 (start/end pairs at 246+3k)
        *(b + o for b in range(276, 299, 3) for o in (0, 1)),  # DISCHARGE_SLOT_3..10 (start/end pairs at 276+3k)
    }
)

# Three-phase allowlist — DERIVED from the single-phase set (never re-typed): the
# single-phase slot pairs and scalars are swapped for their 1000-range equivalents.
WRITE_SAFE_THREE_PHASE: frozenset[int] = frozenset(
    (
        WRITE_SAFE_SINGLE_PHASE
        - {94, 95}  # CHARGE_SLOT_1_START/_END → 1113/1114
        - {31, 32}  # CHARGE_SLOT_2_START/_END → 1115/1116
        - {56, 57}  # DISCHARGE_SLOT_1_START/_END → 1118/1119
        - {44, 45}  # DISCHARGE_SLOT_2_START/_END → 1120/1121
        - {96}  # ENABLE_CHARGE → AC_CHARGE_ENABLE (1112)
        - {110}  # BATTERY_SOC_RESERVE → BATTERY_SOC_RESERVE_3PH (1109)
        - {116}  # CHARGE_TARGET_SOC → CHARGE_TARGET_SOC_3PH (1111)
    )
    | frozenset(
        {
            1078,  # BATTERY_RESERVE_SOC (three-phase only; no single-phase equivalent)
            1109,  # BATTERY_SOC_RESERVE_3PH (shadows HR 110)
            1111,  # CHARGE_TARGET_SOC_3PH (shadows HR 116)
            1112,  # AC_CHARGE_ENABLE (replaces ENABLE_CHARGE, HR 96)
            *range(1113, 1117),  # charge slots 1-2 (three-phase; start/end pairs 1113/1114, 1115/1116)
            *range(1118, 1122),  # discharge slots 1-2 (three-phase; start/end pairs 1118/1119, 1120/1121)
            1122,  # FORCE_DISCHARGE_ENABLE
            1123,  # FORCE_CHARGE_ENABLE
        }
    )
)

# EMS plant-controller allowlist — the EMS is a peer device, not an inverter subclass;
# its set does not derive from the single-phase base. Slot start/end pairs mirror
# model/slot_map.EMS_SLOTS; scalar names mirror RegisterMap.
WRITE_SAFE_EMS: frozenset[int] = frozenset(
    {
        2040,  # EMS_PLANT_ENABLE
        # EMS scheduling block (layout mirrors slot_map.EMS_SLOTS + RegisterMap scalars):
        #   2044-2052 — discharge slots 1-3, each a (start, end, EMS_DISCHARGE_TARGET_SOC_n) triple
        #   2053-2061 — charge slots 1-3, each a (start, end, EMS_CHARGE_TARGET_SOC_n) triple
        #   2062-2070 — export slots 1-3, each a (EXPORT_SLOT_n_START, _END, EMS_EXPORT_TARGET_SOC_n) triple
        #   2071 — EMS_EXPORT_POWER_LIMIT
        *range(2044, 2072),
    }
)

# HR(300-359) AC-output config-block writes, gated on has_ac_config_block rather than
# the model class: only a model that exposes the block (Model.AC / All-in-One) accepts
# them — never a DC-coupled hybrid, a three-phase unit (it remaps these controls to
# HR1110/1108), or an undetected client (#295/#296 review). 311/317 were previously in
# the universal set, accepted on DC hybrids and undetected (#297 moved them here).
WRITE_SAFE_AC_CONFIG: frozenset[int] = frozenset(
    {
        311,  # EXPORT_PRIORITY
        313,  # BATTERY_CHARGE_LIMIT_AC
        314,  # BATTERY_DISCHARGE_LIMIT_AC
        317,  # ENABLE_EPS
    }
)


def write_safe_registers(model: Model | None, arm_fw: int | None = None) -> frozenset[int]:
    """Registers this model/firmware permits at the normal (non-installer) write tier.

    Encapsulates the model→set decision previously duplicated across client.py's two
    write methods: EMS / three-phase / single-phase base selection, plus the AC-config
    union gated on has_ac_config_block AND NOT is_three_phase (AC_3PH has the block but
    remaps those controls — #295/#296/#297), plus the model=None → single-phase
    conservative fallback (has_capability returns False for None, so an undetected
    client falls through every branch — no special case needed). Does NOT include
    INSTALLER_WRITE_REGISTERS: the installer tier is a universal danger classification,
    unioned at the client boundary, not a per-model capability. ``arm_fw`` is accepted
    for signature consistency; no write capability is firmware-gated today.

    Callers pass the resolved ``caps.device_type`` (not the ``caps`` object) — this gate
    keys off the model directly, unlike the polling path's ``getattr(caps, name)`` in
    client.load_config(), which routes through the instance properties so tests can
    PropertyMock a not-yet-confirmed capability. There is no such test seam on the write
    path, so keying off the model is the simpler, equivalent choice here.
    """
    if has_capability("is_ems", model):
        safe = WRITE_SAFE_EMS
    elif has_capability("is_three_phase", model):
        safe = WRITE_SAFE_THREE_PHASE
    else:
        safe = WRITE_SAFE_SINGLE_PHASE
    if has_capability("has_ac_config_block", model) and not has_capability("is_three_phase", model):
        safe = safe | WRITE_SAFE_AC_CONFIG
    return safe
