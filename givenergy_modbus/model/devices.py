"""Generic energy-topology device abstractions.

These types are intentionally manufacturer- and protocol-agnostic — they
describe the shape of devices on an energy Plant graph regardless of how
their data is actually obtained. The GivEnergy-specific concrete decoders
(:class:`SinglePhaseInverter`, :class:`ThreePhaseInverter`, :class:`Ems`,
etc.) live in their own modules and populate these generic types.

Phase 1 of the Plant refactor introduces :class:`Inverter` as a read-only
facade unifying three data sources (direct register cache, EMS-rollup
view, or both reconciled). The design discipline these shapes are
written under — no concrete GivEnergy or Modbus types leak into the
generic surface, so an eventual extract to a base package is a code-org
refactor rather than an architectural redesign — is tracked alongside
the wider refactor sketch in the v2.1 roadmap (see ``docs/v2.1-roadmap.md``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# ``Inverter`` deliberately accepts the concrete decoders as ``Any`` because
# the generic shape doesn't depend on their identity, only on their attribute
# surface (``serial_number``, ``status``, ``p_inverter_out``, ``battery_soc``,
# ``t_inverter_heatsink``). Keeping the concrete types out of the generic
# module preserves the hoistability discipline documented in
# ``project_plant_abstraction_direction``.

DataSource = Literal["direct", "ems_rollup", "merged"]


@dataclass(frozen=True)
class InverterSummary:
    """Compact runtime summary of one inverter's state.

    The shape mirrors what a controller-level rollup typically exposes:
    identity (serial number), liveness (status), instantaneous power,
    battery charge level, and temperature. Per-PV-string / per-MPPT
    detail is *not* here — those require a direct register cache and
    live on the per-manufacturer concrete model.

    Field names match the directly-reachable inverter surface so the
    unified :class:`Inverter` facade can pull from either source by the
    same attribute name (``status``, ``p_inverter_out``,
    ``battery_soc``, ``t_inverter_heatsink``). Populated from any
    source that knows the rollup fields. GivEnergy's EMS exposes them
    at ``IR(2040..2094)`` and constructs one ``InverterSummary`` per
    managed slot; other manufacturers' rollups would populate the same
    shape from their own register / API surface.
    """

    serial_number: str
    status: Any | None = None  # Status enum value (manufacturer-specific), or None
    p_inverter_out: int | None = None  # active output power, W (signed)
    battery_soc: int | None = None  # battery state of charge, 0–100
    t_inverter_heatsink: float | None = None  # inverter heatsink temperature in °C


class Inverter:
    """Unified inverter facade — one node on the Plant graph.

    Represents one logical inverter regardless of how its data is sourced:

    - ``data_source="direct"`` — full register cache available (e.g. a
      reachable modbus dongle on the inverter itself). Read-through to
      the concrete model gives access to every per-PV-string and per-MPPT
      field. Returned by :py:meth:`from_direct`.
    - ``data_source="ems_rollup"`` — only an :class:`InverterSummary`
      from a controller-level rollup is available ("blinded"
      inverter — managed by an EMS but no separate dongle). Returned by
      :py:meth:`from_summary`.
    - ``data_source="merged"`` — both a direct cache and a summary are
      available, reconciled by serial number. The direct source is
      preferred for any field it knows; the summary fills gaps. Returned
      by :py:meth:`merge`.

    Phase 1 of the Plant refactor uses this purely as a read-only facade.
    Write commands continue to flow through the manufacturer-specific
    concrete models (e.g. :class:`SinglePhaseInverter`) — moving them
    onto this class is reconciled with :issue:`75` in phase 2.

    The class is deliberately not a Pydantic model. It's a thin
    multiplexer over its data sources; serialisation is the consumer's
    concern via the underlying sources.
    """

    __slots__ = ("data_source", "_direct", "_summary")

    def __init__(
        self,
        data_source: DataSource,
        direct: Any | None = None,
        summary: InverterSummary | None = None,
    ) -> None:
        """Construct directly (prefer the factory methods).

        The constructor is permissive about which source is present so
        the class can be tested with mocks; the factories enforce the
        invariant that ``data_source`` matches the supplied sources.
        """
        self.data_source = data_source
        self._direct = direct
        self._summary = summary

    @classmethod
    def from_direct(cls, direct: Any) -> "Inverter":
        """Construct from a directly-reachable concrete inverter model.

        ``direct`` is duck-typed: anything exposing the standard inverter
        attribute surface (``serial_number``, ``status``,
        ``p_inverter_out``, ``battery_soc``, ``t_inverter_heatsink``)
        works. In practice today this is :class:`SinglePhaseInverter` or
        :class:`ThreePhaseInverter`. Note that ``p_inverter_out`` is
        only directly exposed on :class:`ThreePhaseInverter`;
        single-phase direct sources will return ``None`` for that field
        unless the rollup ``summary`` is also merged in.
        """
        return cls(data_source="direct", direct=direct)

    @classmethod
    def from_summary(cls, summary: InverterSummary) -> "Inverter":
        """Construct from a rollup summary (e.g. EMS-managed, no direct dongle).

        The resulting inverter is "blinded": :attr:`batteries` is empty,
        per-PV-string fields aren't available. Consumers see the same
        interface as a directly-reachable inverter, just with fewer
        populated fields.
        """
        return cls(data_source="ems_rollup", summary=summary)

    @classmethod
    def merge(cls, direct: Any, summary: InverterSummary) -> "Inverter":
        """Construct from a direct source reconciled with a rollup summary.

        Reconciliation is the caller's responsibility (typically matching
        on serial number at end of detect). Once merged, direct fields
        are preferred; the summary fills any gap the direct source has.
        """
        return cls(data_source="merged", direct=direct, summary=summary)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def serial_number(self) -> str:
        """The inverter's serial number.

        Prefer the direct source (more authoritative), fall back to the
        summary. At least one is always present by construction.
        """
        if self._direct is not None:
            value = getattr(self._direct, "serial_number", None)
            if value:
                return value
        if self._summary is not None:
            return self._summary.serial_number
        # Should be unreachable by construction, but keep the contract honest.
        return ""

    @property
    def is_blinded(self) -> bool:
        """True when no direct register cache is available for this inverter.

        Blinded inverters expose only the controller-level rollup fields
        (status, power, SoC, temperature, serial). Per-PV-string detail,
        battery-level detail, and write access are all unavailable.
        """
        return self._direct is None

    # ------------------------------------------------------------------
    # Read-through fields
    # ------------------------------------------------------------------

    def _from_direct(self, name: str) -> Any | None:
        if self._direct is None:
            return None
        return getattr(self._direct, name, None)

    def _from_summary(self, name: str) -> Any | None:
        if self._summary is None:
            return None
        return getattr(self._summary, name, None)

    def _resolve(self, name: str) -> Any | None:
        """Direct source preferred; summary fills gaps."""
        value = self._from_direct(name)
        if value is not None:
            return value
        return self._from_summary(name)

    @property
    def status(self) -> Any | None:
        """Current operating status (enum value or None if unknown)."""
        return self._resolve("status")

    @property
    def p_inverter_out(self) -> int | None:
        """Inverter active output power in watts (signed).

        Resolved from :class:`ThreePhaseInverter.p_inverter_out` on direct
        sources, or :attr:`InverterSummary.p_inverter_out` on rollup
        sources. Single-phase direct sources don't expose an aggregate
        active-output field today, so this returns ``None`` for them
        unless a rollup summary has been merged in.
        """
        return self._resolve("p_inverter_out")

    @property
    def battery_soc(self) -> int | None:
        """Battery state of charge, 0–100."""
        return self._resolve("battery_soc")

    @property
    def t_inverter_heatsink(self) -> float | None:
        """Inverter heatsink temperature in °C."""
        return self._resolve("t_inverter_heatsink")

    # ------------------------------------------------------------------
    # Sub-devices
    # ------------------------------------------------------------------

    @property
    def batteries(self) -> list[Any]:
        """List of batteries attached to this inverter.

        Empty list when the inverter is blinded — we honestly do not
        know what batteries (if any) are attached, since the EMS rollup
        does not expose per-battery serials or SoC. Phase 2 of the Plant
        refactor populates this from the inverter's own register cache;
        for now phase 1 conservatively returns ``[]`` for all sources
        because the legacy ``Plant.batteries`` accessor already serves
        directly-reachable installs.
        """
        return []

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def direct(self) -> Any | None:
        """The underlying directly-reachable inverter model, or None if blinded.

        Exposed so consumers that need per-PV-string / per-MPPT fields
        not surfaced on this facade can read through. Future-friendly:
        when the unified surface grows, consumers can migrate off this
        accessor at their own pace.
        """
        return self._direct

    @property
    def summary(self) -> InverterSummary | None:
        """The underlying rollup summary, or None when only a direct source is present."""
        return self._summary

    def __repr__(self) -> str:
        return (
            f"Inverter(serial_number={self.serial_number!r}, "
            f"data_source={self.data_source!r}, "
            f"is_blinded={self.is_blinded})"
        )
