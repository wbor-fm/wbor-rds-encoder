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
from utils.discord import Colors, EmbedType
from utils.discord import send_embed as send_discord_embed
from utils.logging import configure_logging
from utils.metadata import clean_metadata_field
from utils.profane_words import filter_profane_words

logger = configure_logging(__name__)


async def sanitize_text(raw_text: str, field_type: str = None) -> str:
    """
    Sanitize metadata text for broadcast and SmartGen syntax. Strip or
    replace disallowed characters, remove or filter out profane words.

    Reduces the character set to the ASCII range (see
    `images/ascii-safe.png`).

    Note: all returned text is capitalized.
    """
    logger.debug("Sanitizing text: `%s`", raw_text)

    # (0) Clean metadata
    cleaned_text = raw_text
    if field_type:
        try:
            # Clean the metadata field using music-metadata-filter
            # (Amazon filter). This removes unwanted characters and
            # normalizes the text.
            cleaned_text = clean_metadata_field(field_type, raw_text)
            if cleaned_text != raw_text:
                logger.debug(
                    "Metadata cleaned (%s): `%s` -> `%s`",
                    field_type,
                    raw_text,
                    cleaned_text,
                )

                title = "Metadata Cleaned"
                description = (
                    f"{field_type.capitalize()} field cleaned using "
                    f"music-metadata-filter (Amazon filter)."
                )
                fields = {
                    "Original": raw_text,
                    "Cleaned": cleaned_text,
                }

                await send_discord_embed(
                    embed_type=EmbedType.METADATA,
                    title=title,
                    title_url="https://github.com/WBOR-91-1-FM/wbor-rds-encoder/blob/c860debbe5994af0fe391fdbbc8539a7741549a3/encoder/utils/sanitization.py#L24",  # pylint: disable=line-too-long
                    desc=description,
                    fields=fields,
                    color=Colors.WARNING,
                )
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("Metadata cleaning failed: %s", e)

    unidecoded_text = cleaned_text

    # (1) Detect non-ASCII characters. If found, unidecode the text by
    #   replacing them with ASCII equivalents. If no equivalents are
    #   found, the unicode character is substituted with a question
    #   mark. Log the original and unidecoded text for debugging to logs
    #   and Discord.
    non_ascii_chars = re.findall(r"[^\x00-\x7F]", cleaned_text)
    if non_ascii_chars:
        unidecoded_text = unidecode(raw_text, errors="replace").strip()

        logger.debug(
            "Non-ASCII characters unidecoded: `%s` -> `%s`",
            cleaned_text,
            unidecoded_text,
        )

        title = ""
        description = ""
        if len(non_ascii_chars) > 1:
            title = "Non-ASCII Characters Replaced"
            description = f"Characters: `{''.join(set(non_ascii_chars))}`"
        else:
            title = "Non-ASCII Character Replaced"
            description = f"Character: `{''.join(set(non_ascii_chars))}`"
        fields = {
            "Original": cleaned_text,
            "Unidecoded": unidecoded_text,
        }

        await send_discord_embed(
            embed_type=EmbedType.UNIDECODE,
            title=title,
            title_url="https://github.com/WBOR-91-1-FM/wbor-rds-encoder/blob/c860debbe5994af0fe391fdbbc8539a7741549a3/encoder/utils/sanitization.py#L24",  # pylint: disable=line-too-long
            desc=description,
            fields=fields,
            color=Colors.WARNING,
        )

    # (2) At this point, the cleaned_text string *may* have been
    #   unidecoded. It should be safe within the ASCII range. Filter
    #   out profanity.
    filtered_text = await filter_profane_words(unidecoded_text)

    # (3) Capitalize.
    sanitized = filtered_text.upper()
    return sanitized
