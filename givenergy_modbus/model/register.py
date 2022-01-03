# noqa: E222
from enum import Enum, auto


class Type(Enum):
    """Type of data register represents."""

    BOOL = auto()
    WORD = auto()  # unsigned single word
    DWORD_HIGH = auto()  # unsigned double word, higher (MSB) address half
    DWORD_LOW = auto()  # unsigned double word, lower (LSB) address half
    SWORD = auto()  # signed single word
    ASCII = auto()

    def render(self, value: int, scaling: float):
        """Convert val to its true representation as determined by the register definition."""
        if self == self.DWORD_HIGH:
            # shift MSB half of the word left by 4 bytes
            return (value << 16) * scaling

        if self == self.SWORD:
            # Subtract 2^n if bit n-1 is set:
            if value & (1 << (16 - 1)):
                value -= 1 << 16
            return value * scaling

        if self == self.ASCII:
            return value.to_bytes(2, byteorder='big').decode(encoding='ascii')

        if self == self.BOOL:  # TODO is this the correct assumption?
            return bool(value & 0x0001)

        # only unsigned WORD left
        return value * scaling


class Scaling(Enum):
    """What scaling factor needs to be applied to a register's value."""

    # KILO = 1000
    # HECTO = 100
    # DECA = 10
    UNIT = 1
    DECI = 0.1
    CENTI = 0.01
    MILLI = 0.001


class Unit(Enum):
    """Measurement unit for the register value."""

    ENERGY_KWH = auto()
    POWER_W = auto()
    FREQUENCY_HZ = auto()
    VOLTAGE_V = auto()
    CURRENT_A = auto()
