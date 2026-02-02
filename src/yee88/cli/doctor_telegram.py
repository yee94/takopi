"""Telegram-specific health checks for yee88 doctor."""

from __future__ import annotations

import os
from pathlib import Path

from ..config import ConfigError
from ..ids import RESERVED_CHAT_COMMANDS
from ..runtime_loader import resolve_plugins_allowlist
from ..settings import TakopiSettings, TelegramTopicsSettings
from ..telegram.client import TelegramClient
from ..telegram.topics import _validate_topics_setup_for
from .doctor import DoctorCheck, TransportDoctor


class TelegramDoctor(TransportDoctor):
    def run_checks(
        self,
        settings: TakopiSettings,
        config_path: Path,
    ) -> list[DoctorCheck]:
        from ..engines import list_backend_ids

        tg = settings.transports.telegram
        allowlist = resolve_plugins_allowlist(settings)
        engine_ids = list_backend_ids(allowlist=allowlist)

        try:
            projects_cfg = settings.to_projects_config(
                config_path=config_path,
                engine_ids=engine_ids,
                reserved=RESERVED_CHAT_COMMANDS,
            )
        except ConfigError as exc:
            return [DoctorCheck("config", "error", str(exc))]

        project_chat_ids = projects_cfg.project_chat_ids()
        telegram_checks = self._check_telegram(
            tg.bot_token,
            tg.chat_id,
            tg.topics,
            project_chat_ids,
        )
        file_checks = self._check_files(settings)
        voice_checks = self._check_voice(settings)

        return [
            *telegram_checks,
            *file_checks,
            *voice_checks,
        ]

    def _check_telegram(
        self,
        token: str,
        chat_id: int,
        topics: TelegramTopicsSettings,
        project_chat_ids: tuple[int, ...],
    ) -> list[DoctorCheck]:
        import anyio

        return anyio.run(
            self._async_check_telegram,
            token,
            chat_id,
            topics,
            project_chat_ids,
        ) or []

    async def _async_check_telegram(
        self,
        token: str,
        chat_id: int,
        topics: TelegramTopicsSettings,
        project_chat_ids: tuple[int, ...],
    ) -> list[DoctorCheck]:
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

    def _check_files(self, settings: TakopiSettings) -> list[DoctorCheck]:
        files = settings.transports.telegram.files
        if not files.enabled:
            return [DoctorCheck("file transfer", "ok", "disabled")]
        if files.allowed_user_ids:
            count = len(files.allowed_user_ids)
            detail = f"restricted to {count} user id(s)"
            return [DoctorCheck("file transfer", "ok", detail)]
        return [DoctorCheck("file transfer", "warning", "enabled for all users")]

    def _check_voice(self, settings: TakopiSettings) -> list[DoctorCheck]:
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
