"""
App configuration file. Load environment variables from .env file.
"""

import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_AUTHOR_ICON_URL = os.getenv(
    "DISCORD_AUTHOR_ICON_URL", "https://wbor.org/assets/images/apple-touch-icon.png"
)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST")
RABBITMQ_USER = os.getenv("RABBITMQ_USER")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS")

# Consuming from this queue
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE")
RABBITMQ_EXCHANGE = os.getenv("RABBITMQ_EXCHANGE")

# Publishing to this exchange (optional, for a "preview" feature)
PREVIEW_EXCHANGE = os.getenv("RABBITMQ_PREVIEW_EXCHANGE")
PREVIEW_ROUTING_KEY = os.getenv("RABBITMQ_PREVIEW_ROUTING_KEY")

RDS_ENCODER_HOST = str(os.getenv("RDS_ENCODER_HOST"))
RDS_ENCODER_PORT = os.getenv("RDS_ENCODER_PORT")

required_env_vars = [
    RABBITMQ_HOST,
    RABBITMQ_USER,
    RABBITMQ_PASS,
    RABBITMQ_QUEUE,
    PREVIEW_EXCHANGE,
    PREVIEW_ROUTING_KEY,
    RDS_ENCODER_HOST,
    RDS_ENCODER_PORT,
]

if not all(required_env_vars):
    missing_vars = [
        var
        for var in [
            "RABBITMQ_HOST",
            "RABBITMQ_USER",
            "RABBITMQ_PASS",
            "RABBITMQ_QUEUE",
            "PREVIEW_EXCHANGE",
            "PREVIEW_ROUTING_KEY",
            "RDS_ENCODER_HOST",
            "RDS_ENCODER_PORT",
        ]
        if not locals()[var]
    ]
    raise EnvironmentError(
        f"Missing required environment variables: `{', '.join(missing_vars)}`"
    )

RDS_ENCODER_PORT = int(RDS_ENCODER_PORT)

# Content type codes
ARTIST_TAG = "04"
TITLE_TAG = "01"
BLANK_TAG = "00"
