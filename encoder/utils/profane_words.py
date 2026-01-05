"""
Filter out profane words from input text using a configurable list
stored in `words.json`. The filter replaces whole profane words
(ignoring substrings and case-insensitive) with asterisks of matching
length. The words list is cached in memory to improve performance.

To  update the filtered words, edit `words.json` and clear the cache if
the application is running (`load_profane_words.cache_clear()`).

Author: Mason Daugherty <@mdrxy>
Version: 1.1.0
Last Modified: 2025-04-15

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
    - 1.1.0 (2025-04-16): Implemented lazy-loading with caching.
"""

import json
import re
from functools import lru_cache

from utils.discord import Colors, EmbedType
from utils.discord import send_embed as send_discord_embed
from utils.logging import configure_logging

logger = configure_logging(__name__)


@lru_cache(maxsize=1)
def load_profane_words() -> set:
    """Lazy-load and cache profane words from file.

    Words are cached in memory for performance. The cache is cleared when
    the application is restarted or when explicitly called with
    `load_profane_words.cache_clear()`.

    Returns:
        A set of profane words to filter, or empty set if loading fails.
    """
    try:
        with open("utils/words.json", "r", encoding="utf-8") as file:
            logger.debug("Profane words loaded into cache.")
            return set(json.load(file))
    except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
        logger.critical("Failed to load words.json: %s", e)
        return set()


async def filter_profane_words(text: str) -> str:
    """Filter out profane words from the input text.

    Args:
        text: The input text to filter.

    Returns:
        The filtered text with profane words replaced by asterisks.
    """
    original_text = text
    censored_text = text.lower()
    censored = False

    for word in load_profane_words():
        pattern = rf"\b{re.escape(word)}\b"
        if re.search(pattern, censored_text):
            logger.info("Replacing profane word: %s", word)
            censored = True
            censored_text = re.sub(
                pattern, lambda m: "*" * len(m.group(0)), censored_text
            )

    if censored:
        markdown_safe_censored_text = censored_text.replace("*", r"\*")
        fields = {
            "Original": original_text,
            "Censored": markdown_safe_censored_text,
        }
        await send_discord_embed(
            embed_type=EmbedType.PROFANITY,
            title="Profanity Filtered",
            title_url=(
                "https://github.com/wbor-fm/wbor-rds-encoder/blob/c860debbe5994af0"
                "fe391fdbbc8539a7741549a3/encoder/utils/profane_words.py#L29"
            ),
            desc="Profane word detected and filtered.",
            fields=fields,
            color=Colors.WARNING,
        )
        logger.debug("Censored text: `%s`", censored_text)

    return censored_text if censored else original_text
