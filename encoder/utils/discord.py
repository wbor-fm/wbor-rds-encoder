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

from config import DISCORD_WEBHOOK_URL
from discord_webhook import AsyncDiscordWebhook, DiscordEmbed
from utils.logging import configure_logging

logger = configure_logging(__name__)


class EmbedType:
    """
    Categorize the type of message being sent.
    """

    UNIDECODE = "Unidecoded to ASCII"
    PROFANITY = "Profanity Filtered"


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


async def send_embed(
    embed_type: EmbedType,
    title: str,
    desc: str,
    fields: dict,
    color: Colors = Colors.DEFAULT,
) -> None:
    """
    Send a message with an embed to Discord using a webhook.
    """
    webhook = AsyncDiscordWebhook(url=DISCORD_WEBHOOK_URL)
    embed = DiscordEmbed(title=title, color=color, description=desc)
    for field in fields.items():
        field_name, field_value = field
        embed.add_embed_field(name=field_name, value=field_value)
    embed.set_timestamp()
    webhook.add_embed(embed)
    response = await webhook.execute()
    logger.debug(
        "Sent `%s` embed to Discord - Response: `%s`",
        embed_type,
        response,
    )
