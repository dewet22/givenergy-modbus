from __future__ import annotations

import logging

from loguru import logger


class InterceptHandler(logging.Handler):
    """Install loguru by intercepting logging."""

    def emit(self, record):
        """Redirect logging emissions to loguru instead."""
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where the logged message originated, skipping frames from plumbing/infrastructure
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__ or "sentry_sdk/integrations" in frame.f_code.co_filename:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())
