"""Discord handoff backend implementation."""

from __future__ import annotations

import json
from pathlib import Path

from ..discord.client import DiscordBotClient
from . import HandoffBackend, HandoffResult, SessionContext


class DiscordHandoffBackend(HandoffBackend):
    """Discord handoff backend using Discord API."""

    def __init__(self, bot_token: str, channel_id: int) -> None:
        self._bot_token = bot_token
        self._channel_id = channel_id
        self._state_file = "discord_handoffs.json"

    @property
    def name(self) -> str:
        return "discord"

    def is_available(self) -> bool:
        return bool(self._bot_token and self._channel_id)

    def format_messages(self, messages: list[dict], session_id: str, project: str | None) -> str:
        lines = ["📱 **会话接力**", ""]

        if project:
            lines.append(f"📁 项目: `{project}`")
        lines.append(f"🔗 Session: `{session_id}`")
        lines.append("")
        lines.append("---")
        lines.append("")

        for msg in messages:
            role = msg.get("role", "unknown")
            text = msg.get("text", "")
            role_label = "👤" if role == "user" else "🤖"
            if len(text) > 500:
                text = text[:500] + "..."
            lines.append(f"{role_label} **{role}**:")
            lines.append(text)
            lines.append("")

        total_len = sum(len(line) for line in lines)
        if total_len > 3500:
            lines = lines[:20]
            lines.append("... (truncated)")

        lines.append("---")
        lines.append("")
        lines.append("💡 直接在此 Thread 发消息即可继续对话")

        return "\n".join(lines)

    async def handoff(
        self,
        *,
        context: SessionContext,
        config_path: Path,
    ) -> HandoffResult:
        title = f"📱 {context.project} handoff"

        client = DiscordBotClient(self._bot_token)
        try:
            await client.start()

            send_result = await client.send_message(
                channel_id=self._channel_id,
                content=f"Creating handoff thread for {title}...",
            )

            if send_result is None:
                return HandoffResult(success=False, thread_id=None)

            message_id = send_result.message_id

            thread_id = await client.create_thread(
                channel_id=self._channel_id,
                message_id=message_id,
                name=title,
            )

            if thread_id is None:
                return HandoffResult(success=False, thread_id=None)

            self._save_handoff_state(
                config_path=config_path,
                thread_id=thread_id,
                session_id=context.session_id,
                project=context.project,
            )

            handoff_msg = self.format_messages(
                context.messages,
                context.session_id,
                context.project,
            )

            send_result = await client.send_message(
                channel_id=thread_id,
                content=handoff_msg,
            )

            success = send_result is not None
            return HandoffResult(success=success, thread_id=thread_id if success else None)
        finally:
            await client.close()

    def _get_state_path(self, config_path: Path) -> Path:
        return config_path.parent / self._state_file

    def _load_state(self, config_path: Path) -> dict:
        state_path = self._get_state_path(config_path)
        if not state_path.exists():
            return {"handoffs": []}
        try:
            with open(state_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"handoffs": []}

    def _save_state(self, config_path: Path, state: dict) -> None:
        state_path = self._get_state_path(config_path)
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

    def _save_handoff_state(
        self,
        config_path: Path,
        thread_id: int,
        session_id: str,
        project: str,
    ) -> None:
        state = self._load_state(config_path)
        handoff = {
            "thread_id": thread_id,
            "session_id": session_id,
            "project": project.lower(),
        }
        state["handoffs"].append(handoff)
        self._save_state(config_path, state)
