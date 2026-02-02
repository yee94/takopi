"""Discord-specific health checks for yee88 doctor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import ConfigError
from ..settings import TakopiSettings
from .doctor import DoctorCheck, TransportDoctor


class DiscordDoctor(TransportDoctor):
    def run_checks(
        self,
        settings: TakopiSettings,
        config_path: Path,
    ) -> list[DoctorCheck]:
        checks: list[DoctorCheck] = []

        # Get Discord settings from model_extra
        extra = settings.transports.model_extra or {}
        discord_config = extra.get("discord", {})

        if not isinstance(discord_config, dict):
            checks.append(
                DoctorCheck("discord config", "error", "invalid discord configuration")
            )
            return checks

        # Check bot token
        token = discord_config.get("bot_token")
        if not token:
            checks.append(DoctorCheck("discord token", "error", "bot_token not set"))
        else:
            checks.append(DoctorCheck("discord token", "ok", "configured"))

        # Check guild_id
        guild_id = discord_config.get("guild_id")
        if guild_id:
            checks.append(DoctorCheck("discord guild", "ok", f"guild_id={guild_id}"))
        else:
            checks.append(DoctorCheck("discord guild", "warning", "guild_id not set"))

        # Check channel_id
        channel_id = discord_config.get("channel_id")
        if channel_id:
            checks.append(DoctorCheck("discord channel", "ok", f"channel_id={channel_id}"))
        else:
            checks.append(
                DoctorCheck("discord channel", "warning", "channel_id not set (optional)")
            )

        # Check message_overflow setting
        overflow = discord_config.get("message_overflow", "split")
        checks.append(DoctorCheck("message overflow", "ok", f"mode={overflow}"))

        # Check session_mode
        session_mode = discord_config.get("session_mode", "stateless")
        checks.append(DoctorCheck("session mode", "ok", f"mode={session_mode}"))

        return checks
