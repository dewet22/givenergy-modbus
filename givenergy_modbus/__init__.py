"""Top-level package for GivEnergy Modbus."""

__author__ = """Dewet Diener"""
__email__ = 'givenergy-modbus@dewet.org'
__version__ = '0.1.0'


import logging

from loguru import logger


class InterceptHandler(logging.Handler):
    """Install loguru by intercepting built-in logging."""

    def emit(self, record):
        """Redirect logging emissions to loguru instead."""
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


logging.basicConfig(handlers=[InterceptHandler()], level=0)
