"""
Handles incoming spin messages and sends commands to the RDS encoder.
After parsing metadata from the message, prep and send commands.

Author: Mason Daugherty <@mdrxy>
Version: 1.0.0
Last Modified: 2025-03-23

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
"""

import json
import socket

import aio_pika
from smartgen import SmartGenConnectionManager
from utils.logging import configure_logging
from utils.rt_plus import build_rt_plus_tag_command
from utils.sanitization import sanitize_text

logger = configure_logging(__name__)


async def on_message(
    message: aio_pika.IncomingMessage,
    smartgen_mgr: SmartGenConnectionManager,
    _channel: aio_pika.Channel,
    _preview_exchange: aio_pika.Exchange,
):
    """
    Handle incoming messages from RabbitMQ, extracting track metadata
    and sending commands to the SmartGen encoder.
    """
    async with message.process():
        try:
            raw_payload = message.body.decode("utf-8")
            logger.debug("Received track payload: `%s`", raw_payload)

            # Parse and validate JSON
            track_info = json.loads(raw_payload)
            artist = track_info.get("artist")
            title = track_info.get("song")
            duration_seconds = track_info.get("duration", 0)

            if not artist or not title:
                # TODO: test this
                logger.critical("Missing track info in payload")
                raise ValueError("Missing track info in payload")

            logger.debug("Extracted track info: `%s` - `%s`", artist, title)

            # (1) Sanitize (unidecode, filter profanity, truncate, uppercase)
            sanitized_artist = await sanitize_text(artist, field_type="artist")
            sanitized_title = await sanitize_text(title, field_type="track")
            logger.debug(
                "Returned sanitized track info: `%s` - `%s`",
                sanitized_artist,
                sanitized_title,
            )

            # (2) Create a TEXT value
            text = f"{sanitized_artist} - {sanitized_title}"
            logger.debug("TEXT value: `%s`", text)
            truncated = len(text) > 64
            truncated_text = text[:64] if truncated else text
            if truncated:
                logger.warning("TEXT value exceeds 64 characters: `%s`", text)
                logger.debug("Truncated TEXT value: `%s`", truncated_text)

            # (3) Determine RT+ tagging
            artist_in_truncated = sanitized_artist in truncated_text
            title_in_truncated = sanitized_title in truncated_text

            # Only tag fields that fully fit
            # TODO: first n characters that fit instead of empty tag
            rt_plus_artist = sanitized_artist if artist_in_truncated else ""
            rt_plus_title = sanitized_title if title_in_truncated else ""

            # (4) Send Commands to SmartGen Encoder. At this point, we
            #   know that the track info is sanitized (unidecode) safe
            #   to broadcast (profanity filtered), and truncated to fit
            #   within the SmartGen `TEXT=` character limit.
            try:
                smartgen_mgr.send_command("TEXT", truncated_text)

                rt_plus_payload = build_rt_plus_tag_command(
                    truncated_text,
                    rt_plus_artist,
                    rt_plus_title,
                    duration_seconds // 60,  # convert to minutes
                )
                if not rt_plus_payload:
                    logger.critical("Failed to build RT+TAG payload")
                else:
                    smartgen_mgr.send_command("RT+TAG", rt_plus_payload, truncated_text)

                    # Publish to the preview queue
            except (ConnectionError, RuntimeError, socket.error) as e:
                # TODO: decide if we should requeue the message (e.g., network failure)
                raise aio_pika.exceptions.AMQPError("Failed to send to encoder") from e
        except json.JSONDecodeError:
            logger.critical("Failed to parse JSON from payload: `%s`", raw_payload)
        except ValueError as e:
            logger.critical("Invalid track info: `%s`", e)
        except (aio_pika.exceptions.AMQPError, socket.error, RuntimeError) as e:
            logger.exception("Error processing message: `%s`", e)
