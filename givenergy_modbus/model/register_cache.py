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


def _get_serial_groups() -> "list[tuple[str, int, int]]":
    """Return (reg_type, base, count) for every C.serial register group (built once)."""
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
    _SERIAL_GROUPS = groups
    return _SERIAL_GROUPS


class RegisterCache(defaultdict[Register, int]):
    """Holds a cache of Registers populated after querying a device."""

    def __init__(self, registers: dict[Register, int] | None = None) -> None:
        if registers is None:
            registers = {}
        super().__init__(lambda: 0, registers)

    def json(self) -> str:
        """Return JSON representation of the register cache, to mirror `from_json()`."""  # noqa: D402,D202,E501
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
                    ret[lookup[reg](int(idx))] = v
                except (KeyError, ValueError):
                    # KeyError: unknown register prefix (e.g. a future namespace
                    # we don't know about yet). ValueError: idx wasn't an int.
                    # Either way, skip the entry rather than aborting the load.
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
        LUTs, decodes each group to a string, applies ``Converter.redact_serial``
        (zeroing the trailing unit digits), and re-encodes back into register values.
        Groups that are only partially present in the cache, or whose decoded string
        doesn't match a known serial pattern, are left unchanged.

        Produces the same ``AAYYWWA000``-style placeholders as :class:`FrameRedactor`,
        so a redacted export is indistinguishable from a redacted capture.
        """
        from givenergy_modbus.model.register import Converter

        _reg_cls: dict[str, type[Register]] = {"HR": HR, "IR": IR}
        result = RegisterCache(dict(self))
        for reg_type, base, count in _get_serial_groups():
            reg_cls = _reg_cls.get(reg_type)
            if reg_cls is None:
                continue
            regs = [reg_cls(base + i) for i in range(count)]
            if not all(r in self for r in regs):
                continue
            raw = b"".join(self[r].to_bytes(2, "big") for r in regs)
            serial_str = raw.decode("latin1").replace("\x00", "").upper()
            redacted = Converter.redact_serial(serial_str)
            if redacted is None or redacted == serial_str:
                continue
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
