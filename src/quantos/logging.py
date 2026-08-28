"""Structured logging setup using loguru."""

import sys
from loguru import logger
from quantos.config import get_config

def setup_logging():
    config = get_config()
    logger.remove()
    logger.add(
        sys.stdout,
        format=config.logging.format,
        level=config.logging.level,
        colorize=True,
    )
    logger.add(
        "logs/quantos.log",
        rotation=config.logging.rotation,
        retention=config.logging.retention,
        format=config.logging.format,
        level=config.logging.level,
    )
    return logger