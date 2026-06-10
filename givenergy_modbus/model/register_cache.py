import datetime
import json
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from givenergy_modbus.model.register import HR, IR, MR, Register

if TYPE_CHECKING:
    from givenergy_modbus.model import TimeSlot

_logger = logging.getLogger(__name__)

_SERIAL_GROUPS: "list[tuple[str, int, int]] | None" = None

# BMU serials are not in any REGISTER_LUT (Bmu.from_register_cache decodes them
# manually at IR(114 + _BMU_STRIDE * bmu_index)).  Add groups for up to this
# many BMUs per BCU so a BCU cache is fully redacted.  Absent groups are
# harmlessly skipped by the all-registers-present check in redact_serials().
_MAX_BMUS_PER_BCU = 8
_BMU_SERIAL_BASE = 114
_BMU_STRIDE = 120


def _get_serial_groups() -> "list[tuple[str, int, int]]":
    """Return (reg_type, base, count) for every C.serial register group (built once).

    Covers:
    - all groups discovered by walking the model REGISTER_LUTs (inverter/battery/
      EMS/gateway Converter.serial fields);
    - explicit BMU serial groups for up to ``_MAX_BMUS_PER_BCU`` modules per BCU,
      because Bmu decodes its serial manually (no LUT entry).
    """
    global _SERIAL_GROUPS
    if _SERIAL_GROUPS is not None:
        return _SERIAL_GROUPS
    from givenergy_modbus.model import battery, ems, gateway, inverter
    from givenergy_modbus.model.register import Converter

    seen: set[tuple[str, int, int]] = set()
    groups: list[tuple[str, int, int]] = []
    for module in (inverter, battery, ems, gateway):
        for attr in dir(module):
            cls = getattr(module, attr)
            if not isinstance(cls, type):
                continue
            lut = getattr(cls, "REGISTER_LUT", None)
            if not lut:
                continue
            for _field, defn in lut.items():
                pre_conv = defn.pre_conv[0] if isinstance(defn.pre_conv, tuple) else defn.pre_conv
                if pre_conv is Converter.serial and defn.registers:
                    reg_type = type(defn.registers[0]).__name__
                    base = defn.registers[0]._idx
                    count = len(defn.registers)
                    key = (reg_type, base, count)
                    if key not in seen:
                        seen.add(key)
                        groups.append(key)
    for i in range(_MAX_BMUS_PER_BCU):
        key = ("IR", _BMU_SERIAL_BASE + _BMU_STRIDE * i, 5)
        if key not in seen:
            seen.add(key)
            groups.append(key)
    # Legacy first_battery_serial_number registers (HR 8-12) — removed from the LUT
    # (#191), but still redacted: AIO firmware stores the unit serial here byte-swapped
    # (CH… → HC…), recoverable to the real serial, so it must not leak in a shared
    # export. Appended explicitly, like the BMU serials, since no LUT Def carries it.
    groups.append(("HR", 8, 5))
    # Meter product serial (MR 60-61, FC 0x16). The MeterProductRegisterGetter walk above
    # doesn't reach it (meter isn't a walked module and its Def is C.string), so add it
    # explicitly. It's a short non-GE-pattern identifier; redact_serials() blanks it via the
    # fail-closed strict redaction (audit H2). Guarded against a future auto-discovery duplicate.
    mr_key = ("MR", 60, 2)
    if mr_key not in seen:
        seen.add(mr_key)
        groups.append(mr_key)
    _SERIAL_GROUPS = groups
    return _SERIAL_GROUPS


class RegisterCache(defaultdict[Register, int]):
    """Holds a cache of Registers populated after querying a device."""

    def __init__(self, registers: dict[Register, int] | None = None) -> None:
        if registers is None:
            registers = {}
        super().__init__(lambda: 0, registers)

    def json(self) -> str:
        """Return JSON representation of the register cache, to mirror `from_json()`.

        .. warning::
            This emits **unredacted** serial-number registers (and any other raw values).
            For a share-safe export, redact first: ``cache.redact_serials().json()``.
        """  # noqa: D402,D202,E501
        return json.dumps(self)

    @classmethod
    def from_json(cls, data: str) -> "RegisterCache":
        """Instantiate a RegisterCache from its JSON form."""

        def register_object_hook(object_dict: dict[str, int]) -> dict[Register, int]:
            """Rewrite the parsed object to have Register instances as keys instead of their (string) repr."""
            lookup = {"HR": HR, "IR": IR, "MR": MR}
            ret = {}
            for k, v in object_dict.items():
                if k.find("(") > 0:
                    reg, idx = k.split("(", maxsplit=1)
                    idx = idx[:-1]
                elif k.find(":") > 0:
                    reg, idx = k.split(":", maxsplit=1)
                else:
                    _logger.warning("Skipping unrecognised register key %r", k)
                    continue
                try:
                    register = lookup[reg](int(idx))
                    if v is None:
                        # None is the codebase's legitimate "unset" sentinel (e.g. a missing
                        # slot endpoint); preserve it so it round-trips through JSON.
                        value = None
                    elif isinstance(v, bool):
                        # bool is an int subclass, so 1 == True would slip past the range check;
                        # reject JSON true/false rather than silently storing it as 1/0 (M4).
                        raise ValueError(f"register value {v!r} is a bool, not an integer")
                    else:
                        value = int(v)
                        if value != v or not (0 <= value <= 0xFFFF):
                            # Fail closed: a register is an unsigned 16-bit word. A fractional
                            # number (silently truncated by int()) or an out-of-range value
                            # would later raise OverflowError in to_bytes() in a consumer (M4).
                            raise ValueError(f"register value {v!r} is not an unsigned 16-bit int")
                    ret[register] = value
                except (KeyError, ValueError, TypeError, OverflowError):
                    # KeyError: unknown register prefix (e.g. a future namespace we don't know
                    # about yet). ValueError: idx wasn't an int, or the value wasn't a coercible
                    # in-range integer (a string / bool / fractional / out-of-range value in a
                    # tampered cache JSON). TypeError: value was a non-scalar (list/dict).
                    # OverflowError: int(float("inf")) from a non-standard JSON Infinity. Skip the
                    # entry rather than aborting the load or storing a value that crashes a consumer.
                    _logger.warning("Skipping unloadable register entry %r=%r", k, v)
                    continue
            return ret

        return cls(registers=(json.loads(data, object_hook=register_object_hook)))

    # helper methods to convert register data types

    def to_string(self, *registers: Register) -> str:
        """Combine registers into an ASCII string."""
        s = "".join([self[r].to_bytes(2, byteorder="big").decode(encoding="latin1") for r in registers])
        return "".join(filter(str.isalnum, s)).upper()

    def to_hex_string(self, *registers: Register) -> str:
        """Render a register as a 2-byte hexadecimal value."""
        values = [f"{self[r]:04x}" for r in registers]
        if all(values):
            ret = ""
            for r in registers:
                ret += f"{self[r]:04x}"
            return "".join(filter(str.isalnum, ret)).upper()
        return ""

    def to_duint8(self, *registers: Register) -> tuple[int, ...]:
        """Split registers into two unsigned 8-bit integers each."""
        return sum(((self[r] >> 8, self[r] & 0xFF) for r in registers), ())

    def to_uint32(self, high_register: Register, low_register: Register) -> int:
        """Combine two registers into an unsigned 32-bit integer."""
        return (self[high_register] << 16) + self[low_register]

    def to_datetime(self, y: Register, m: Register, d: Register, h: Register, min: Register, s: Register):
        """Combine 6 registers into a datetime, with safe defaults for zeroes."""
        return datetime.datetime(self[y] + 2000, self.get(m, 1) or 1, self.get(d, 1) or 1, self[h], self[min], self[s])

    def redact_serials(self) -> "RegisterCache":
        """Return a copy of this cache with all known serial-number registers redacted.

        Identifies every register group tagged as ``Converter.serial`` in the model
        LUTs (plus BMU serial groups, which are decoded manually), decodes each fully-
        present group, and date-redacts values that match a known GE serial pattern
        (prefix + manufacture date kept, unit digits zeroed).

        **Fails open for HR/IR groups by necessity.** Serial groups are applied without
        device-type context and overlap: the BMU serial groups (e.g. IR(114-118)) are
        real serials only on HV BMU stacks, but on an LV battery those addresses hold the
        battery serial's last register (IR114) and ordinary data (IR115 = usb_device_inserted).
        With no way to tell a non-GE serial from non-serial data, anything that doesn't
        match a serial pattern is left **unchanged** — blanking it would destroy legitimate
        data and corrupt overlapping serials. The share-safe-export guarantee (#212/#214)
        is enforced fail-closed where it is unambiguous: the inverter/dongle header serials
        (:meth:`Plant.redact`) and the meter product identifier (MR, a distinct register
        namespace, blanked below).

        Produces the same ``AAYYWWA000``-style placeholders as :class:`FrameRedactor`,
        so a redacted export is indistinguishable from a redacted capture.
        """
        from givenergy_modbus.model.register import Converter

        _reg_cls: dict[str, type[Register]] = {"HR": HR, "IR": IR, "MR": MR}
        result = RegisterCache(dict(self))
        for reg_type, base, count in _get_serial_groups():
            reg_cls = _reg_cls.get(reg_type)
            if reg_cls is None:
                continue
            regs = [reg_cls(base + i) for i in range(count)]
            # Meter product identifier (MR): a short non-GE value in a distinct register namespace
            # that can't overlap HR/IR data — safe to fail closed. Blank whatever is present (a
            # full or partial fragment) before the HR/IR completeness check, without injecting
            # absent registers.
            if reg_type == "MR":
                for reg in regs:
                    if isinstance(self.get(reg), int):
                        result[reg] = 0
                continue
            if not all(isinstance(self.get(r), int) for r in regs):
                continue
            raw = b"".join((self[r] & 0xFFFF).to_bytes(2, "big") for r in regs)
            serial_str = raw.decode("latin1").replace("\x00", "").upper()
            redacted = Converter.redact_serial(serial_str)
            if redacted is None or redacted == serial_str:
                continue  # not a recognised serial — leave unchanged (may be non-serial data)
            redacted_bytes = redacted.encode("latin1").ljust(count * 2, b"\x00")[: count * 2]
            for i, reg in enumerate(regs):
                result[reg] = int.from_bytes(redacted_bytes[i * 2 : i * 2 + 2], "big")
        return result

    def to_timeslot(self, start: Register, end: Register) -> "TimeSlot | None":
        """Combine two registers into a time slot, or None if either is unset.

        Mirrors Converter.timeslot: a missing/None endpoint, or the raw value 60
        (a hardware sentinel for an unset slot — the portal shows '--:--'), means
        "unset". Both would otherwise raise ValueError in TimeSlot.from_repr.
        """
        from givenergy_modbus.model import TimeSlot

        start_val, end_val = self.get(start), self.get(end)
        if start_val is None or end_val is None or start_val == 60 or end_val == 60:
            return None
        return TimeSlot.from_repr(start_val, end_val)
