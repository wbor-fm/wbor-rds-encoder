"""
Send status messages to Discord using webhooks.
https://github.com/lovvskillz/python-discord-webhook

Author: Mason Daugherty <@mdrxy>
Version: 1.0.0
Last Modified: 2025-03-23

Changelog:
    - 1.0.0 (2025-03-23): Initial release.

TODO: parse response and test for success/failure.
"""

from config import DISCORD_AUTHOR_ICON_URL, DISCORD_WEBHOOK_URL
from discord_webhook import AsyncDiscordWebhook, DiscordEmbed
from utils.logging import configure_logging

logger = configure_logging(__name__)


class EmbedType:
    """
    Categorize the type of message being sent.
    """

    UNIDECODE = "Unidecoded to ASCII"
    PROFANITY = "Profanity Filtered"
    METADATA = "Metadata Cleaned"


class Colors:
    """
    Predefined colors for Discord embeds.
    """

    DEFAULT = 242424  # Default color
    SUCCESS = 3066993  # Green
    WARNING = 16776960  # Yellow
    ERROR = 15158332  # Red


async def send_basic_webhook(message: str) -> None:
    """
    Send a message to Discord using a webhook.
    """
    webhook = AsyncDiscordWebhook(url=DISCORD_WEBHOOK_URL, content=message)
    response = await webhook.execute()
    logger.debug(
        "Sent basic webhook message to Discord: `%s` | Response: `%s`",
        message,
        response,
    )


async def send_embed(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    embed_type: EmbedType,
    title: str,
    title_url: str,
    desc: str,
    fields: dict,
    color: Colors = Colors.DEFAULT,
    author_icon_url: str = DISCORD_AUTHOR_ICON_URL,
    author: str = "wbor-rds-encoder",
) -> None:
    """
    Send a message with an embed to Discord using a webhook.
    """
    webhook = AsyncDiscordWebhook(url=DISCORD_WEBHOOK_URL)
    embed = DiscordEmbed(title=title, color=color, description=desc, url=title_url)
    for field in fields.items():
        field_name, field_value = field
        embed.add_embed_field(name=field_name, value=field_value)

    embed.set_author(name=author, icon_url=author_icon_url)
    webhook.add_embed(embed)
    response = await webhook.execute()
    logger.debug(
        "Sent `%s` embed to Discord - Response: `%s`",
        embed_type,
        response.status_code,
    )
