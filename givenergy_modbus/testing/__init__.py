"""Test/diagnostic helpers for exercising clients against a faithful GivEnergy plant.

`MockPlant` is a TCP server that seeds per-device register state from a recorded wire
capture and serves synthesized, correct-CRC responses to register reads — so this
library's `Client`, GivTCP, or the vendor app can be driven end-to-end without hardware.

`sentinel_devices`, `identify`, and `Candidate` support register cross-correlation:
seed a MockPlant with sentinel values (raw = register address), read displayed values
off the app's Read Only tab, and invert the converter to identify which register backs
each label.
"""

from givenergy_modbus.testing.identify import Candidate, SentinelSpec, identify, sentinel_devices
from givenergy_modbus.testing.mock_plant import MockPlant, plant_from_capture

__all__ = [
    "Candidate",
    "MockPlant",
    "SentinelSpec",
    "identify",
    "plant_from_capture",
    "sentinel_devices",
]
