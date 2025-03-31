"""
Load the `words.json` file and filter out whole profane words from the
input text. Ignores substrings. Case insensitive. Replaces the profane
words with asterisks of the same length.

TODO: This is expensive since it is loading the `words.json` file for
    every message. Consider loading the file once and caching the
    profane words. This will reduce the overhead of reading the file for
    every message.

Author: Mason Daugherty <@mdrxy>
Version: 1.0.0
Last Modified: 2025-03-23

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
"""

import json
import re

from utils.discord import Colors, EmbedType
from utils.discord import send_embed as send_discord_embed
from utils.logging import configure_logging

logger = configure_logging(__name__)


async def filter_profane_words(text: str) -> str:
    """
    Filter out profane words from the input text.
    """
    try:
        with open("utils/words.json", "r", encoding="utf-8") as file:
            profane_words = json.load(file)
    except FileNotFoundError:
        logger.critical("words.json file not found.")
        return text
    except json.JSONDecodeError as e:
        logger.critical("Failed to decode JSON in words.json: %s", e)
        return text
    except IOError as e:
        logger.critical("I/O error occurred while reading words.json: %s", e)
        return text

    for word in profane_words:
        # Match the full word only - no substrings
        pattern = r"\b" + re.escape(word) + r"\b"

        # Lowercase the text and the word for case-insensitive matching
        text = text.lower()
        censored = False
        if re.search(pattern, text):
            logger.info("Replacing profane word: %s", word)
            censored = True

        if censored:
            censored_text = re.sub(pattern, lambda m: "*" * len(m.group(0)), text)
            markdown_safe_censored_text = re.sub(
                pattern, lambda m: r"\*" * len(m.group(0)), text
            )
            fields = {
                "Original": text,
                "Censored": markdown_safe_censored_text,
            }
            await send_discord_embed(
                embed_type=EmbedType.PROFANITY,
                title="Profanity Filtered",
                title_url="https://github.com/WBOR-91-1-FM/wbor-rds-encoder/blob/c860debbe5994af0fe391fdbbc8539a7741549a3/encoder/utils/profane_words.py#L29",  # pylint: disable=line-too-long
                desc=f"Profane word detected: `{word}`",
                fields=fields,
                color=Colors.WARNING,
            )
            logger.debug("Censored text: `%s`", censored_text)

            return censored_text

    return text
