from typing import List

from pydantic import BaseModel, PrivateAttr

from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import Inverter  # type: ignore  # shut up mypy
from givenergy_modbus.model.register_cache import RegisterCache


class Plant(BaseModel):
    """Representation of a complete GivEnergy plant."""

    _inverter_rc: RegisterCache = PrivateAttr()
    _batteries_rcs: List[RegisterCache] = PrivateAttr()

    inverter: Inverter = None
    batteries: List[Battery] = []

    class Config:  # noqa: D106
        arbitrary_types_allowed = True
        # allow_mutation = False

    def __init__(self, batteries: int = 1, **data):
        super().__init__(**data)
        self._inverter_rc = RegisterCache()
        self._batteries_rcs = [RegisterCache() for _ in range(batteries)]

    def refresh(self):
        """Refresh the represented models from internal caches."""
        self.inverter = Inverter.from_orm(self._inverter_rc)
        self.batteries = [Battery.from_orm(rc) for rc in self._batteries_rcs]
