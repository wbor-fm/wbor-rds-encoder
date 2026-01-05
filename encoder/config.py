"""
App configuration file. Load environment variables from .env file.
"""

import os
import sys

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

# Binding queue to this key
QUEUE_BINDING_KEY = os.getenv("QUEUE_BINDING_KEY", "spinitron.#")

# Publishing to this exchange (optional, for a "preview" feature)
PREVIEW_EXCHANGE = os.getenv("RABBITMQ_PREVIEW_EXCHANGE")
PREVIEW_ROUTING_KEY = os.getenv("RABBITMQ_PREVIEW_ROUTING_KEY")

RDS_ENCODER_HOST = str(os.getenv("RDS_ENCODER_HOST"))
RDS_ENCODER_PORT = os.getenv("RDS_ENCODER_PORT")

# Enable or disable the profanity filter (defaults to true)
PROFANITY_FILTER_ENABLED = os.getenv("PROFANITY_FILTER_ENABLED", "true").lower() in (
    "true",
    "1",
    "yes",
)

required_env_vars = [
    RABBITMQ_HOST,
    RABBITMQ_USER,
    RABBITMQ_PASS,
    RABBITMQ_QUEUE,
    RABBITMQ_EXCHANGE,
    QUEUE_BINDING_KEY,
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
            "RABBITMQ_EXCHANGE",
            "QUEUE_BINDING_KEY",
            "RDS_ENCODER_HOST",
            "RDS_ENCODER_PORT",
        ]
        if not locals()[var]
    ]
    error_msg = f"Missing required environment variables: `{', '.join(missing_vars)}`"
    print(f"CRITICAL CONFIG ERROR: {error_msg}", file=sys.stderr)
    raise EnvironmentError(error_msg)

if RDS_ENCODER_PORT is not None:
    try:
        RDS_ENCODER_PORT = int(RDS_ENCODER_PORT)
    except ValueError as exc:
        error_msg = f"RDS_ENCODER_PORT ('{os.getenv('RDS_ENCODER_PORT')}') is not a valid integer."
        print(f"CRITICAL CONFIG ERROR: {error_msg}", file=sys.stderr)
        raise EnvironmentError(error_msg) from exc
else:
    error_msg = "RDS_ENCODER_PORT must be set and be an integer."
    print(f"CRITICAL CONFIG ERROR: {error_msg}", file=sys.stderr)
    raise EnvironmentError(error_msg)

# Content type codes
ARTIST_TAG = "04"
TITLE_TAG = "01"
BLANK_TAG = "00"
