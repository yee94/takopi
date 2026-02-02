"""Tests for topic backend implementations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yee88.topics import TopicBackend, TopicInfo
from yee88.topics.discord import DiscordTopicBackend
from yee88.topics.factory import create_topic_backend
from yee88.topics.telegram import TelegramTopicBackend


class TestTopicBackendInterface:
    """Test that all backends implement the interface correctly."""

    def test_telegram_backend_has_name(self) -> None:
        backend = TelegramTopicBackend("token", 123)
        assert backend.name == "telegram"

    def test_discord_backend_has_name(self) -> None:
        backend = DiscordTopicBackend("token", 123)
        assert backend.name == "discord"

    def test_telegram_backend_is_available_with_config(self) -> None:
        backend = TelegramTopicBackend("token", 123)
        assert backend.is_available() is True

    def test_telegram_backend_not_available_without_token(self) -> None:
        backend = TelegramTopicBackend("", 123)
        assert backend.is_available() is False

    def test_discord_backend_is_available_with_config(self) -> None:
        backend = DiscordTopicBackend("token", 123)
        assert backend.is_available() is True

    def test_discord_backend_not_available_without_token(self) -> None:
        backend = DiscordTopicBackend("", 123)
        assert backend.is_available() is False


class TestTelegramTopicBackend:
    """Test TelegramTopicBackend implementation."""

    @pytest.mark.anyio
    async def test_create_topic_delegates_to_client(self) -> None:
        backend = TelegramTopicBackend("token", 123456)

        with patch("yee88.topics.telegram.TelegramClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_result = MagicMock()
            mock_result.message_thread_id = 789
            mock_client.create_forum_topic = AsyncMock(return_value=mock_result)
            mock_client.send_message = AsyncMock()
            mock_client.close = AsyncMock()

            result = await backend.create_topic(
                project="myproject",
                branch="feature",
                config_path=Path("/tmp/config.toml"),
            )

            assert result is not None
            assert result.thread_id == 789
            assert result.title == "myproject @feature"
            mock_client.create_forum_topic.assert_called_once_with(123456, "myproject @feature")

    @pytest.mark.anyio
    async def test_create_topic_returns_none_on_failure(self) -> None:
        backend = TelegramTopicBackend("token", 123456)

        with patch("yee88.topics.telegram.TelegramClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.create_forum_topic = AsyncMock(return_value=None)
            mock_client.close = AsyncMock()

            result = await backend.create_topic(
                project="myproject",
                branch=None,
                config_path=Path("/tmp/config.toml"),
            )

            assert result is None

    @pytest.mark.anyio
    async def test_delete_topic_finds_and_deletes(self) -> None:
        backend = TelegramTopicBackend("token", 123456)

        with patch("yee88.topics.telegram.TopicStateStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store_class.return_value = mock_store
            mock_store.find_thread_for_context = AsyncMock(return_value=789)
            mock_store.delete_thread = AsyncMock()

            with patch("yee88.topics.telegram.TelegramClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                mock_client.send_message = AsyncMock()
                mock_client.close = AsyncMock()

                result = await backend.delete_topic(
                    project="myproject",
                    branch="feature",
                    config_path=Path("/tmp/config.toml"),
                )

                assert result is True
                mock_store.delete_thread.assert_called_once_with(123456, 789)

    @pytest.mark.anyio
    async def test_delete_topic_returns_false_when_not_found(self) -> None:
        backend = TelegramTopicBackend("token", 123456)

        with patch("yee88.topics.telegram.TopicStateStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store_class.return_value = mock_store
            mock_store.find_thread_for_context = AsyncMock(return_value=None)

            result = await backend.delete_topic(
                project="myproject",
                branch="feature",
                config_path=Path("/tmp/config.toml"),
            )

            assert result is False


class TestDiscordTopicBackend:
    """Test DiscordTopicBackend implementation."""

    def test_generate_title_with_branch(self) -> None:
        backend = DiscordTopicBackend("token", 123)
        title = backend._generate_title("myproject", "feature-branch")
        assert title == "myproject @feature-branch"

    def test_generate_title_without_branch(self) -> None:
        backend = DiscordTopicBackend("token", 123)
        title = backend._generate_title("myproject", None)
        assert title == "myproject"

    def test_state_file_path(self, tmp_path: Path) -> None:
        backend = DiscordTopicBackend("token", 123)
        config_path = tmp_path / "config.toml"
        state_path = backend._get_state_path(config_path)
        assert state_path == tmp_path / "discord_topics.json"

    def test_save_and_load_topic_state(self, tmp_path: Path) -> None:
        backend = DiscordTopicBackend("token", 123)
        config_path = tmp_path / "config.toml"

        backend._save_topic_state(
            config_path=config_path,
            thread_id=456,
            project="myproject",
            branch="feature",
            title="myproject @feature",
        )

        state = backend._load_state(config_path)
        assert len(state["topics"]) == 1
        assert state["topics"][0]["thread_id"] == 456
        assert state["topics"][0]["project"] == "myproject"

    def test_find_topic_existing(self, tmp_path: Path) -> None:
        backend = DiscordTopicBackend("token", 123)
        config_path = tmp_path / "config.toml"

        backend._save_topic_state(
            config_path=config_path,
            thread_id=456,
            project="myproject",
            branch="feature",
            title="myproject @feature",
        )

        result = backend._find_topic(config_path, "myproject", "feature")
        assert result is not None
        assert result.thread_id == 456

    def test_find_topic_not_found(self, tmp_path: Path) -> None:
        backend = DiscordTopicBackend("token", 123)
        config_path = tmp_path / "config.toml"

        result = backend._find_topic(config_path, "myproject", "feature")
        assert result is None

    def test_delete_topic_state(self, tmp_path: Path) -> None:
        backend = DiscordTopicBackend("token", 123)
        config_path = tmp_path / "config.toml"

        backend._save_topic_state(
            config_path=config_path,
            thread_id=456,
            project="myproject",
            branch="feature",
            title="myproject @feature",
        )
        backend._save_topic_state(
            config_path=config_path,
            thread_id=789,
            project="other",
            branch=None,
            title="other",
        )

        backend._delete_topic_state(config_path, 456)

        state = backend._load_state(config_path)
        assert len(state["topics"]) == 1
        assert state["topics"][0]["thread_id"] == 789

    @pytest.mark.anyio
    async def test_list_topics_returns_saved_topics(self, tmp_path: Path) -> None:
        backend = DiscordTopicBackend("token", 123)
        config_path = tmp_path / "config.toml"

        backend._save_topic_state(
            config_path=config_path,
            thread_id=456,
            project="myproject",
            branch="feature",
            title="myproject @feature",
        )

        topics = await backend.list_topics(config_path=config_path)

        assert len(topics) == 1
        assert topics[0].thread_id == 456
        assert topics[0].title == "myproject @feature"


class TestCreateTopicBackend:
    """Test factory function create_topic_backend."""

    @patch("yee88.topics.factory.load_settings")
    def test_creates_telegram_backend(self, mock_load_settings: MagicMock) -> None:
        mock_settings = MagicMock()
        mock_settings.transport = "telegram"
        mock_settings.transports.telegram.bot_token = "token"
        mock_settings.transports.telegram.chat_id = 123
        mock_settings.transports.telegram.topics.enabled = True
        mock_load_settings.return_value = (mock_settings, Path("/tmp/config.toml"))

        backend = create_topic_backend()

        assert isinstance(backend, TelegramTopicBackend)
        assert backend.name == "telegram"

    @patch("yee88.topics.factory.load_settings")
    def test_creates_discord_backend(self, mock_load_settings: MagicMock) -> None:
        mock_settings = MagicMock()
        mock_settings.transport = "discord"
        mock_settings.transports.model_extra = {
            "discord": {
                "bot_token": "token",
                "channel_id": 123,
            }
        }
        mock_load_settings.return_value = (mock_settings, Path("/tmp/config.toml"))

        backend = create_topic_backend()

        assert isinstance(backend, DiscordTopicBackend)
        assert backend.name == "discord"

    @patch("yee88.topics.factory.load_settings")
    def test_raises_for_unsupported_transport(self, mock_load_settings: MagicMock) -> None:
        from yee88.config import ConfigError

        mock_settings = MagicMock()
        mock_settings.transport = "unknown"
        mock_load_settings.return_value = (mock_settings, Path("/tmp/config.toml"))

        with pytest.raises(ConfigError):
            create_topic_backend()

    @patch("yee88.topics.factory.load_settings")
    def test_raises_when_telegram_topics_disabled(self, mock_load_settings: MagicMock) -> None:
        from yee88.config import ConfigError

        mock_settings = MagicMock()
        mock_settings.transport = "telegram"
        mock_settings.transports.telegram.topics.enabled = False
        mock_load_settings.return_value = (mock_settings, Path("/tmp/config.toml"))

        with pytest.raises(ConfigError):
            create_topic_backend()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
