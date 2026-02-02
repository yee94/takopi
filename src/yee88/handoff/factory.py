"""Handoff backend factory."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..config import ConfigError
from ..settings import load_settings
from . import HandoffBackend

if TYPE_CHECKING:
    from ..settings import TakopiSettings


def create_handoff_backend(
    settings: TakopiSettings | None = None,
    config_path: Path | None = None,
) -> HandoffBackend:
    """Create handoff backend based on transport settings."""
    if settings is None:
        settings, _ = load_settings(config_path)

    transport = settings.transport

    if transport == "telegram":
        from .telegram import TelegramHandoffBackend

        tg = settings.transports.telegram
        if not tg.topics.enabled:
            raise ConfigError(
                "topics not enabled. "
                "Run `yee88 config set transports.telegram.topics.enabled true`"
            )
        return TelegramHandoffBackend(bot_token=tg.bot_token, chat_id=tg.chat_id)

    elif transport == "discord":
        from .discord import DiscordHandoffBackend

        discord_config = settings.transports.model_extra.get("discord") if settings.transports.model_extra else None
        if not discord_config:
            raise ConfigError("discord transport not configured")

        bot_token = discord_config.get("bot_token")
        channel_id = discord_config.get("channel_id")

        if not bot_token:
            raise ConfigError("discord.bot_token is required")
        if not channel_id:
            raise ConfigError("discord.channel_id is required for handoff")

        return DiscordHandoffBackend(bot_token=bot_token, channel_id=channel_id)

    else:
        raise ConfigError(f"handoff not supported for transport: {transport}")
