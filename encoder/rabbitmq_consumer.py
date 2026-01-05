"""
Consumer; establishes a robust async connection to a RabbitMQ exchange
and queue, consuming messages for processing.
"""

import asyncio
import socket
from contextlib import suppress
from typing import TYPE_CHECKING, Optional, cast

import aio_pika
from aio_pika import ExchangeType, IncomingMessage
from aio_pika import exceptions as aio_pika_exceptions
from aio_pika.abc import AbstractRobustChannel, AbstractRobustConnection
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


# This is for type hinting the sender argument in the callback
if TYPE_CHECKING:
    pass


async def consume_rabbitmq(  # pylint: disable=too-many-branches, too-many-locals, too-many-statements
    smartgen_mgr: SmartGenConnectionManager, shutdown_event: asyncio.Event
) -> Optional[AbstractRobustConnection]:
    """Connect to RabbitMQ and consume messages.

    The connection will attempt to reconnect robustly. If a `shutdown_event` is set, it
    will try to terminate gracefully.

    Args:
        smartgen_mgr: The SmartGen connection manager.
        shutdown_event: An event to signal shutdown.

    Returns:
        The RabbitMQ connection object if successful, or `None` if shutdown occurs
            before connection.

    Raises:
        ValueError: If RabbitMQ connection parameters are `None`.
    """
    if RABBITMQ_HOST is None or RABBITMQ_USER is None or RABBITMQ_PASS is None:
        raise ValueError("RabbitMQ connection parameters must not be None.")

    if RABBITMQ_EXCHANGE is None:
        raise ValueError("RABBITMQ_EXCHANGE must not be None.")

    # PREVIEW_EXCHANGE is optional, so not checked here strictly.

    connection: AbstractRobustConnection | None = None
    connect_retry_delay = 5  # seconds
    max_connect_retry_delay = 60  # seconds

    def on_rabbitmq_reconnect(sender: Optional[AbstractRobustConnection]):
        """Log callback for when the connection is re-established.

        Args:
            sender: The connection instance that reconnected, or `None` if not provided.
        """
        if sender:
            host_info = "N/A"

            # Safely get the `url` attribute using getattr since Pylance isn't finding it
            connection_url = getattr(sender, "url", None)

            if connection_url:
                # connection_url should be a yarl.URL object
                # Safely get the 'host' attribute from the URL object
                host_attr = getattr(connection_url, "host", None)
                if host_attr is not None:  # Check if host is not None
                    host_info = str(host_attr)  # Ensure it's a string
                else:
                    host_info = "HOST_NOT_IN_URL"
            else:
                host_info = "URL_ATTRIBUTE_MISSING_OR_NONE"

            logger.info(
                "Successfully reconnected to RabbitMQ at %s. Connection: %r",
                host_info,
                sender,
            )
        else:
            logger.warning(
                "RabbitMQ reconnection event triggered, but sender information was None."
            )

    while not shutdown_event.is_set():
        try:
            logger.info("Attempting to connect to RabbitMQ at `%s`...", RABBITMQ_HOST)
            connection = await asyncio.wait_for(
                aio_pika.connect_robust(
                    host=RABBITMQ_HOST,
                    login=RABBITMQ_USER,
                    password=RABBITMQ_PASS,
                    client_properties={"connection_name": "wbor-rds-encoder-consumer"},
                    # Heartbeat to detect dead connections sooner from client side
                    heartbeat=60,
                ),
                timeout=30,  # 30 second connection timeout
            )
            logger.info("Successfully connected to RabbitMQ.")
            connect_retry_delay = 5  # Reset retry delay on success

            if connection:
                connection.reconnect_callbacks.add(on_rabbitmq_reconnect)

            async with connection:
                async with connection.channel() as channel:
                    # `channel` is now an instance of RobustChannel

                    channel = cast(AbstractRobustChannel, channel)
                    logger.debug("RabbitMQ channel opened.")

                    def on_channel_closed_callback(
                        _sender, exc: Optional[BaseException]
                    ):
                        if exc:
                            logger.error(
                                "RobustChannel was closed with error: %s",
                                exc,
                                exc_info=exc,
                            )
                        else:
                            logger.info("RobustChannel was closed.")

                    channel.close_callbacks.add(on_channel_closed_callback)

                    await channel.declare_exchange(
                        RABBITMQ_EXCHANGE, ExchangeType.TOPIC, durable=True
                    )
                    logger.debug("Exchange `%s` ensured/declared.", RABBITMQ_EXCHANGE)

                    queue = await channel.declare_queue(RABBITMQ_QUEUE, durable=True)
                    logger.debug("Queue `%s` ensured/declared.", RABBITMQ_QUEUE)
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
                        logger.debug(
                            "Preview exchange `%s` ensured/declared.", PREVIEW_EXCHANGE
                        )
                    else:
                        logger.debug(
                            "Preview exchange not configured, skipping declaration."
                        )

                    logger.info("Waiting for messages in queue `%s`...", RABBITMQ_QUEUE)
                    consumer_tag = await queue.consume(
                        lambda msg: on_message(
                            cast(IncomingMessage, msg),
                            smartgen_mgr,
                            preview_exchange_obj,
                        )
                    )
                    logger.info(
                        "RabbitMQ consumer started with tag `%s` & listening.",
                        consumer_tag,
                    )

                    # Wait for either the connection to close or a shutdown signal
                    conn_closed_future: asyncio.Future = cast(
                        asyncio.Future, connection.closed()
                    )
                    event_wait_task: asyncio.Task[bool] = asyncio.create_task(
                        shutdown_event.wait()
                    )  # Explicit type for event_wait_task

                    logger.debug("Waiting for connection close or shutdown event...")
                    _done, pending = await asyncio.wait(
                        {conn_closed_future, event_wait_task},
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
                                    "Error cancelling consumer `%s`: `%s`",
                                    consumer_tag,
                                    e,
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
