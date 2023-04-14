import json
import logging
from json import JSONEncoder
from typing import Any, DefaultDict, Optional

from givenergy_modbus.exceptions import ExceptionBase
from givenergy_modbus.model.register import HoldingRegister, InputRegister, Register, RegisterError

_logger = logging.getLogger(__name__)


class RegisterCacheUpdateFailed(ExceptionBase):
    """Exception raised when a register cache rejects an update due to invalid registers."""

    def __init__(self, errors: list[RegisterError]) -> None:
        self.errors = errors
        super().__init__(f'{len(errors)} invalid values ({", ".join([str(e) for e in errors])})')


class RegisterCache(DefaultDict[Register, int]):
    """Holds a cache of Registers populated after querying a device."""

    def __init__(self, registers: Optional[dict[Register, int]] = None) -> None:
        if registers is None:
            registers = {}
        super().__init__(lambda: 0, registers)

    def json(self) -> str:
        """Return JSON representation of the register cache, suitable for using with `from_json()`."""  # noqa: D402,D202,E501

        class RegisterCacheEncoder(JSONEncoder):
            """Custom JSONEncoder to work around Register behaviour.

            This is a workaround to force register keys to render themselves as strings instead of
            relying on the internal identity by default (due to the Register Enum extending str).
            """

            def encode(self, o: Any) -> str:
                """Custom JSON encoder to treat RegisterCaches specially."""
                if isinstance(o, RegisterCache):
                    return super().encode({str(k): v for k, v in o.items()})
                else:
                    return super().encode(o)

        return json.dumps(self, cls=RegisterCacheEncoder)

    @classmethod
    def from_json(cls, data: str) -> 'RegisterCache':
        """Instantiate a RegisterCache from its JSON form."""

        def register_object_hook(object_dict: dict[str, int]) -> dict[Register, int]:
            """Rewrite the parsed object to have Register instances as keys instead of their (string) repr."""
            lookup = {'HR': HoldingRegister, 'IR': InputRegister}
            ret = {}
            for k, v in object_dict.items():
                if k.find('(') > 0:
                    reg, idx = k.split('(', maxsplit=1)
                    ret[lookup[reg](int(idx[:-1]))] = v
                elif k.find(':') > 0:
                    reg, idx = k.split(':', maxsplit=1)
                    ret[lookup[reg](int(idx))] = v
                else:
                    raise ValueError(f'{k} is not a valid Register type')
            return ret

        return cls(registers=(json.loads(data, object_hook=register_object_hook)))

    # helper methods to convert register data types

    def to_string(self, *registers: Register) -> str:
        """Combine registers into an ASCII string."""
        values = [self[r] for r in registers]
        if all(values):
            return ''.join(v.to_bytes(2, byteorder='big').decode(encoding='latin1') for v in values)
        return ''

    def to_hex_string(self, *registers: Register) -> str:
        """Render a register as a 2-byte hexadecimal value."""
        ret = ''
        for r in registers:
            ret += f'{self[r]:04x}'
        return ''.join(filter(str.isalnum, ret)).upper()

    def to_duint8(self, *registers: Register) -> tuple[int, ...]:
        """Split registers into two unsigned 8-bit integers each."""
        return sum(((self[r] >> 8, self[r] & 0xFF) for r in registers), ())

    def to_uint32(self, high_register: Register, low_register: Register) -> int:
        """Combine two registers into an unsigned 32-bit integer."""
        return (self[high_register] << 16) + self[low_register]
