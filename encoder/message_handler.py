"""
Handles incoming spin messages and sends commands to the RDS encoder.
After parsing metadata from the message, prep and send commands.

Author: Mason Daugherty <@mdrxy>
Version: 1.0.1
Last Modified: 2025-04-16

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
    - 1.0.1 (2025-04-16): Refactor to improve readability and
        maintainability. Re-queue messages on recoverable errors.
"""

import json
import socket

import aio_pika
from smartgen import SmartGenConnectionManager
from utils.logging import configure_logging
from utils.rt_plus import build_rt_plus_tag_command
from utils.sanitization import sanitize_text

logger = configure_logging(__name__)


async def parse_payload(raw_payload: str) -> tuple[str, str, int]:
    """
    Parse JSON payload and extract artist, title, duration.
    """
    track_info = json.loads(raw_payload)
    artist = track_info.get("artist")
    title = track_info.get("song")
    duration_seconds = track_info.get("duration", 0)

    if not artist or not title:
        raise ValueError("Missing track info in payload")

    return artist, title, duration_seconds


async def sanitize_metadata(artist: str, title: str) -> tuple[str, str]:
    """
    Sanitize metadata fields.
    """
    sanitized_artist = await sanitize_text(artist, field_type="artist")
    sanitized_title = await sanitize_text(title, field_type="track")
    return sanitized_artist, sanitized_title


def create_text_field(artist: str, title: str) -> tuple[str, bool]:
    """
    Create and possibly truncate the TEXT field.
    """
    text = f"{artist} - {title}"
    truncated = len(text) > 64
    truncated_text = text[:64] if truncated else text
    return truncated_text, truncated


def determine_rt_plus_tags(
    artist: str, title: str, truncated_text: str
) -> tuple[str, str]:
    """
    Determine RT+ tags based on truncation.
    """
    rt_plus_artist = artist if artist in truncated_text else ""
    rt_plus_title = title if title in truncated_text else ""

    # Only tag fields that fully fit
    # TODO: first n characters that fit instead of empty tag

    return rt_plus_artist, rt_plus_title


async def send_to_encoder(
    smartgen_mgr: SmartGenConnectionManager,
    truncated_text: str,
    rt_plus_artist: str,
    rt_plus_title: str,
    duration_seconds: int,
):
    """
    Send metadata commands to SmartGen Encoder.
    """
    smartgen_mgr.send_command("TEXT", truncated_text)

    rt_plus_payload = build_rt_plus_tag_command(
        truncated_text,
        rt_plus_artist,
        rt_plus_title,
        duration_seconds // 60,  # minutes
    )

    if not rt_plus_payload:
        raise RuntimeError("Failed to build RT+TAG payload")

    smartgen_mgr.send_command("RT+TAG", rt_plus_payload, truncated_text)


async def on_message(
    message: aio_pika.IncomingMessage,
    smartgen_mgr: SmartGenConnectionManager,
    _channel: aio_pika.Channel,
    _preview_exchange: aio_pika.Exchange,
):
    """
    Handle incoming messages from RabbitMQ, extracting track metadata
    and sending commands to the SmartGen encoder.

    On recoverable errors (e.g., network failures or encoder connection
    problems), the message is re-queued. Non-recoverable errors (e.g.,
    JSON errors, missing payload fields) are logged but not re-queued.
    """
    async with message.process():
        try:
            raw_payload = message.body.decode("utf-8")
            logger.debug("Received payload: `%s`", raw_payload)

            artist, title, duration_seconds = await parse_payload(raw_payload)
            logger.debug("Extracted track info: `%s` - `%s`", artist, title)

            # (1) Sanitize (unidecode, filter profanity, truncate, uppercase)
            sanitized_artist, sanitized_title = await sanitize_metadata(artist, title)
            logger.debug(
                "Returned sanitized track info: `%s` - `%s`",
                sanitized_artist,
                sanitized_title,
            )

            # (2) Create a TEXT value
            truncated_text, truncated = create_text_field(
                sanitized_artist, sanitized_title
            )

            if truncated:
                logger.warning("TEXT value truncated to 64 chars: `%s`", truncated_text)

            # (3) Determine RT+ tagging
            rt_plus_artist, rt_plus_title = determine_rt_plus_tags(
                sanitized_artist, sanitized_title, truncated_text
            )

            # (4) Send Commands to SmartGen Encoder. At this point, we
            #   know that the track info is sanitized (unidecode) safe
            #   to broadcast (profanity filtered), and truncated to fit
            #   within the SmartGen `TEXT=` character limit.
            await send_to_encoder(
                smartgen_mgr,
                truncated_text,
                rt_plus_artist,
                rt_plus_title,
                duration_seconds,
            )

            # TODO: publish to the preview queue

        except json.JSONDecodeError:
            logger.critical("Failed to parse JSON from payload: `%s`", raw_payload)
        except (ValueError, RuntimeError) as e:
            logger.critical("Invalid payload or processing error: `%s`", e)
        except (
            ConnectionError,
            socket.error,
            aio_pika.exceptions.AMQPError,
        ) as e:
            logger.exception("Communication error: `%s`", e)
            await message.nack(requeue=True)
