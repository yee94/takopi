"""Telegram handoff backend implementation."""

from __future__ import annotations

from pathlib import Path

from ..context import RunContext
from ..model import ResumeToken
from ..telegram.client import TelegramClient
from ..telegram.topic_state import TopicStateStore, resolve_state_path
from . import HandoffBackend, HandoffResult, SessionContext


class TelegramHandoffBackend(HandoffBackend):
    """Telegram handoff backend using Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: int) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    @property
    def name(self) -> str:
        return "telegram"

    def is_available(self) -> bool:
        return bool(self._bot_token and self._chat_id)

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
        lines.append("💡 直接在此 Topic 发消息即可继续对话")

        return "\n".join(lines)

    async def handoff(
        self,
        *,
        context: SessionContext,
        config_path: Path,
    ) -> HandoffResult:
        title = f"📱 {context.project} handoff"

        client = TelegramClient(self._bot_token)
        try:
            result = await client.create_forum_topic(self._chat_id, title)
            if result is None:
                return HandoffResult(success=False, thread_id=None)

            thread_id = result.message_thread_id

            state_path = resolve_state_path(config_path)
            store = TopicStateStore(state_path)

            run_context = RunContext(project=context.project.lower(), branch=None)
            await store.set_context(self._chat_id, thread_id, run_context, topic_title=title)

            resume_token = ResumeToken(engine="opencode", value=context.session_id)
            await store.set_session_resume(self._chat_id, thread_id, resume_token)

            handoff_msg = self.format_messages(
                context.messages,
                context.session_id,
                context.project,
            )

            send_result = await client.send_message(
                chat_id=self._chat_id,
                text=handoff_msg,
                message_thread_id=thread_id,
                parse_mode="Markdown",
            )

            success = send_result is not None
            return HandoffResult(success=success, thread_id=thread_id if success else None)
        finally:
            await client.close()
