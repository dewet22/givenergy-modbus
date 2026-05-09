"""Top-level package for GivEnergy Modbus."""

from importlib.metadata import PackageNotFoundError, version

__author__ = """Dewet Diener"""
__email__ = "givenergy-modbus@dewet.org"
try:
    __version__ = version("givenergy-modbus")
except PackageNotFoundError:
    __version__ = "unknown"
