from __future__ import annotations

import json

from givenergy_modbus.model.register import HoldingRegister, InputRegister, Register  # type: ignore  # shut up mypy
from givenergy_modbus.pdu import (
    ModbusPDU,
    ReadHoldingRegistersResponse,
    ReadInputRegistersResponse,
    ReadRegistersResponse,
    WriteHoldingRegisterResponse,
)


class RegisterCache(dict):
    """Holds a cache of Registers populated after querying a device."""

    _register_lookup_table: dict[str, Register]

    def __init__(self, slave_address: int, registers=None) -> None:
        if registers is None:
            registers = {}
        registers['slave_address'] = slave_address
        super().__init__(registers)
        self._register_lookup_table = {}
        for k, v in InputRegister.__members__.items():
            self._register_lookup_table[k] = v
        for k, v in HoldingRegister.__members__.items():
            self._register_lookup_table[k] = v

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

    def set_registers(self, register_type: type[Register], registers: dict[int, int]):
        """Update internal holding register cache with given values."""
        # loop through all incoming registers to see if any fail to convert – in that case discard entire update
        errors = []
        for k, v in registers.items():
            r = register_type(k)
            try:
                r.convert(v)
            except ValueError as e:
                errors.append(f"{r}/{r.name}:{e}")
        if errors:
            raise ValueError(f'{len(errors)} invalid {register_type.__name__} values ({", ".join(errors)})')

        for k, v in registers.items():
            self[register_type(k)] = v

    def update_from_pdu(self, pdu: ModbusPDU):
        """Update internal state directly from a PDU Response message."""
        if isinstance(pdu, ReadRegistersResponse):
            if pdu.slave_address != self['slave_address']:
                raise ValueError(f'Mismatched slave address: 0x{pdu.slave_address:02x}!=0x{self["slave_address"]:02x}')
            if isinstance(pdu, ReadHoldingRegistersResponse):
                self.set_registers(HoldingRegister, pdu.to_dict())
            elif isinstance(pdu, ReadInputRegistersResponse):
                self.set_registers(InputRegister, pdu.to_dict())
            else:
                raise ValueError(f'Cannot handle response {pdu}')
        elif isinstance(pdu, WriteHoldingRegisterResponse):
            self.set_registers(HoldingRegister, {pdu.register: pdu.value})

    def to_json(self) -> str:
        """Return JSON representation of the register cache, suitable for using with `from_json()`."""
        return json.dumps(self)

    @classmethod
    def from_json(cls, data: str) -> RegisterCache:
        """Instantiate a RegisterCache from its JSON form."""

        def register_object_hook(object_dict: dict[str, int]) -> dict[Register, int]:
            """Rewrite the parsed object to have Register instances as keys instead of their (string) repr."""
            lookup = {'HR': HoldingRegister, 'IR': InputRegister}
            ret = {}
            for k, v in object_dict.items():
                if k.find(':') > 0:
                    reg, idx = k.split(':', maxsplit=1)
                    ret[lookup[reg](int(idx))] = v
                else:
                    ret[k] = v
            return ret

        decoded_data = json.loads(data, object_hook=register_object_hook)
        return cls(int(decoded_data['slave_address']), registers=decoded_data)

    def debug(self):
        """Dump the internal state of registers and their value representations."""
        class_name = ''

        for r, v in self.items():
            if class_name != r.__class__.__name__:
                class_name = r.__class__.__name__
                print('### ' + class_name + ' ' + '#' * 100)
            print(f'{r} {r.name:>35}: {r.repr(v):20}  |  ' f'{r.type.name:15}  {r.scaling.name:5}  0x{v:04x}  {v:10}')
