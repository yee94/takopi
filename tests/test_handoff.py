"""Tests for handoff backend implementations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yee88.handoff import HandoffBackend, HandoffResult, SessionContext
from yee88.handoff.discord import DiscordHandoffBackend
from yee88.handoff.factory import create_handoff_backend
from yee88.handoff.telegram import TelegramHandoffBackend


class TestHandoffBackendInterface:
    """Test that all backends implement the interface correctly."""

    def test_telegram_backend_has_name(self) -> None:
        backend = TelegramHandoffBackend("token", 123)
        assert backend.name == "telegram"

    def test_discord_backend_has_name(self) -> None:
        backend = DiscordHandoffBackend("token", 123)
        assert backend.name == "discord"

    def test_telegram_backend_is_available_with_config(self) -> None:
        backend = TelegramHandoffBackend("token", 123)
        assert backend.is_available() is True

    def test_telegram_backend_not_available_without_token(self) -> None:
        backend = TelegramHandoffBackend("", 123)
        assert backend.is_available() is False

    def test_discord_backend_is_available_with_config(self) -> None:
        backend = DiscordHandoffBackend("token", 123)
        assert backend.is_available() is True

    def test_discord_backend_not_available_without_token(self) -> None:
        backend = DiscordHandoffBackend("", 123)
        assert backend.is_available() is False


class TestTelegramHandoffBackend:
    """Test TelegramHandoffBackend implementation."""

    def test_format_messages_with_project(self) -> None:
        backend = TelegramHandoffBackend("token", 123)
        messages = [{"role": "user", "text": "Hello"}, {"role": "assistant", "text": "Hi there"}]

        result = backend.format_messages(messages, "sess-123", "myproject")

        assert "📱 **会话接力**" in result
        assert "📁 项目: `myproject`" in result
        assert "🔗 Session: `sess-123`" in result
        assert "👤 **user**" in result
        assert "🤖 **assistant**" in result

    def test_format_messages_without_project(self) -> None:
        backend = TelegramHandoffBackend("token", 123)
        messages = [{"role": "user", "text": "Hello"}]

        result = backend.format_messages(messages, "sess-123", None)

        assert "📱 **会话接力**" in result
        assert "🔗 Session: `sess-123`" in result

    def test_format_messages_truncates_long_text(self) -> None:
        backend = TelegramHandoffBackend("token", 123)
        messages = [{"role": "user", "text": "x" * 1000}]

        result = backend.format_messages(messages, "sess-123", "myproject")

        assert "..." in result

    @pytest.mark.anyio
    async def test_handoff_creates_topic_and_sends_message(self) -> None:
        backend = TelegramHandoffBackend("token", 123456)
        context = SessionContext(
            session_id="sess-123",
            project="myproject",
            messages=[{"role": "user", "text": "Hello"}],
        )

        with patch("yee88.handoff.telegram.TelegramClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_topic_result = MagicMock()
            mock_topic_result.message_thread_id = 789
            mock_client.create_forum_topic = AsyncMock(return_value=mock_topic_result)
            mock_client.send_message = AsyncMock(return_value=MagicMock())
            mock_client.close = AsyncMock()

            with patch("yee88.handoff.telegram.TopicStateStore") as mock_store_class:
                mock_store = MagicMock()
                mock_store_class.return_value = mock_store
                mock_store.set_context = AsyncMock()
                mock_store.set_session_resume = AsyncMock()

                result = await backend.handoff(
                    context=context,
                    config_path=Path("/tmp/config.toml"),
                )

                assert result.success is True
                assert result.thread_id == 789
                mock_client.create_forum_topic.assert_called_once_with(123456, "📱 myproject handoff")

    @pytest.mark.anyio
    async def test_handoff_returns_failure_on_topic_creation_error(self) -> None:
        backend = TelegramHandoffBackend("token", 123456)
        context = SessionContext(
            session_id="sess-123",
            project="myproject",
            messages=[{"role": "user", "text": "Hello"}],
        )

        with patch("yee88.handoff.telegram.TelegramClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.create_forum_topic = AsyncMock(return_value=None)
            mock_client.close = AsyncMock()

            result = await backend.handoff(
                context=context,
                config_path=Path("/tmp/config.toml"),
            )

            assert result.success is False
            assert result.thread_id is None


class TestDiscordHandoffBackend:
    """Test DiscordHandoffBackend implementation."""

    def test_format_messages_with_project(self) -> None:
        backend = DiscordHandoffBackend("token", 123)
        messages = [{"role": "user", "text": "Hello"}]

        result = backend.format_messages(messages, "sess-123", "myproject")

        assert "📱 **会话接力**" in result
        assert "💡 直接在此 Thread 发消息即可继续对话" in result

    def test_state_file_path(self, tmp_path: Path) -> None:
        backend = DiscordHandoffBackend("token", 123)
        config_path = tmp_path / "config.toml"
        state_path = backend._get_state_path(config_path)
        assert state_path == tmp_path / "discord_handoffs.json"

    def test_save_and_load_handoff_state(self, tmp_path: Path) -> None:
        backend = DiscordHandoffBackend("token", 123)
        config_path = tmp_path / "config.toml"

        backend._save_handoff_state(
            config_path=config_path,
            thread_id=456,
            session_id="sess-123",
            project="myproject",
        )

        state = backend._load_state(config_path)
        assert len(state["handoffs"]) == 1
        assert state["handoffs"][0]["thread_id"] == 456
        assert state["handoffs"][0]["session_id"] == "sess-123"


class TestCreateHandoffBackend:
    """Test factory function create_handoff_backend."""

    @patch("yee88.handoff.factory.load_settings")
    def test_creates_telegram_backend(self, mock_load_settings: MagicMock) -> None:
        mock_settings = MagicMock()
        mock_settings.transport = "telegram"
        mock_settings.transports.telegram.bot_token = "token"
        mock_settings.transports.telegram.chat_id = 123
        mock_settings.transports.telegram.topics.enabled = True
        mock_load_settings.return_value = (mock_settings, Path("/tmp/config.toml"))

        backend = create_handoff_backend()

        assert isinstance(backend, TelegramHandoffBackend)
        assert backend.name == "telegram"

    @patch("yee88.handoff.factory.load_settings")
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

        backend = create_handoff_backend()

        assert isinstance(backend, DiscordHandoffBackend)
        assert backend.name == "discord"

    @patch("yee88.handoff.factory.load_settings")
    def test_raises_for_unsupported_transport(self, mock_load_settings: MagicMock) -> None:
        from yee88.config import ConfigError

        mock_settings = MagicMock()
        mock_settings.transport = "unknown"
        mock_load_settings.return_value = (mock_settings, Path("/tmp/config.toml"))

        with pytest.raises(ConfigError):
            create_handoff_backend()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
