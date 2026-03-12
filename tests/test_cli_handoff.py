from __future__ import annotations

from pathlib import Path
import tomllib
from typing import cast

import pytest

from yee88.cli import handoff
from yee88.telegram.client import TelegramClient
from yee88.telegram.api_schemas import Chat, ForumTopic, Message
from yee88.telegram.topic_state import TopicStateStore, resolve_state_path


def _write_min_config(path: Path) -> None:
    path.write_text(
        '[transports.telegram]\nbot_token = "token"\nchat_id = 123\n',
        encoding="utf-8",
    )


def test_ensure_handoff_project_auto_registers_missing_project(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "yee88.toml"
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _write_min_config(config_path)

    monkeypatch.setattr(handoff, "list_backend_ids", lambda: ["codex"])
    monkeypatch.setattr(
        handoff,
        "resolve_main_worktree_root",
        lambda path: path if path == repo_path else None,
    )
    monkeypatch.setattr(handoff, "resolve_default_base", lambda _path: "main")

    project, note = handoff._ensure_handoff_project(
        project="lws",
        session_directory=str(repo_path),
        config_path=config_path,
    )

    assert project == "lws"
    assert note == "auto-registered project 'lws'"

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert data["projects"]["lws"]["path"] == str(repo_path)
    assert data["projects"]["lws"]["worktrees_dir"] == ".worktrees"
    assert data["projects"]["lws"]["worktree_base"] == "main"


def test_ensure_handoff_project_rejects_conflicting_alias(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "yee88.toml"
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _write_min_config(config_path)

    monkeypatch.setattr(handoff, "list_backend_ids", lambda: ["codex", "lws"])

    project, note = handoff._ensure_handoff_project(
        project="lws",
        session_directory=str(repo_path),
        config_path=config_path,
    )

    assert project is None
    assert note == "项目别名 'lws' 与引擎 ID 冲突，无法自动注册"

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert "projects" not in data


@pytest.mark.anyio
async def test_create_handoff_topic_sends_first_message_into_new_thread(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "yee88.toml"
    sent_calls: list[dict[str, object]] = []

    class _FakeClient:
        async def create_forum_topic(
            self, chat_id: int, name: str
        ) -> ForumTopic | None:
            assert chat_id == 123
            assert name == "📱 lws handoff"
            return ForumTopic(message_thread_id=77)

        async def send_message(
            self,
            chat_id: int,
            text: str,
            reply_to_message_id: int | None = None,
            disable_notification: bool | None = False,
            message_thread_id: int | None = None,
            entities: list[dict] | None = None,
            parse_mode: str | None = None,
            reply_markup: dict | None = None,
            *,
            replace_message_id: int | None = None,
        ) -> Message | None:
            _ = reply_to_message_id, disable_notification, entities, reply_markup
            _ = replace_message_id
            sent_calls.append(
                {
                    "chat_id": chat_id,
                    "text": text,
                    "message_thread_id": message_thread_id,
                    "parse_mode": parse_mode,
                }
            )
            return Message(
                message_id=1,
                chat=Chat(id=chat_id, type="supergroup"),
                message_thread_id=message_thread_id,
            )

        async def close(self) -> None:
            return None

    handoff.TelegramClient = lambda _token: _FakeClient()  # type: ignore[assignment]

    created = await handoff._create_handoff_topic(
        token="token",
        chat_id=123,
        session_id="sess-1",
        project="lws",
        config_path=config_path,
        message="hello",
    )

    assert created == (77, True)
    assert sent_calls == [
        {
            "chat_id": 123,
            "text": "hello",
            "message_thread_id": 77,
            "parse_mode": "Markdown",
        }
    ]

    store = TopicStateStore(resolve_state_path(config_path))
    snapshot = await store.get_thread(123, 77)
    assert snapshot is not None
    assert snapshot.context is not None
    assert snapshot.context.project == "lws"


@pytest.mark.anyio
async def test_send_message_with_client_rejects_thread_mismatch() -> None:
    class _MismatchClient:
        async def send_message(
            self,
            chat_id: int,
            text: str,
            reply_to_message_id: int | None = None,
            disable_notification: bool | None = False,
            message_thread_id: int | None = None,
            entities: list[dict] | None = None,
            parse_mode: str | None = None,
            reply_markup: dict | None = None,
            *,
            replace_message_id: int | None = None,
        ) -> Message | None:
            _ = (
                chat_id,
                text,
                reply_to_message_id,
                disable_notification,
                message_thread_id,
                entities,
                parse_mode,
                reply_markup,
                replace_message_id,
            )
            return Message(
                message_id=1,
                chat=Chat(id=123, type="supergroup"),
                message_thread_id=1,
            )

    ok = await handoff._send_message_with_client(
        cast(TelegramClient, _MismatchClient()),
        chat_id=123,
        message="hello",
        thread_id=77,
    )

    assert ok is False
