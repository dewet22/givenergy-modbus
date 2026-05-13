import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from json import JSONEncoder
from typing import Any, get_type_hints

from givenergy_modbus.model import TimeSlot

_logger = logging.getLogger(__name__)


class Converter:
    """Type of data register represents. Encoding is always big-endian."""

    @staticmethod
    def uint16(val: int) -> int:
        """Simply return the raw unsigned 16-bit integer register value."""
        if val is not None:
            return int(val)

    @staticmethod
    def duint8(val: int, *idx: int) -> int:
        """Split one register into two unsigned 8-bit ints and return the specified index."""
        if val is not None:
            vals = (val >> 8), (val & 0xFF)
            return vals[idx[0]]

    @staticmethod
    def uint32(high_val: int, low_val: int) -> int:
        """Combine two registers into an unsigned 32-bit int."""
        if high_val is not None and low_val is not None:
            return (high_val << 16) + low_val

    @staticmethod
    def int32(high_val: int, low_val: int) -> int:
        """Combine two registers into a signed 32-bit int (two's complement)."""
        if high_val is not None and low_val is not None:
            raw = (high_val << 16) + low_val
            return raw if raw < 0x80000000 else raw - 0x100000000

    @staticmethod
    def timeslot(start_time: int, end_time: int) -> TimeSlot:
        """Interpret register as a time slot."""
        if start_time is not None and end_time is not None:
            # Some inverters store 60 as a sentinel for an unset slot (portal shows '--:--').
            # Passing 60 as minutes to TimeSlot.from_repr raises ValueError, so treat it as unset.
            if start_time == 60 or end_time == 60:
                return None
            return TimeSlot.from_repr(start_time, end_time)

    @staticmethod
    def bool(val: int) -> "bool":
        """Interpret register as a bool."""
        if val is not None:
            return bool(val)
        return None

    @staticmethod
    def string(*vals: int) -> str | None:
        """Represent one or more registers as a concatenated string."""
        if vals is not None and None not in vals:
            return (
                b"".join(v.to_bytes(2, byteorder="big") for v in vals)
                .decode(encoding="latin1")
                .replace("\x00", "")
                .upper()
            )
        return None

    @staticmethod
    def fstr(val, fmt) -> str | None:
        """Render a value using a format string."""
        if val is not None:
            return f"{val:{fmt}}"
        return None

    @staticmethod
    def firmware_version(dsp_version: int, arm_version: int) -> str | None:
        """Represent ARM & DSP firmware versions in the same format as the dashboard."""
        if dsp_version is not None and arm_version is not None:
            return f"D0.{dsp_version}-A0.{arm_version}"

    @staticmethod
    def hex(val: int, width: int = 4) -> str:
        """Represent a register value as a 4-character hex string."""
        if val is not None:
            return f"{val:0{width}x}"

    @staticmethod
    def milli(val: int) -> float:
        """Represent a register value as a float in 1/1000 units."""
        if val is not None:
            return val / 1000

    @staticmethod
    def centi(val: int) -> float:
        """Represent a register value as a float in 1/100 units."""
        if val is not None:
            return val / 100

    @staticmethod
    def int16(val: int) -> int:
        """Interpret a 16-bit register value as a signed integer (two's complement)."""
        if val is not None:
            return val if val < 0x8000 else val - 0x10000

    @staticmethod
    def deci(val: int) -> float:
        """Represent a register value as a float in 1/10 units."""
        if val is not None:
            return val / 10

    @staticmethod
    def datetime(year, month, day, hour, min, sec) -> "datetime | None":
        """Compose a datetime from 6 registers."""
        if None not in [year, month, day, hour, min, sec]:
            return datetime(year + 2000, month, day, hour, min, sec)
        return None

    @staticmethod
    def nominal_voltage(option: int) -> int | None:
        """Map register option index to nominal grid voltage (V): 0→230, 1→208, 2→240."""
        if option is not None:
            return (230, 208, 240)[option]
        return None

    @staticmethod
    def nominal_frequency(option: int) -> int | None:
        """Map register option index to nominal grid frequency (Hz): 0→50, 1→60."""
        if option is not None:
            return (50, 60)[option]
        return None

    @staticmethod
    def inverter_fault_code(val: int) -> list[str] | None:
        """Decode a 32-bit inverter fault bitmask into a list of active fault names.

        Bit table sourced from britkat1980/givenergy-modbus-async; not verified against
        official firmware documentation (contact @britkat1980 for provenance).
        Three-phase units use a different 9-word fault register layout (IR 1300–1307)
        and are not decoded here — see open questions in fork-merge-plan.md.
        """
        if val is None:
            return None
        _FAULTS = [
            None,
            None,
            None,
            "Backup Overload Fault",
            None,
            None,
            "Grid Monitor Comm Fault",
            "ARM Comms Fault",
            "Consistent Fault",
            "EEPROM Fault",
            None,
            None,
            None,
            None,
            None,
            None,
            "Inverter Frequency Fault",
            "Relay Fault",
            "Inverter Voltage Fault",
            "GFCI Fault",
            "Hail Sensor Fault",
            "DSP Comms Fault",
            "Bus over voltage",
            "Inverter Current Fault",
            "No Utility",
            "PV Isolation Fault",
            "Current leak high",
            "DCI high",
            "PV Over voltage",
            "Grid voltage Fault",
            "Grid Frequency Fault",
            "Inverter NTC Fault",
            None,
        ]
        bits = f"{val:032b}"
        return [_FAULTS[i] for i, b in enumerate(bits) if b == "1" and _FAULTS[i] is not None]

    @staticmethod
    def hexfield(val: int, idx: int, width: int = 1) -> int | None:
        """Extract `width` hex digit(s) starting at `idx` from the 4-char hex representation."""
        if val is not None:
            return int(f"{val:04X}"[idx : idx + width], 16)
        return None

    @staticmethod
    def bitfield(val: int, low: int, high: int) -> int | None:
        """Extract the bit range [low, high] (inclusive) from a 16-bit register value."""
        if val is not None:
            return int(f"{val:016b}"[low : high + 1], 2)
        return None

    @staticmethod
    def gateway_version(first: int, second: int, third: int, fourth: int) -> str | None:
        """Decode gateway firmware version string from 4 registers (e.g. 'GA000009')."""
        if None in (first, second, third, fourth):
            return None
        prefix = b"".join(v.to_bytes(2, "big") for v in (first, second)).decode("latin1").replace("\x00", "")
        digits = "".join(str(b) for v in (third, fourth) for b in v.to_bytes(2, "big"))
        return prefix + digits


@dataclass(init=False)
class RegisterDefinition:
    """Specifies how to convert raw register values into their actual representation."""

    pre_conv: Callable | tuple | None
    post_conv: Callable | tuple[Callable, Any] | None
    registers: tuple["Register"]
    min: int | float | None
    max: int | float | None

    def __init__(self, *args, min: int | float | None = None, max: int | float | None = None):
        self.pre_conv = args[0]
        self.post_conv = args[1]
        self.registers = args[2:]  # type: ignore[assignment]
        self.min = min
        self.max = max

    def __hash__(self):
        return hash(self.registers)


_SERIAL_PATTERN = re.compile(r"[A-Z]{2}\d{4}[A-Z]\d{3}")


def is_valid_serial(s: str | None) -> bool:
    """Return True if s looks like a real GivEnergy serial number (exactly 10 [A-Z0-9] chars).

    Also logs a warning when the value passes the length/charset gate but does not match the
    expected AA0000A000 pattern — preserving compatibility with unknown real-world variants.
    """
    if not (s and len(s) == 10 and s.isalnum() and s == s.upper()):
        return False
    if not _SERIAL_PATTERN.fullmatch(s):
        _logger.warning("serial number %r is valid but does not match expected pattern AA0000A000", s)
    return True


class RegisterGetter:
    """Specifies how device attributes are derived from raw register values."""

    REGISTER_LUT: dict[str, RegisterDefinition]

    def __init__(self, obj: Any) -> None:
        self._obj = obj

    def get(self, key: str, default: Any = None) -> Any:
        """Return a named register's value, after pre- and post-conversion."""
        try:
            defn = self.REGISTER_LUT[key]
        except KeyError:
            return default

        regs = [self._obj.get(reg) for reg in defn.registers]

        if None in regs:
            return None

        if defn.pre_conv:
            if isinstance(defn.pre_conv, tuple):
                args = regs + list(defn.pre_conv[1:])
                val = defn.pre_conv[0](*args)
            else:
                val = defn.pre_conv(*regs)
        else:
            val = regs

        if defn.post_conv:
            if isinstance(defn.post_conv, tuple):
                val = defn.post_conv[0](val, *defn.post_conv[1:])
            else:
                val = defn.post_conv(val)

        if val is not None and (defn.min is not None or defn.max is not None):
            if (defn.min is not None and val < defn.min) or (defn.max is not None and val > defn.max):
                # TODO(enforcement): change to `return None` to suppress out-of-bounds values.
                _logger.error("register value out of bounds: %r not in [%s, %s]", val, defn.min, defn.max)

        return val

    def build(self) -> dict[str, Any]:
        """Resolve all fields in REGISTER_LUT against the wrapped cache."""
        return {key: self.get(key) for key in self.REGISTER_LUT}

    @classmethod
    def validate_bank(
        cls,
        incoming: dict["Register", int],
        committed: Any,
    ) -> list[str]:
        """Check incoming registers against bounds-constrained fields.

        Returns the names of any fields whose post-conversion value falls outside
        the defined bounds. Only fields that have bounds defined and whose registers
        overlap the incoming bank are checked.
        """
        from givenergy_modbus.model.register_cache import RegisterCache

        candidate = RegisterCache({**committed, **incoming})
        getter = cls(candidate)
        violations = []

        for name, defn in cls.REGISTER_LUT.items():
            if defn.min is None and defn.max is None:
                continue
            if not any(r in incoming for r in defn.registers):
                continue
            if any(candidate.get(r) is None for r in defn.registers):
                continue
            val = getter.get(name)
            # TODO(enforcement): once get() suppresses OOB values (returns None), this explicit
            # bounds check can be replaced with the simpler `if getter.get(name) is None`.
            if val is not None and (
                (defn.min is not None and val < defn.min) or (defn.max is not None and val > defn.max)
            ):
                violations.append(name)

        return violations

    @classmethod
    def is_coherent(cls, incoming: dict["Register", int], committed: Any) -> bool:
        """Return False if the incoming bank contains a serial number that is not valid.

        Only fires when the serial number registers are present in the incoming bank.
        Getters without a 'serial_number' field always return True.
        """
        if "serial_number" not in cls.REGISTER_LUT:
            return True
        serial_regs = set(cls.REGISTER_LUT["serial_number"].registers)
        if not serial_regs & set(incoming):
            return True
        from givenergy_modbus.model.register_cache import RegisterCache

        candidate = RegisterCache({**committed, **incoming})
        return is_valid_serial(cls(candidate).get("serial_number"))

    @classmethod
    def to_fields(cls) -> dict[str, tuple[Any, None]]:
        """Determine a pydantic fields definition for the class."""

        def infer_return_type(obj: Any):
            if isinstance(obj, staticmethod):
                obj = obj.__func__
            if callable(obj) and not isinstance(obj, type):
                # Use get_type_hints() to resolve annotations in the correct module scope.
                # Direct __annotations__ access fails under PEP 649 (Python 3.14+) when
                # a method name shadows a builtin (e.g. Converter.bool shadows bool).
                try:
                    hints = get_type_hints(obj)
                    if ret := hints.get("return"):
                        return ret
                except Exception:  # nosec B110
                    pass
                return Any
            return obj  # assume it is a class/type already

        def return_type(v: RegisterDefinition):
            if v.post_conv:
                if isinstance(v.post_conv, tuple):
                    return infer_return_type(v.post_conv[0])
                else:
                    return infer_return_type(v.post_conv)
            elif v.pre_conv:
                if isinstance(v.pre_conv, tuple):
                    return infer_return_type(v.pre_conv[0])
                else:
                    return infer_return_type(v.pre_conv)
            return Any

        return {k: (return_type(v) | None, None) for k, v in cls.REGISTER_LUT.items()}


class RegisterEncoder(JSONEncoder):
    """Custom JSONEncoder to work around Register behaviour.

    This is a workaround to force registers to render themselves as strings instead of
    relying on the internal identity by default.
    """

    def default(self, o: Any) -> str:
        """Custom JSON encoder to treat RegisterCaches specially."""
        if isinstance(o, Register):
            return f"{o._type}_{o._idx}"
        else:
            return super().default(o)


class Register:
    """Register base class."""

    TYPE_HOLDING = "HR"
    TYPE_INPUT = "IR"
    TYPE_METER = "MR"

    _type: str
    _idx: int

    def __init__(self, idx):
        self._idx = idx

    def __str__(self):
        return "%s_%d" % (self._type, int(self._idx))

    __repr__ = __str__

    def __eq__(self, other):
        return isinstance(other, Register) and self._type == other._type and self._idx == other._idx

    def __hash__(self):
        return hash((self._type, self._idx))


class HR(Register):
    """Holding Register."""

    _type = Register.TYPE_HOLDING


class IR(Register):
    """Input Register."""

    _type = Register.TYPE_INPUT


class MR(Register):
    """Meter Product Register."""

    _type = Register.TYPE_METER
