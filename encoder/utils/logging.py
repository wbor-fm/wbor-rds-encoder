"""
Logging module.
"""

import logging
from datetime import datetime, timezone
import os

import pytz
from colorlog import ColoredFormatter


def configure_logging(logger_name: str = "wbor_rds_encoder") -> logging.Logger:
    """Set up logging with colorized output and timestamps in Eastern Time.

    Args:
        logger_name: The name of the logger to configure.

    Returns:
        The configured logger instance.
    """
    logger = logging.getLogger(logger_name)
    if logger.hasHandlers():
        # Avoid re-adding handlers if the logger is already configured
        return logger

    log_level_str = os.getenv("LOG_LEVEL", "DEBUG").upper()
    log_level = getattr(logging, log_level_str, logging.DEBUG)
    logger.setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    class EasternTimeFormatter(ColoredFormatter):
        """Custom log formatter for Eastern Time timestamps with colorized output."""

        def formatTime(self, record, datefmt=None) -> str:
            # Convert UTC to Eastern Time
            eastern = pytz.timezone("America/New_York")
            utc_dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
            eastern_dt = utc_dt.astimezone(eastern)
            # Use ISO 8601 format
            return eastern_dt.isoformat()

    # Define the formatter with color and PID
    formatter = EasternTimeFormatter(
        "%(log_color)s%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        log_colors={
            "DEBUG": "white",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
