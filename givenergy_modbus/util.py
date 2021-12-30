import inspect
import logging
from typing import Any

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


# logging.basicConfig(handlers=[InterceptHandler()], level=0)
#
# class FriendlyClassName(type):
#     def __repr__(self):
#         return f'repr:{self}'
#
#     def __str__(self):
#         return f'str:()'


def friendly_class_name(c: Any):
    """Provides an easy way to only show the class name."""
    if inspect.isclass(c):
        return str(c)[8:-2].rsplit(".", maxsplit=1)[-1]
    return friendly_class_name(c.__class__)  # + f'({vars(c)})'


def hexxed(val):
    """Provides an easy way to print hex values when you might not always have ints."""
    if isinstance(val, int):
        return f'0x{val:04x}'
    return val
