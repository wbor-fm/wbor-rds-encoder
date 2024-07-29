"""
Methods to sanitize text to (a) make safe for broadcast and (b) comply
with SmartGen Mini syntax requirements.

Author: Mason Daugherty <@mdrxy>
Version: 1.0.0
Last Modified: 2025-03-23

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
"""

import re

from unidecode import unidecode
from utils.discord import send_webhook as notify_discord
from utils.logging import configure_logging
from utils.profane_words import filter_profane_words

logger = configure_logging(__name__)


async def sanitize_text(raw_text: str) -> str:
    """
    Strip or replace disallowed characters, remove or filter out profane
    words.

    We need to reduce the character set to the ASCII range (see
    `images/ascii-safe.png`) and ensure that the text is safe for
    broadcast. This involves:
    - Removing control characters
    - Filtering out profanity
    - Converting to uppercase (for receiver compatibility)
    - Replacing special characters with safe equivalents if possible
        - If not, replace with a question mark

    Note: all returned text is capitalized.
    """
    logger.debug("Sanitizing text: `%s`", raw_text)
    unidecoded_text = raw_text

    # (1) Detect non-ASCII characters. If found, unidecode the text by
    #   replacing them with ASCII equivalents. If none are found, the
    #   character is substituted with a question mark. Log the original
    #   and unidecoded text for debugging to logs and Discord.
    non_ascii_chars = re.findall(r"[^\x00-\x7F]", raw_text)
    if non_ascii_chars:
        unidecoded_text = unidecode(raw_text, errors="replace").strip()

        log_message = (
            f"Non-ASCII characters found: `{''.join(set(non_ascii_chars))}`\n"
            f"Original: `{raw_text}`\n"
            f"Unidecoded: `{unidecoded_text}`"
        )
        logger.warning(log_message)
        await notify_discord(log_message)

    # (2) At this point, the raw_text string may have been unidecoded.
    #   It should be safe within the ASCII range. We move on to
    #   filtering out profanity. Profanity filtering is not yet
    #   implemented in this snippet.
    filtered_text = await filter_profane_words(unidecoded_text)

    sanitized = filtered_text.upper()
    return sanitized
