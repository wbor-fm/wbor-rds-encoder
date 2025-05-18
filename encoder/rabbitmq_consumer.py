"""
Consumer; establishes a robust async connection to a RabbitMQ exchange
and queue, consuming messages for processing.

Author: Mason Daugherty <@mdrxy>
Version: 1.0.3
Last Modified: 2025-05-17

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
    - 1.0.1 (2025-04-15): Use env var for queue binding key.
    - 1.0.2 (2025-05-17): Improved robustness, connection retry logic,
        and shutdown handling.
    - 1.0.3 (2025-05-17): Addressed Pylance/Pylint issues, refined error
        handling and optional PREVIEW_EXCHANGE check.
"""

import asyncio
import socket
from contextlib import suppress
from typing import cast

import aio_pika
from aio_pika import ExchangeType, IncomingMessage, RobustChannel, RobustExchange
from aio_pika import exceptions as aio_pika_exceptions
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


async def consume_rabbitmq(  # pylint: disable=too-many-branches, too-many-locals, too-many-statements
    smartgen_mgr: SmartGenConnectionManager, shutdown_event: asyncio.Event
):
    """
    Connects to RabbitMQ and consumes messages. The connection will
    attempt to reconnect robustly.

    If a shutdown_event is set, it should try to terminate gracefully.
    Returns the connection object if successful, or None if shutdown
    occurs before connection.

    Raises exceptions if connection attempts fail persistently.

    Parameters:
    - smartgen_mgr (SmartGenConnectionManager): The SmartGen connection
        manager.
    - shutdown_event (asyncio.Event): An event to signal shutdown.
    """
    if RABBITMQ_HOST is None or RABBITMQ_USER is None or RABBITMQ_PASS is None:
        raise ValueError("RabbitMQ connection parameters must not be None.")

    if RABBITMQ_EXCHANGE is None or PREVIEW_EXCHANGE is None:
        raise ValueError(
            "Both exchanges (RABBITMQ_EXCHANGE, PREVIEW_EXCHANGE) must not be None."
        )

    # PREVIEW_EXCHANGE is optional, so not checked here strictly.

    connection = None
    connect_retry_delay = 5  # seconds
    max_connect_retry_delay = 60  # seconds

    while not shutdown_event.is_set():
        try:
            logger.info("Attempting to connect to RabbitMQ at `%s`...", RABBITMQ_HOST)
            connection = await aio_pika.connect_robust(
                host=RABBITMQ_HOST,
                login=RABBITMQ_USER,
                password=RABBITMQ_PASS,
                client_properties={"connection_name": "wbor-rds-encoder-consumer"},
                # Add heartbeat to detect dead connections sooner from client side
                heartbeat=60,
            )
            logger.info("Successfully connected to RabbitMQ.")
            connect_retry_delay = 5  # Reset retry delay on successful connection

            async with connection:
                channel = cast(RobustChannel, await connection.channel())
                logger.info("RabbitMQ channel opened.")

                # Add callbacks for channel closure for more detailed logging
                def on_channel_closed_callback(_sender, exc):
                    if exc:
                        logger.error(
                            "RobustChannel was closed with error: %s", exc, exc_info=exc
                        )
                    else:
                        logger.info("RobustChannel was closed.")

                channel.add_on_close_callback(  # type: ignore[attr-defined]
                    on_channel_closed_callback
                )

                await channel.declare_exchange(
                    RABBITMQ_EXCHANGE, ExchangeType.TOPIC, durable=True
                )
                logger.info("Exchange `%s` declared.", RABBITMQ_EXCHANGE)

                queue = await channel.declare_queue(RABBITMQ_QUEUE, durable=True)
                logger.info("Queue `%s` declared.", RABBITMQ_QUEUE)
                await queue.bind(RABBITMQ_EXCHANGE, routing_key=QUEUE_BINDING_KEY)
                logger.info(
                    "Queue `%s` bound to exchange `%s` with key `%s`.",
                    RABBITMQ_QUEUE,
                    RABBITMQ_EXCHANGE,
                    QUEUE_BINDING_KEY,
                )

                preview_exchange_obj = None
                if PREVIEW_EXCHANGE:  # Optional: only declare if configured
                    preview_exchange_obj = await channel.declare_exchange(
                        PREVIEW_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
                    )
                    logger.info("Preview exchange `%s` declared.", PREVIEW_EXCHANGE)
                else:
                    logger.info(
                        "Preview exchange not configured, skipping declaration."
                    )

                logger.info("Waiting for messages in queue `%s`...", RABBITMQ_QUEUE)
                consumer_tag = await queue.consume(
                    lambda msg: on_message(
                        cast(IncomingMessage, msg),
                        smartgen_mgr,
                        channel,
                        cast(RobustExchange | None, preview_exchange_obj),
                    )
                )
                logger.info(
                    "Consumer started with tag `%s`. Listening for messages.",
                    consumer_tag,
                )

                # Wait for either the connection to close or a shutdown signal

                # Step 1: Ensure Pylance correctly understands connection.closed is a Future.
                conn_closed_future = cast(asyncio.Future, connection.closed)

                # Step 2: Explicitly create an asyncio.Task for the shutdown_event.wait() coroutine.
                # shutdown_event.wait() returns a coroutine. Wrapping it in a task is clearer for
                # type checking.
                event_wait_coroutine = shutdown_event.wait()
                event_wait_task = asyncio.create_task(
                    event_wait_coroutine, name="shutdown_event_wait_task"
                )

                logger.info("Waiting for connection close or shutdown event...")
                _done, pending = await asyncio.wait(
                    [
                        conn_closed_future,
                        event_wait_task,
                    ],  # Pass the Future and the explicit Task
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks to avoid issues on exit
                for task in pending:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task

                if shutdown_event.is_set():
                    logger.info("Shutdown event received, stopping consumer.")
                    if (
                        channel and not channel.is_closed
                    ):  # Added channel existence check
                        try:
                            await queue.cancel(consumer_tag)
                            logger.info("Consumer `%s` cancelled.", consumer_tag)
                        except aio_pika_exceptions.ChannelInvalidStateError:
                            logger.warning(
                                "Channel in invalid state when trying to cancel consumer `%s`.",
                                consumer_tag,
                            )
                        except aio_pika_exceptions.ChannelClosed:
                            logger.warning(
                                "Channel already closed when trying to cancel consumer `%s`.",
                                consumer_tag,
                            )
                        except Exception as e:  # pylint: disable=broad-except
                            logger.error(
                                "Error cancelling consumer `%s`: `%s`", consumer_tag, e
                            )
                    return connection

                if connection.is_closed:
                    # Assert to Pylance that connection.closed is an asyncio.Future
                    closed_future = cast(asyncio.Future, connection.closed)
                    closed_exc = closed_future.exception()
                    if closed_exc:
                        logger.error(
                            "RabbitMQ connection lost: %s",
                            closed_exc,
                            exc_info=closed_exc,
                        )
                        raise closed_exc
                    logger.warning(
                        "RabbitMQ connection closed without a specific exception (likely "
                        "broker shutdown)."
                    )
                    raise aio_pika_exceptions.AMQPConnectionError(
                        "Connection closed by broker (shutdown) and connect_robust could not "
                        "maintain it."
                    )

        except (
            aio_pika_exceptions.AMQPConnectionError,
            ConnectionRefusedError,
            socket.gaierror,
            asyncio.TimeoutError,
            OSError,  # For [Errno 111] etc.
        ) as e:
            logger.error(
                "RabbitMQ connection/setup error: %s. Retrying in %ss.",
                e,
                connect_retry_delay,
            )
            if connection and not connection.is_closed:
                try:
                    await connection.close()
                except Exception as close_exc:  # pylint: disable=broad-except
                    logger.error(
                        "Error closing RabbitMQ connection during error handling: %s",
                        close_exc,
                    )
            connection = None
            if shutdown_event.is_set():
                logger.info(
                    "Shutdown initiated, aborting RabbitMQ connection attempts."
                )
                return None

            try:
                await asyncio.sleep(connect_retry_delay)
            except asyncio.CancelledError:
                logger.info(
                    "Shutdown initiated during sleep, aborting RabbitMQ connection attempts."
                )
                return None

            connect_retry_delay = min(connect_retry_delay * 2, max_connect_retry_delay)
        except RuntimeError as e:
            # Check if it's the specific RuntimeError from channel restoration issues
            if "closed" in str(
                e
            ).lower() and (  # make check case-insensitive for "closed"
                e.__cause__ is None
                or isinstance(
                    e.__cause__, aio_pika_exceptions.AMQPError
                )  # Allow None for __cause__
            ):
                logger.error(
                    "RuntimeError during RabbitMQ operation (likely channel restore on closed "
                    "connection): %s. Propagating for full reset.",
                    e,
                )
                raise  # Let main.py handle this by recreating everything
            else:  # Other RuntimeErrors
                logger.critical(
                    "An unexpected RuntimeError occurred in consume_rabbitmq: %s",
                    e,
                    exc_info=True,
                )
                raise  # Propagate other critical runtime errors
        except Exception as e:  # pylint: disable=broad-except
            logger.critical(
                "An unexpected critical error occurred in consume_rabbitmq: %s",
                e,
                exc_info=True,
            )
            if connection and not connection.is_closed:
                try:
                    await connection.close()
                except Exception as close_exc:  # pylint: disable=broad-except
                    logger.error(
                        "Error closing RabbitMQ connection during critical error handling: %s",
                        close_exc,
                    )
            connection = None
            raise

    logger.info("consume_rabbitmq: Shutdown event is set. Exiting consumption loop.")
    return connection
