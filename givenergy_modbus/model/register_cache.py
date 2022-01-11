from .register import HoldingRegister, InputRegister, Register  # type: ignore  # shut up mypy


class RegisterCache:
    """Holds a cache of Registers populated after querying a device."""

    def __init__(self) -> None:
        self._registers: dict[Register, int] = {}
        self._register_lookup_table: dict[str, Register] = {}
        for k, v in InputRegister.__members__.items():
            self._register_lookup_table[k] = v
        for k, v in HoldingRegister.__members__.items():
            self._register_lookup_table[k] = v

    def __getattr__(self, item: str):
        """Magic attributes that try to look up and convert register values."""
        item_upper = item.upper()
        if item_upper in self._register_lookup_table:
            register = self._register_lookup_table[item_upper]
            val = self._registers[register]
            return register.convert(val)
        elif item_upper + '_H' in self._register_lookup_table and item_upper + '_L' in self._register_lookup_table:
            register_h = self._register_lookup_table[item_upper + '_H']
            register_l = self._register_lookup_table[item_upper + '_L']
            val_h = self._registers[register_h] << 16
            val_l = self._registers[register_l]
            return register_l.convert(val_h + val_l)
        raise KeyError(item)

    def set_registers(self, type_: type[Register], registers: dict[int, int]):
        """Update internal holding register cache with given values."""
        for k, v in registers.items():
            self._registers[type_(k)] = v

    def debug(self):
        """Dump the internal state of registers and their value representations."""
        class_name = ''

        for r, v in self._registers.items():
            if class_name != r.__class__.__name__:
                class_name = r.__class__.__name__
                print('### ' + class_name + ' ' + '#' * 100)
            print(f'{r} {r.name:>35}: {r.repr(v):20}  |  ' f'{r.type.name:15}  {r.scaling.name:5}  0x{v:04x}  {v:10}')
