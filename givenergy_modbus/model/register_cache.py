import json
import logging
from json import JSONEncoder
from typing import Any, Dict, List, Mapping

from givenergy_modbus.exceptions import ExceptionBase
from givenergy_modbus.model.register import HoldingRegister, InputRegister, Register, RegisterError

_logger = logging.getLogger(__name__)


class RegisterCacheUpdateFailed(ExceptionBase):
    """Exception raised when a register cache rejects an update due to invalid registers."""

    def __init__(self, errors: List[RegisterError]) -> None:
        self.errors = errors
        super().__init__(f'{len(errors)} invalid values ({", ".join([str(e) for e in errors])})')


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


class RegisterCache(Dict[Register, int]):
    """Holds a cache of Registers populated after querying a device."""

    _register_lookup_table: Dict[str, Register]

    def __init__(self, registers=None) -> None:
        if registers is None:
            registers = {}
        super().__init__(registers)
        self._register_lookup_table = {}
        self._register_lookup_table.update(InputRegister._member_map_)  # type: ignore[arg-type]
        self._register_lookup_table.update(HoldingRegister._member_map_)  # type: ignore[arg-type]

    def __getattr__(self, item: str):
        """Magic attributes that try to look up and convert register values."""
        item_upper = item.upper()
        if item_upper in self._register_lookup_table:
            register = self._register_lookup_table[item_upper]
            val = self[register]
            return register.convert(val)
        elif item_upper + '_H' in self._register_lookup_table and item_upper + '_L' in self._register_lookup_table:
            register_h = self._register_lookup_table[item_upper + '_H']
            register_l = self._register_lookup_table[item_upper + '_L']
            val_h = self[register_h] << 16
            val_l = self[register_l]
            return register_l.convert(val_h + val_l)
        raise KeyError(item)

    def update_with_validate(self, m: Mapping[Register, int]) -> None:
        """Given a Map of registers and values, validate before applying a bulk update."""
        errors = []
        for register, value in m.items():
            try:
                register.convert(value)
            except RegisterError as e:
                errors.append(e)
        if errors:
            raise RegisterCacheUpdateFailed(errors)
        super().update(m)

    def json(self) -> str:
        """Return JSON representation of the register cache, suitable for using with `from_json()`."""  # noqa: D402
        return json.dumps(self, cls=RegisterCacheEncoder)

    @classmethod
    def from_json(cls, data: str) -> 'RegisterCache':
        """Instantiate a RegisterCache from its JSON form."""

        def register_object_hook(object_dict: Dict[str, int]) -> Dict[Register, int]:
            """Rewrite the parsed object to have Register instances as keys instead of their (string) repr."""
            lookup = {
                'HR': HoldingRegister,
                'IR': InputRegister,
                'HoldingRegister': HoldingRegister,
                'InputRegister': InputRegister,
            }
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

    def debug(self):
        """Dump the internal state of registers and their value representations."""
        class_name = ''

        for r, v in self.items():
            if class_name != r.__class__.__name__:
                class_name = r.__class__.__name__
                print('### ' + class_name + ' ' + '#' * 100)
            print(
                f'{r} {r.name:>35}: {r.repr(v):20}  |  '
                f'{r.data_type.name:15}  {r.scaling_factor.name:5}  0x{v:04x}  {v:10}'
            )
