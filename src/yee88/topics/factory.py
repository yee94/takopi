"""Topic backend factory for creating transport-specific backends."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..config import ConfigError
from ..settings import load_settings
from . import TopicBackend

if TYPE_CHECKING:
    from ..settings import TakopiSettings


def create_topic_backend(
    settings: TakopiSettings | None = None,
    config_path: Path | None = None,
) -> TopicBackend:
    """Create and return the appropriate topic backend based on transport settings.

    Args:
        settings: Optional pre-loaded settings. If None, will load from config.
        config_path: Optional path to config file.

    Returns:
        TopicBackend implementation for the configured transport.

    Raises:
        ConfigError: If transport is not supported or not configured.
    """
    if settings is None:
        settings, _ = load_settings(config_path)

    transport = settings.transport

    if transport == "telegram":
        from .telegram import TelegramTopicBackend

        tg = settings.transports.telegram
        if not tg.topics.enabled:
            raise ConfigError(
                "topics not enabled. "
                "Run `yee88 config set transports.telegram.topics.enabled true`"
            )
        return TelegramTopicBackend(bot_token=tg.bot_token, chat_id=tg.chat_id)

    elif transport == "discord":
        from .discord import DiscordTopicBackend

        discord_config = settings.transports.model_extra.get("discord") if settings.transports.model_extra else None
        if not discord_config:
            raise ConfigError("discord transport not configured")

        bot_token = discord_config.get("bot_token")
        channel_id = discord_config.get("channel_id")

        if not bot_token:
            raise ConfigError("discord.bot_token is required")
        if not channel_id:
            raise ConfigError("discord.channel_id is required for topic management")

        return DiscordTopicBackend(bot_token=bot_token, channel_id=channel_id)

    else:
        raise ConfigError(f"topic management not supported for transport: {transport}")
