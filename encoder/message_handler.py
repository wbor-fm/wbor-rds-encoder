"""
Handles incoming spin messages and sends commands to the RDS encoder.
After parsing metadata from the message, prep and send commands.

Author: Mason Daugherty <@mdrxy>
Version: 1.1.0
Last Modified: 2025-04-16

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
    - 1.0.1 (2025-04-16): Refactor to improve readability and
        maintainability. Re-queue messages on recoverable errors.
    - 1.1.0 (2025-04-16): Improved RT+ tagging logic using elipsis
        for truncated fields.
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

    Parameters:
    - raw_payload (str): The raw JSON payload string.

    Returns:
    - tuple: A tuple containing the artist, title, and duration in
        seconds.
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

    Parameters:
    - artist (str): The artist name.
    - title (str): The song title.

    Returns:
    - tuple: A tuple containing the sanitized artist and title.
    """
    sanitized_artist = await sanitize_text(artist, field_type="artist")
    sanitized_title = await sanitize_text(title, field_type="track")
    return sanitized_artist, sanitized_title


def create_text_field(artist: str, title: str) -> tuple[str, bool]:
    """
    Create and possibly truncate the TEXT field.

    Parameters:
    - artist (str): The artist name.
    - title (str): The song title.

    Returns:
    - tuple: A tuple containing the truncated text and a boolean
        indicating if truncation occurred.
    """
    text = f"{artist} - {title}"
    truncated = len(text) > 64
    truncated_text = text[:64] if truncated else text
    return truncated_text, truncated


def find_fitting_prefix(
    field: str, text: str, max_len: int, ellipsis: str = "..."
) -> str:
    """
    Helper to find the longest prefix of a field that fits within the
    truncated text. If the field is found, it returns the field with
    ellipsis. If not, it returns an empty string.

    Parameters:
    - field (str): The field to search for.
    - text (str): The text to search within.
    - max_len (int): The maximum length of the field.
    - ellipsis (str): The ellipsis to append if truncated.

    Returns:
    - str: The fitting prefix of the field or an empty string.
    """
    for i in range(max_len, 0, -1):
        candidate = field[:i]
        if candidate in text:
            return candidate + ellipsis
    return ""


def determine_rt_plus_tags(
    artist: str, title: str, truncated_text: str
) -> tuple[str, str]:
    """
    Determine RT+ tags based on what's included in the truncated text.

    If artist or title is fully present in the truncated text, return it
    as-is.

    If not, attempt to return the longest prefix of the field that is
    present in the text, appending '...' if truncated. Ensures the final
    text remains within 64 characters total.

    Examples:

    If everything fits:
        artist = "Artist Name"
        title = "Song Title"
        truncated_text = "Artist Name - Song Title"
        rt_plus_artist = "Artist Name"
        rt_plus_title = "Song Title"

    If truncation occurs:
        artist = "Very Long Artist Name"
        title = "Long Song Title"
        truncated_text = "Very Long Artist Name - Long So..."
        rt_plus_artist = "Very Long Artist Name"
        rt_plus_title = "Long So..."

    Parameters:
    - artist (str): The artist name.
    - title (str): The song title.
    - truncated_text (str): The truncated text.

    Returns:
    - tuple: A tuple containing the RT+ artist and title.
    """
    ellipsis = "..."

    # 3 is subtracted to account for the space and dash between artist
    # and title (` - `)
    if artist in truncated_text:
        rt_plus_artist = artist
    else:
        max_artist_len = max(0, 64 - len(title) - len(ellipsis) - 3)
        rt_plus_artist = find_fitting_prefix(artist, truncated_text, max_artist_len)

    if title in truncated_text:
        rt_plus_title = title
    else:
        max_title_len = max(0, 64 - len(rt_plus_artist) - len(ellipsis) - 3)
        rt_plus_title = find_fitting_prefix(title, truncated_text, max_title_len)

    return rt_plus_artist, rt_plus_title


async def send_to_encoder(
    smartgen_mgr: SmartGenConnectionManager,
    truncated_text: str,
    rt_plus_artist: str,
    rt_plus_title: str,
    duration_seconds: int,
) -> None:
    """
    Send metadata commands to SmartGen Encoder.

    Parameters:
    - smartgen_mgr (SmartGenConnectionManager): The SmartGen connection
        manager.
    - truncated_text (str): The truncated text to send.
    - rt_plus_artist (str): The RT+ artist name.
    - rt_plus_title (str): The RT+ title name.
    - duration_seconds (int): The duration of the track in seconds.
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
) -> None:
    """
    Handle incoming messages from RabbitMQ, extracting track metadata
    and sending commands to the SmartGen encoder.

    On recoverable errors (e.g., network failures or encoder connection
    problems), the message is re-queued. Non-recoverable errors (e.g.,
    JSON errors, missing payload fields) are logged but not re-queued.

    Parameters:
    - message (aio_pika.IncomingMessage): The incoming RabbitMQ
        message.
    - smartgen_mgr (SmartGenConnectionManager): The SmartGen
        connection manager.
    - _channel (aio_pika.Channel): The RabbitMQ channel.
    - _preview_exchange (aio_pika.Exchange): The preview exchange.
    """
    async with message.process():
        raw_payload = None
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
