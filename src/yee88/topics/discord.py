"""Discord thread backend implementation."""

from __future__ import annotations

import json
from pathlib import Path

from ..context import RunContext
from ..discord.client import DiscordBotClient
from ..topics import TopicBackend, TopicInfo


class DiscordTopicBackend(TopicBackend):
    """Discord thread backend using Discord API."""

    def __init__(self, bot_token: str, channel_id: int) -> None:
        self._bot_token = bot_token
        self._channel_id = channel_id
        self._state_file = "discord_topics.json"

    @property
    def name(self) -> str:
        return "discord"

    def is_available(self) -> bool:
        return bool(self._bot_token and self._channel_id)

    async def create_topic(
        self,
        *,
        project: str,
        branch: str | None,
        config_path: Path,
    ) -> TopicInfo | None:
        import sys

        title = self._generate_title(project, branch)

        client = DiscordBotClient(self._bot_token)
        try:
            print(f"debug: starting discord bot...", file=sys.stderr)
            await client.start()
            print(f"debug: bot started, user={client.user}", file=sys.stderr)

            print(f"debug: sending message to channel {self._channel_id}...", file=sys.stderr)
            send_result = await client.send_message(
                channel_id=self._channel_id,
                content=f"Creating thread for {title}...",
            )

            if send_result is None:
                print(f"error: failed to send initial message to channel {self._channel_id}", file=sys.stderr)
                print(f"debug: bot user={client.user}, bot={client._bot}", file=sys.stderr)
                return None

            message_id = send_result.message_id

            thread_id = await client.create_thread(
                channel_id=self._channel_id,
                message_id=message_id,
                name=title,
            )

            if thread_id is None:
                print(f"error: failed to create thread from message {message_id}", file=sys.stderr)
                return None

            self._save_topic_state(
                config_path=config_path,
                thread_id=thread_id,
                project=project,
                branch=branch,
                title=title,
            )

            await client.send_message(
                channel_id=thread_id,
                content=f"Thread bound to `{project}{' @' + branch if branch else ''}`",
            )

            return TopicInfo(thread_id=thread_id, title=title)
        except Exception as e:
            print(f"error: exception during topic creation: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return None
        finally:
            await client.close()

    async def delete_topic(
        self,
        *,
        project: str,
        branch: str | None,
        config_path: Path,
    ) -> bool:
        topic_info = self._find_topic(config_path, project, branch)

        if topic_info is None:
            return False

        self._delete_topic_state(config_path, topic_info.thread_id)

        client = DiscordBotClient(self._bot_token)
        try:
            await client.start()
            await client.send_message(
                channel_id=topic_info.thread_id,
                content=f"Thread unbound from `{project}{' @' + branch if branch else ''}`",
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
        state = self._load_state(config_path)
        return [
            TopicInfo(thread_id=t["thread_id"], title=t["title"])
            for t in state.get("topics", [])
        ]

    def _generate_title(self, project: str, branch: str | None) -> str:
        if branch:
            return f"{project} @{branch}"
        return project

    def _get_state_path(self, config_path: Path) -> Path:
        return config_path.parent / self._state_file

    def _load_state(self, config_path: Path) -> dict:
        state_path = self._get_state_path(config_path)
        if not state_path.exists():
            return {"topics": []}
        try:
            with open(state_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"topics": []}

    def _save_state(self, config_path: Path, state: dict) -> None:
        state_path = self._get_state_path(config_path)
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

    def _save_topic_state(
        self,
        config_path: Path,
        thread_id: int,
        project: str,
        branch: str | None,
        title: str,
    ) -> None:
        state = self._load_state(config_path)
        topic = {
            "thread_id": thread_id,
            "project": project.lower(),
            "branch": branch,
            "title": title,
        }
        state["topics"].append(topic)
        self._save_state(config_path, state)

    def _find_topic(
        self,
        config_path: Path,
        project: str,
        branch: str | None,
    ) -> TopicInfo | None:
        state = self._load_state(config_path)
        for t in state.get("topics", []):
            if t["project"] == project.lower() and t["branch"] == branch:
                return TopicInfo(thread_id=t["thread_id"], title=t["title"])
        return None

    def _delete_topic_state(self, config_path: Path, thread_id: int) -> None:
        state = self._load_state(config_path)
        state["topics"] = [t for t in state.get("topics", []) if t["thread_id"] != thread_id]
        self._save_state(config_path, state)
