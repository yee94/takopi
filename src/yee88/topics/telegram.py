"""Telegram topic backend implementation."""

from __future__ import annotations

from pathlib import Path

from ..context import RunContext
from ..telegram.client import TelegramClient
from ..telegram.topic_state import TopicStateStore, resolve_state_path
from ..topics import TopicBackend, TopicInfo


class TelegramTopicBackend(TopicBackend):
    """Telegram topic backend using Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: int) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    @property
    def name(self) -> str:
        return "telegram"

    def is_available(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    async def create_topic(
        self,
        *,
        project: str,
        branch: str | None,
        config_path: Path,
    ) -> TopicInfo | None:
        title = self._generate_title(project, branch)

        client = TelegramClient(self._bot_token)
        try:
            result = await client.create_forum_topic(self._chat_id, title)
            if result is None:
                return None

            thread_id = result.message_thread_id

            state_path = resolve_state_path(config_path)
            store = TopicStateStore(state_path)

            context = RunContext(project=project.lower(), branch=branch)
            await store.set_context(self._chat_id, thread_id, context, topic_title=title)

            bound_text = f"topic bound to `{project}"
            if branch:
                bound_text += f" @{branch}"
            bound_text += "`"

            await client.send_message(
                chat_id=self._chat_id,
                text=bound_text,
                message_thread_id=thread_id,
                parse_mode="Markdown",
            )

            return TopicInfo(thread_id=thread_id, title=title)
        finally:
            await client.close()

    async def delete_topic(
        self,
        *,
        project: str,
        branch: str | None,
        config_path: Path,
    ) -> bool:
        state_path = resolve_state_path(config_path)
        store = TopicStateStore(state_path)

        context = RunContext(project=project.lower(), branch=branch)
        thread_id = await store.find_thread_for_context(self._chat_id, context)

        if thread_id is None:
            return False

        await store.delete_thread(self._chat_id, thread_id)

        client = TelegramClient(self._bot_token)
        try:
            await client.send_message(
                chat_id=self._chat_id,
                text=f"topic unbound from `{project}{' @' + branch if branch else ''}`",
                message_thread_id=thread_id,
                parse_mode="Markdown",
            )
        except Exception:
            pass
        finally:
            await client.close()

        return True

    async def list_topics(
        self,
        *,
        config_path: Path,
    ) -> list[TopicInfo]:
        return []

    def _generate_title(self, project: str, branch: str | None) -> str:
        if branch:
            return f"{project} @{branch}"
        return project
