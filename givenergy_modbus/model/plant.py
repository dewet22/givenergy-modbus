from typing import Sequence

from givenergy_modbus.model import GivEnergyBaseModel
from givenergy_modbus.model.battery import Battery
from givenergy_modbus.model.inverter import Inverter  # type: ignore  # shut up mypy


class Plant(GivEnergyBaseModel):
    """Representation of a complete GivEnergy plant."""

    inverter: Inverter
    batteries: Sequence[Battery]
    # solar_pv: SolarPV
