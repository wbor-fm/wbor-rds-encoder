"""Handles incoming spin messages and sends commands to the RDS encoder.

After parsing metadata from the message, prep and send commands.
"""

import asyncio
import json
from dataclasses import dataclass

from aio_pika import IncomingMessage
from aio_pika.abc import AbstractRobustExchange
from smartgen import SmartGenConnectionManager
from utils.logging import configure_logging
from utils.rt_plus import build_rt_plus_tag_command
from utils.sanitization import sanitize_text

logger = configure_logging(__name__)


@dataclass
class TrackInfo:
    """Holds parsed track information."""

    artist: str
    title: str
    duration_seconds: int


class MessageProcessor:
    """Processes RabbitMQ messages and sends to SmartGen encoder.

    Only keeps the latest track info - stale messages are dropped since
    RDS only cares about what's currently playing.
    """

    def __init__(self, smartgen_mgr: SmartGenConnectionManager):
        self.smartgen_mgr = smartgen_mgr
        self._latest_track: TrackInfo | None = None
        self._lock = asyncio.Lock()
        self._processor_task: asyncio.Task | None = None
        self._new_track_event = asyncio.Event()
        self._stop = False

    async def start(self):
        """Start the background processor task."""
        self._processor_task = asyncio.create_task(self._process_loop())

    async def stop(self):
        """Stop the background processor task."""
        self._stop = True
        self._new_track_event.set()  # Wake up the loop
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

    async def handle_message(
        self,
        message: IncomingMessage,
        _preview_exchange: AbstractRobustExchange | None,
    ) -> None:
        """Handle an incoming message from RabbitMQ.

        Acks the message immediately and stores track info for processing.

        Only the latest track is kept - older tracks are discarded.

        Args:
            message: The incoming RabbitMQ message.
            _preview_exchange: The preview exchange (currently unused).
        """
        # Always ack immediately to prevent queue buildup
        try:
            await message.ack()
        except Exception as e:
            logger.warning("Failed to ack message: %s", e)
            return

        # Parse the message
        try:
            raw_payload = message.body.decode("utf-8")
            logger.debug("Received payload: `%s`", raw_payload)
            track_info = await _parse_payload(raw_payload)
        except json.JSONDecodeError:
            logger.critical("Failed to parse JSON from payload: `%s`", raw_payload)
            return
        except ValueError as e:
            logger.critical("Invalid payload: `%s`", e)
            return

        # Store as latest track (replacing any previous)
        async with self._lock:
            old_track = self._latest_track
            self._latest_track = track_info

            if old_track is not None:
                logger.debug(
                    "Replacing stale track `%s` - `%s` with `%s` - `%s`",
                    old_track.artist,
                    old_track.title,
                    track_info.artist,
                    track_info.title,
                )

        logger.info(
            "Queued for processing: `%s` - `%s`",
            track_info.artist,
            track_info.title,
        )

        # Signal the processor that there's a new track
        self._new_track_event.set()

    async def _process_loop(self):
        """Background loop that processes the latest track when SmartGen is available."""
        while not self._stop:
            # Get the latest track
            async with self._lock:
                track = self._latest_track

            if track is None:
                # No track pending - wait for a new one
                try:
                    await asyncio.wait_for(self._new_track_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass  # Periodic check
                self._new_track_event.clear()
                continue

            if self._stop:
                break

            # Clear event since we have a track to process
            self._new_track_event.clear()

            # Wait for SmartGen connection
            if not self.smartgen_mgr.is_connected:
                logger.info(
                    "Waiting for SmartGen connection before processing: `%s` - `%s`",
                    track.artist,
                    track.title,
                )
                connected = await self.smartgen_mgr.wait_for_connection(timeout=30.0)
                if not connected:
                    # Check if there's a newer track now
                    async with self._lock:
                        if self._latest_track is not track:
                            logger.info(
                                "Discarding stale track `%s` - `%s` (newer track available)",
                                track.artist,
                                track.title,
                            )
                            continue
                    # No newer track, keep waiting
                    logger.warning(
                        "SmartGen connection timeout, will retry: `%s` - `%s`",
                        track.artist,
                        track.title,
                    )
                    continue

            # Re-check that this is still the latest track before processing
            async with self._lock:
                if self._latest_track is not track:
                    logger.info(
                        "Discarding stale track `%s` - `%s` (newer track available)",
                        track.artist,
                        track.title,
                    )
                    continue
                # Clear so we don't reprocess
                self._latest_track = None

            # Process the track
            await self._process_track(track)

    async def _process_track(self, track: TrackInfo) -> None:
        """Process a single track and send to encoder.

        Args:
            track: The track information to process.
        """
        try:
            # Sanitize metadata
            sanitized_artist, sanitized_title = await _sanitize_metadata(
                track.artist, track.title
            )
            logger.debug(
                "Sanitized track info: `%s` - `%s`",
                sanitized_artist,
                sanitized_title,
            )

            # Create TEXT field
            truncated_text, truncated = _create_text_field(
                sanitized_artist, sanitized_title
            )

            if truncated:
                logger.warning("TEXT value truncated to 64 chars: `%s`", truncated_text)

            # Determine RT+ tags
            rt_plus_artist, rt_plus_title = _determine_rt_plus_tags(
                sanitized_artist, sanitized_title, truncated_text
            )

            # Send to encoder
            await _send_to_encoder(
                self.smartgen_mgr,
                truncated_text,
                rt_plus_artist,
                rt_plus_title,
                track.duration_seconds,
            )

            logger.info(
                "Successfully sent to encoder: `%s` - `%s`",
                sanitized_artist,
                sanitized_title,
            )

        except (ConnectionError, OSError, asyncio.TimeoutError) as e:
            logger.error("Failed to send to encoder: %s", e)
            # Re-queue this track for retry
            async with self._lock:
                if self._latest_track is None:
                    self._latest_track = track
                    logger.info(
                        "Re-queued track for retry: `%s` - `%s`",
                        track.artist,
                        track.title,
                    )
        except RuntimeError as e:
            logger.error("Processing error (will not retry): %s", e)


async def _parse_payload(raw_payload: str) -> TrackInfo:
    """Parse JSON payload and extract artist, title, duration.

    Args:
        raw_payload: The raw JSON payload string.

    Returns:
        A `TrackInfo` object containing the artist, title, and duration.

    Raises:
        ValueError: If artist or title is missing from the payload.
        json.JSONDecodeError: If the payload is not valid JSON.
    """
    track_data = json.loads(raw_payload)
    artist = track_data.get("artist")
    title = track_data.get("song")
    duration_seconds = track_data.get("duration", 0)

    if not artist or not title:
        raise ValueError("Missing track info in payload")

    return TrackInfo(artist=artist, title=title, duration_seconds=duration_seconds)


async def _sanitize_metadata(artist: str, title: str) -> tuple[str, str]:
    """Sanitize metadata fields.

    Args:
        artist: The artist name.
        title: The song title.

    Returns:
        A tuple containing the sanitized artist and title.
    """
    sanitized_artist = await sanitize_text(artist, field_type="artist")
    sanitized_title = await sanitize_text(title, field_type="track")
    return sanitized_artist, sanitized_title


def _create_text_field(artist: str, title: str) -> tuple[str, bool]:
    """Create and possibly truncate the `TEXT` field.

    Args:
        artist: The artist name.
        title: The song title.

    Returns:
        A tuple containing the truncated text and a boolean indicating
            if truncation occurred.
    """
    text = f"{artist} - {title}"
    truncated = len(text) > 64
    truncated_text = text[:64] if truncated else text
    return truncated_text, truncated


def _find_fitting_prefix(
    field: str, text: str, max_len: int, ellipsis: str = "..."
) -> str:
    """Find the longest prefix of a field that fits within truncated text.

    If the field is found, returns the field with ellipsis appended.

    If not found, returns an empty string.

    Args:
        field: The field to search for.
        text: The text to search within.
        max_len: The maximum length of the field.
        ellipsis: The ellipsis to append if truncated.

    Returns:
        The fitting prefix of the field or an empty string.
    """
    for i in range(max_len, 0, -1):
        candidate = field[:i]
        if candidate in text:
            return candidate + ellipsis
    return ""


def _determine_rt_plus_tags(
    artist: str, title: str, truncated_text: str
) -> tuple[str, str]:
    """Determine RT+ tags based on what's included in the truncated text.

    If artist or title is fully present in the truncated text, returns it
    as-is. If not, attempts to return the longest prefix of the field that
    is present in the text, appending `'...'` if truncated.

    Ensures the final text remains within 64 characters total.

    Args:
        artist: The artist name.
        title: The song title.
        truncated_text: The truncated text.

    Returns:
        A tuple containing the RT+ artist and title.
    """
    ellipsis = "..."

    if artist in truncated_text:
        rt_plus_artist = artist
    else:
        max_artist_len = max(0, 64 - len(title) - len(ellipsis) - 3)
        rt_plus_artist = _find_fitting_prefix(artist, truncated_text, max_artist_len)

    if title in truncated_text:
        rt_plus_title = title
    else:
        max_title_len = max(0, 64 - len(rt_plus_artist) - len(ellipsis) - 3)
        rt_plus_title = _find_fitting_prefix(title, truncated_text, max_title_len)

    return rt_plus_artist, rt_plus_title


async def _send_to_encoder(
    smartgen_mgr: SmartGenConnectionManager,
    truncated_text: str,
    rt_plus_artist: str,
    rt_plus_title: str,
    duration_seconds: int,
) -> None:
    """Send metadata commands to SmartGen Encoder.

    Args:
        smartgen_mgr: The SmartGen connection manager.
        truncated_text: The truncated text to send.
        rt_plus_artist: The RT+ artist name.
        rt_plus_title: The RT+ title name.
        duration_seconds: The duration of the track in seconds.

    Raises:
        RuntimeError: If the RT+TAG payload cannot be built.
    """
    await smartgen_mgr.send_command("TEXT", truncated_text)

    rt_plus_payload = build_rt_plus_tag_command(
        truncated_text,
        rt_plus_artist,
        rt_plus_title,
        duration_seconds // 60,  # minutes
    )

    if not rt_plus_payload:
        raise RuntimeError("Failed to build RT+TAG payload")

    await smartgen_mgr.send_command("RT+TAG", rt_plus_payload, truncated_text)


# Module-level processor instance (lazily initialized on first message)
_processor: MessageProcessor | None = None


async def on_message(
    message: IncomingMessage,
    smartgen_mgr: SmartGenConnectionManager,
    preview_exchange: AbstractRobustExchange | None,
) -> None:
    """Handle incoming message from RabbitMQ consumer.

    Creates the MessageProcessor on first call and reuses it for all
    subsequent messages.

    Args:
        message: The incoming RabbitMQ message.
        smartgen_mgr: The SmartGen connection manager.
        preview_exchange: The preview exchange (currently unused).
    """
    global _processor  # noqa: PLW0603
    if _processor is None:
        _processor = MessageProcessor(smartgen_mgr)
        await _processor.start()

    await _processor.handle_message(message, preview_exchange)


async def shutdown_processor() -> None:
    """Shutdown the message processor if running."""
    global _processor  # noqa: PLW0603
    if _processor is not None:
        await _processor.stop()
        _processor = None
