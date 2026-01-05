"""
Consume song metadata from a RabbitMQ queue and send it to a SmartGen
Mini RDS encoder to update Radio Data System (RDS) & RDS+ text. Performs
unidecoding (to ASCII) to ensure compatibility with the encoder and
receiver units. Includes naieve profanity filtering.
"""

import asyncio
import logging
import signal
import sys

from config import RABBITMQ_HOST, RDS_ENCODER_HOST, RDS_ENCODER_PORT
from rabbitmq_consumer import consume_rabbitmq
from smartgen import SmartGenConnectionManager
from utils.logging import configure_logging

logging.root.handlers = []
logger = configure_logging()


async def main():
    """Entry point for the application.

    Orchestrates the lifecycle of the SmartGen connection manager and the RabbitMQ
    consumer.
    """
    logger.info("wbor-rds-encoder starting up...")
    logger.info(
        "Configuration: RDS_ENCODER=%s:%s, RABBITMQ_HOST=%s",
        RDS_ENCODER_HOST,
        RDS_ENCODER_PORT,
        RABBITMQ_HOST,
    )

    shutdown_event = asyncio.Event()

    def _signal_handler():
        logger.info("Received shutdown signal.")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, _signal_handler)
    loop.add_signal_handler(signal.SIGINT, _signal_handler)

    smartgen_mgr = SmartGenConnectionManager(RDS_ENCODER_HOST, RDS_ENCODER_PORT)
    await smartgen_mgr.start()

    connection = await consume_rabbitmq(smartgen_mgr, shutdown_event)

    logger.info("Shutting down gracefully...")
    await smartgen_mgr.stop()
    # Ensure connection is not None before attempting to close,
    # as consume_rabbitmq might return None if shutdown occurs during its setup.
    if connection:
        await connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:  # pylint: disable=broad-except
        logger.exception("Application encountered an error and will exit.")
        sys.exit(1)
