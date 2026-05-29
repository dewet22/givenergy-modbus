import logging
import re
from datetime import datetime
from json import JSONEncoder
from typing import Any, ClassVar, get_type_hints

from pydantic import BaseModel, ConfigDict

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
    def int32(high_val: int | None, low_val: int | None) -> int | None:
        """Combine two registers into a signed 32-bit int (two's complement)."""
        if high_val is not None and low_val is not None:
            raw = (high_val << 16) + low_val
            return raw if raw < 0x80000000 else raw - 0x100000000
        return None

    @staticmethod
    def timeslot(start_time: int, end_time: int) -> "TimeSlot | None":
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
        return {0: 230, 1: 208, 2: 240}.get(option)

    @staticmethod
    def nominal_frequency(option: int) -> int | None:
        """Map register option index to nominal grid frequency (Hz): 0→50, 1→60."""
        return {0: 50, 1: 60}.get(option)

    @staticmethod
    def bitfield(val: int | None, low: int, high: int) -> int | None:
        """Extract the bit range [low, high] (inclusive) from a 16-bit register value.

        Indices are MSB-first: 0 = bit 15, 15 = bit 0.
        """
        if val is None:
            return None
        return (val >> (15 - high)) & ((1 << (high - low + 1)) - 1)

    @staticmethod
    def gateway_version(first: int, second: int, third: int, fourth: int) -> str | None:
        """Decode gateway firmware version string from 4 registers (e.g. 'GA000009')."""
        if None in (first, second, third, fourth):
            return None
        prefix = b"".join(v.to_bytes(2, "big") for v in (first, second)).decode("latin1").replace("\x00", "")
        digits = "".join(str(b) for v in (third, fourth) for b in v.to_bytes(2, "big"))
        return prefix + digits


# Decimal places implied by each numeric converter's scaling. Used to derive a
# register's display precision (see RegisterDefinition.precision): deci/centi/
# milli divide by 10/100/1000, the integer converters yield whole numbers.
# Converters absent from this map (enums, bools, strings, timeslots, datetimes,
# and any bespoke converter) are treated as non-numeric — precision None.
_PRECISION_BY_CONVERTER: dict[Any, int] = {
    Converter.milli: 3,
    Converter.centi: 2,
    Converter.deci: 1,
    Converter.uint16: 0,
    Converter.int16: 0,
    Converter.uint32: 0,
    Converter.int32: 0,
    Converter.duint8: 0,
}


class RegisterDefinition(BaseModel):
    """Specifies how to convert raw register values into their actual representation.

    ``min_value`` / ``max_value`` are the bounds for the post-conv value;
    they're named with the ``_value`` suffix rather than ``min`` / ``max``
    to avoid shadowing the builtins of the same name (ruff A002, CodeRabbit
    nag — see #73). The legacy ``min=`` / ``max=`` kwargs on ``__init__`` are
    preserved so the 150+ ``Def(...)`` call sites don't churn.
    """

    # `arbitrary_types_allowed` for `Register` instances; `frozen` because
    # these are class-level LUT constants that must not mutate after build.
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    pre_conv: Any = None
    post_conv: Any = None
    registers: tuple = ()
    min_value: int | float | None = None
    max_value: int | float | None = None

    def __init__(
        self,
        *args: Any,
        min: int | float | None = None,  # noqa: A002 — legacy kwarg, mapped to min_value
        max: int | float | None = None,  # noqa: A002 — legacy kwarg, mapped to max_value
        **kwargs: Any,
    ) -> None:
        # Map legacy positional `(pre_conv, post_conv, *registers)` + min/max
        # kwargs onto the new field names. All 150+ Def(...) call sites use
        # this form; the keyword form remains available for direct callers.
        if args:
            kwargs["pre_conv"] = args[0]
            kwargs["post_conv"] = args[1] if len(args) > 1 else None
            kwargs["registers"] = args[2:]
        if min is not None:
            kwargs["min_value"] = min
        if max is not None:
            kwargs["max_value"] = max
        super().__init__(**kwargs)

    def __hash__(self) -> int:
        # Preserve the historic identity: a definition is identified by its
        # register set, not its conversions or bounds. Used as a dict key in
        # places that look up by register tuple.
        return hash(self.registers)

    @property
    def precision(self) -> int | None:
        """Decimal places implied by this register's numeric scaling.

        Returns 0 for integer quantities, 1/2/3 for deci-/centi-/milli-scaled
        floats, and None for non-numeric registers (enums, bools, strings,
        timeslots) or any converter without a defined scaling. The post-
        converter wins when present — it produces the final value — mirroring
        the resolution order used for return-type inference.
        """
        # Converters are stored as plain functions (Converter.<name> resolves
        # through the staticmethod descriptor at Def-construction time), and a
        # post-conv may carry a (converter, *args) tuple — unwrap to the callable.
        conv = self.post_conv or self.pre_conv
        if isinstance(conv, tuple):
            conv = conv[0]
        return _PRECISION_BY_CONVERTER.get(conv)


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

    @classmethod
    def precision_of(cls, name: str) -> int | None:
        """Decimal places for a register-backed attribute (None if non-numeric/unknown).

        Returns None for attributes not in the LUT (e.g. computed/aggregate
        values), so callers can fall back to their own default.
        """
        defn = cls.REGISTER_LUT.get(name)
        return defn.precision if defn is not None else None

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

        has_bounds = defn.min_value is not None or defn.max_value is not None
        if val is not None and has_bounds and not all(r == 0 for r in regs):
            # An all-zero raw bank means the hardware didn't populate these registers (e.g. an
            # absent external meter slot); skip bounds checks for that case rather than spamming
            # the log every poll. Doing this at the raw level rather than post-conv keeps the
            # "0x0000 means unset" intent unambiguous.
            if (defn.min_value is not None and val < defn.min_value) or (
                defn.max_value is not None and val > defn.max_value
            ):
                # Suppress out-of-bounds values: returning None is more honest than letting an
                # obviously-wrong value reach downstream consumers. See #82 for the corruption
                # pattern this protects against — values produced library-side that never appear
                # on the wire and decode well outside the declared min/max.
                _logger.debug("register value out of bounds: %r not in [%s, %s]", val, defn.min_value, defn.max_value)
                return None

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
            if defn.min_value is None and defn.max_value is None:
                continue
            if not any(r in incoming for r in defn.registers):
                continue
            if any(candidate.get(r) is None for r in defn.registers):
                continue
            if all(candidate.get(r) == 0 for r in defn.registers):
                # All-zero raw registers: hardware sentinel for "unpopulated" — skip bounds
                # check to match get()'s behaviour.
                continue
            # get() suppresses OOB values by returning None. The guards above (registers
            # present and not all-zero) mean a None return here can only be from the
            # bounds check, so it's a violation.
            if getter.get(name) is None:
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


class RegisterMetadataMixin:
    """Exposes register metadata on a device model built from a RegisterGetter.

    A model instance is decoupled from the getter that built it (the LUT lives
    on the getter class), so callers holding e.g. an ``Inverter`` can't reach
    the register definitions directly. Concrete models set ``REGISTER_GETTER``
    to their getter and gain queries like :meth:`precision_of` that resolve
    against that getter's LUT. Composed as a plain mixin — same pattern as the
    command mixins — so it adds no pydantic fields.
    """

    REGISTER_GETTER: ClassVar[type[RegisterGetter]]

    @classmethod
    def precision_of(cls, name: str) -> int | None:
        """Decimal places for ``name`` per its register scaling (None if non-numeric/unknown).

        Precision is model-specific: the same attribute may scale differently
        across models (e.g. ``i_battery`` is centivolts on single-phase but
        decivolts on three-phase), so always query the concrete model.
        """
        return cls.REGISTER_GETTER.precision_of(name)


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
