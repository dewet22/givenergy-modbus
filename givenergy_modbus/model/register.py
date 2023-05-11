from json import JSONEncoder
from typing import Any


class RegisterEncoder(JSONEncoder):
    """Custom JSONEncoder to work around Register behaviour.

    This is a workaround to force registers to render themselves as strings instead of
    relying on the internal identity by default.
    """

    def default(self, o: Any) -> str:
        """Custom JSON encoder to treat RegisterCaches specially."""
        if isinstance(o, Register):
            return f'{o._type}_{o._idx}'
        else:
            return super().default(o)


class Register:
    """Register base class."""

    TYPE_HOLDING = 'HR'
    TYPE_INPUT = 'IR'

    _type: str
    _idx: int

    def __init__(self, idx):
        self._idx = idx

    def __str__(self):
        return '%s_%d' % (self._type, int(self._idx))

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
