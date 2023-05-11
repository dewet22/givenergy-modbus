class Register:
    """Register base class."""

    TYPE_HOLDING = 'HR'
    TYPE_INPUT = 'IR'
    type: str
    idx: int

    def __str__(self):
        return '%s(%d)' % (self.type, int(self.idx))

    def __repr__(self):
        return '%s(%d)' % (self.type, int(self.idx))

    def __eq__(self, other):
        return self.type == other.type and self.idx == other.idx

    def __hash__(self):
        return hash((self.type, self.idx))

    def __init__(self, idx):
        self.idx = idx


class HR(Register):
    """Holding Register."""

    type = Register.TYPE_HOLDING


class IR(Register):
    """Input Register."""

    type = Register.TYPE_INPUT
