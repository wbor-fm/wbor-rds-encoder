"""
Logging module.
"""

import logging
from datetime import datetime, timezone
from colorlog import ColoredFormatter
import pytz


def configure_logging(logger_name="wbor_rds_encoder"):
    """
    Set up logging with colorized output and timestamps in Eastern Time.
    """
    logger = logging.getLogger(logger_name)
    if logger.hasHandlers():
        # Avoid re-adding handlers if the logger is already configured
        return logger

    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    class EasternTimeFormatter(ColoredFormatter):
        """Custom log formatter to display timestamps in Eastern Time with colorized output"""

        def formatTime(self, record, datefmt=None):
            # Convert UTC to Eastern Time
            eastern = pytz.timezone("America/New_York")
            utc_dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
            eastern_dt = utc_dt.astimezone(eastern)
            # Use ISO 8601 format
            return eastern_dt.isoformat()

    # Define the formatter with color and PID
    formatter = EasternTimeFormatter(
        "%(log_color)s%(asctime)s - PID %(process)d - %(name)s - %(levelname)s - %(message)s",
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
