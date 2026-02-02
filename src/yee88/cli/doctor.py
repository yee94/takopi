"""Health checks for yee88 transports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import typer

from ..config import ConfigError
from ..settings import TakopiSettings

DoctorStatus = Literal["ok", "warning", "error"]


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    label: str
    status: DoctorStatus
    detail: str | None = None

    def render(self) -> str:
        if self.detail:
            return f"- {self.label}: {self.status} ({self.detail})"
        return f"- {self.label}: {self.status}"


def _get_transport_doctor(
    transport: str,
) -> "TransportDoctor":
    if transport == "telegram":
        from .doctor_telegram import TelegramDoctor

        return TelegramDoctor()
    elif transport == "discord":
        from .doctor_discord import DiscordDoctor

        return DiscordDoctor()
    else:
        raise ConfigError(f"Unsupported transport: {transport!r}")


class TransportDoctor:
    def run_checks(
        self,
        settings: TakopiSettings,
        config_path: Path,
    ) -> list[DoctorCheck]:
        raise NotImplementedError


def run_doctor(
    *,
    load_settings_fn: Callable[[], tuple[TakopiSettings, Path]],
) -> None:
    try:
        settings, config_path = load_settings_fn()
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    transport = settings.transport

    try:
        doctor = _get_transport_doctor(transport)
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    checks = doctor.run_checks(settings, config_path)

    typer.echo(f"yee88 doctor ({transport})")
    for check in checks:
        typer.echo(check.render())

    if any(check.status == "error" for check in checks):
        raise typer.Exit(code=1)


# Backward compatibility exports
def _doctor_file_checks(settings: TakopiSettings) -> list[DoctorCheck]:
    """Backward compatibility: file checks for telegram transport."""
    tg = settings.transports.telegram.files
    if not tg.enabled:
        return [DoctorCheck("file transfer", "ok", "disabled")]
    if tg.allowed_user_ids:
        count = len(tg.allowed_user_ids)
        detail = f"restricted to {count} user id(s)"
        return [DoctorCheck("file transfer", "ok", detail)]
    return [DoctorCheck("file transfer", "warning", "enabled for all users")]


def _doctor_voice_checks(settings: TakopiSettings) -> list[DoctorCheck]:
    """Backward compatibility: voice checks for telegram transport."""
    import os

    if not settings.transports.telegram.voice_transcription:
        return [DoctorCheck("voice transcription", "ok", "disabled")]
    api_key = settings.transports.telegram.voice_transcription_api_key
    if api_key:
        return [
            DoctorCheck("voice transcription", "ok", "voice_transcription_api_key set")
        ]
    if os.environ.get("OPENAI_API_KEY"):
        return [DoctorCheck("voice transcription", "ok", "OPENAI_API_KEY set")]
    return [DoctorCheck("voice transcription", "error", "API key not set")]


async def _async_doctor_telegram_checks(
    token: str,
    chat_id: int,
    topics,
    project_chat_ids: tuple[int, ...],
) -> list[DoctorCheck]:
    """Async implementation of telegram-specific checks."""
    from ..telegram.client import TelegramClient
    from ..telegram.topics import _validate_topics_setup_for

    checks: list[DoctorCheck] = []
    bot = TelegramClient(token)
    try:
        me = await bot.get_me()
        if me is None:
            checks.append(
                DoctorCheck("telegram token", "error", "failed to fetch bot info")
            )
            checks.append(DoctorCheck("chat_id", "error", "skipped (token invalid)"))
            if topics.enabled:
                checks.append(DoctorCheck("topics", "error", "skipped (token invalid)"))
            else:
                checks.append(DoctorCheck("topics", "ok", "disabled"))
            return checks
        bot_label = f"@{me.username}" if me.username else f"id={me.id}"
        checks.append(DoctorCheck("telegram token", "ok", bot_label))
        chat = await bot.get_chat(chat_id)
        if chat is None:
            checks.append(DoctorCheck("chat_id", "error", f"unreachable ({chat_id})"))
        else:
            checks.append(DoctorCheck("chat_id", "ok", f"{chat.type} ({chat_id})"))
        if topics.enabled:
            try:
                await _validate_topics_setup_for(
                    bot=bot,
                    topics=topics,
                    chat_id=chat_id,
                    project_chat_ids=project_chat_ids,
                )
                checks.append(DoctorCheck("topics", "ok", f"scope={topics.scope}"))
            except ConfigError as exc:
                checks.append(DoctorCheck("topics", "error", str(exc)))
        else:
            checks.append(DoctorCheck("topics", "ok", "disabled"))
    except Exception as exc:
        checks.append(DoctorCheck("telegram", "error", str(exc)))
    finally:
        await bot.close()
    return checks


def _doctor_telegram_checks(
    token: str,
    chat_id: int,
    topics,
    project_chat_ids: tuple[int, ...],
) -> list[DoctorCheck]:
    """Backward compatibility: run telegram-specific checks."""
    import anyio

    result = anyio.run(
        _async_doctor_telegram_checks,
        token,
        chat_id,
        topics,
        project_chat_ids,
    )
    return result or []
