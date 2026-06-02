"""Test/diagnostic helpers for exercising clients against a faithful GivEnergy plant.

`MockPlant` is a TCP server that seeds per-device register state from a recorded wire
capture and serves synthesized, correct-CRC responses to register reads — so this
library's `Client`, GivTCP, or the vendor app can be driven end-to-end without hardware.
"""

from givenergy_modbus.testing.mock_plant import MockPlant, plant_from_capture

__all__ = ["MockPlant", "plant_from_capture"]
