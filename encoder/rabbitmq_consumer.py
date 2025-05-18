"""
Consumer; establishes a robust async connection to a RabbitMQ exchange
and queue, consuming messages for processing.

Author: Mason Daugherty <@mdrxy>
Version: 1.0.1
Last Modified: 2025-04-15

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
    - 1.0.1 (2025-04-15): Use env var for queue binding key.
"""

import aio_pika
from aio_pika import ExchangeType
from config import (
    PREVIEW_EXCHANGE,
    QUEUE_BINDING_KEY,
    RABBITMQ_EXCHANGE,
    RABBITMQ_HOST,
    RABBITMQ_PASS,
    RABBITMQ_QUEUE,
    RABBITMQ_USER,
)
from message_handler import on_message
from smartgen import SmartGenConnectionManager
from utils.logging import configure_logging

logger = configure_logging(__name__)


async def consume_rabbitmq(smartgen_mgr: SmartGenConnectionManager):
    """
    Connects to RabbitMQ and consumes messages.
    """
    if RABBITMQ_HOST is None or RABBITMQ_USER is None or RABBITMQ_PASS is None:
        raise ValueError("RabbitMQ connection parameters must not be None.")

    connection = await aio_pika.connect_robust(
        host=str(RABBITMQ_HOST), login=str(RABBITMQ_USER), password=str(RABBITMQ_PASS)
    )

    # 1) Create a channel and ensure the exchange is declared
    channel = await connection.channel()
    if RABBITMQ_EXCHANGE is None:
        raise ValueError("RABBITMQ_EXCHANGE must not be None.")
    await channel.declare_exchange(RABBITMQ_EXCHANGE, ExchangeType.TOPIC, durable=True)

    # 2) Ensure the queue is declared and bound to the exchange
    queue = await channel.declare_queue(RABBITMQ_QUEUE, durable=True)
    await queue.bind(RABBITMQ_EXCHANGE, routing_key=QUEUE_BINDING_KEY)

    # Declare the preview exchange
    if PREVIEW_EXCHANGE is None:
        raise ValueError("PREVIEW_EXCHANGE must not be None.")
    preview_exchange = await channel.declare_exchange(
        PREVIEW_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
    )

    logger.info("Waiting for messages in queue `%s`...", RABBITMQ_QUEUE)
    await queue.consume(
        lambda msg: on_message(msg, smartgen_mgr, channel, preview_exchange)
    )

    return connection
