from dataclasses import dataclass
from typing import Any, Callable, Union

from pydantic.utils import GetterDict

from givenergy_modbus.model import TimeSlot
from givenergy_modbus.model.register import Register


class DataType:
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
    def timeslot(start_time: int, end_time: int) -> TimeSlot:
        """Interpret register as a time slot."""
        if start_time is not None and end_time is not None:
            return TimeSlot.from_repr(start_time, end_time)

    @staticmethod
    def bool(val: int) -> bool:
        """Interpret register as a bool."""
        if val is not None:
            return bool(val)

    @staticmethod
    def string(*vals: int) -> str:
        """Represent one or more registers as a concatenated string."""
        if vals is not None and None not in vals:
            return b''.join((v or 0).to_bytes(2, byteorder='big') for v in vals).decode(encoding='latin1').upper()
        return ''

    @staticmethod
    def hex(val: int, width: int = 4) -> str:
        """Represent a register value as a 4-character hex string."""
        if val is not None:
            return f'{val:0{width}x}'


@dataclass(init=False)
class RegisterDefinition:
    """Specifies how to convert raw register values into their actual representation."""

    pre_conv: Union[Callable, tuple, None]
    post_conv: Union[Callable, tuple[Callable, Any], None]
    registers: tuple[Register]

    def __init__(self, *args, **kwargs):
        self.pre_conv = args[0]
        self.post_conv = args[1]
        self.registers = args[2:]  # type: ignore[assignment]

    def __hash__(self):
        return hash(self.registers)


class DeviceRegisterGetter(GetterDict):
    """Specifies how device attributes are derived from raw register values."""

    REGISTER_LUT: dict[str, RegisterDefinition]

    def get(self, key: str, default: Any = None) -> Any:
        """Return a named register's value, after pre- and post-conversion."""
        try:
            r = self.REGISTER_LUT[key]
        except KeyError:
            return default

        regs = [self._obj.get(r) for r in r.registers]

        if None in regs:
            return None

        if r.pre_conv:
            if isinstance(r.pre_conv, tuple):
                args = regs + list(r.pre_conv[1:])
                val = r.pre_conv[0](*args)
            else:
                val = r.pre_conv(*regs)
        else:
            val = regs

        if r.post_conv:
            if isinstance(r.post_conv, tuple):
                return r.post_conv[0](val, *r.post_conv[1:])
            else:
                return r.post_conv(val)
        return val

    @classmethod
    def to_fields(cls) -> dict[str, tuple[Any, None]]:
        """Determine a pydantic fields definition for the class."""

        def infer_return_type(obj: Any):
            if hasattr(obj, '__annotations__') and (ret := obj.__annotations__.get('return', None)):
                return ret
            return obj  # assume it is a class/type already?

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

        register_fields = {k: (return_type(v), None) for k, v in cls.REGISTER_LUT.items()}

        return register_fields
