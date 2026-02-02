"""Tests for Discord client module."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yee88.discord.client import DiscordBotClient, SentMessage


class TestDiscordBotClientInitialization:
    """Test DiscordBotClient initialization."""

    def test_creates_client_with_token(self) -> None:
        """Test that client is created with token."""
        client = DiscordBotClient("test-token")
        assert client._token == "test-token"
        assert client._guild_id is None

    def test_creates_client_with_guild_id(self) -> None:
        """Test that client is created with guild_id."""
        client = DiscordBotClient("test-token", guild_id=123456)
        assert client._guild_id == 123456

    def test_creates_client_with_custom_rps(self) -> None:
        """Test that client is created with custom rate limit."""
        client = DiscordBotClient("test-token", channel_rps=2.0)
        assert client._channel_interval == 0.5

    def test_creates_client_with_zero_rps(self) -> None:
        """Test that client handles zero rate limit."""
        client = DiscordBotClient("test-token", channel_rps=0)
        assert client._channel_interval == 0.0


class TestDiscordBotClientUserProperty:
    """Test DiscordBotClient user property."""

    def test_user_property_returns_none_before_bot_created(self) -> None:
        """Test that user property returns None before bot is created."""
        client = DiscordBotClient("test-token")
        assert client.user is None


class TestDiscordBotClientMessageHandler:
    """Test DiscordBotClient message handler."""

    def test_set_message_handler(self) -> None:
        """Test that message handler can be set."""
        client = DiscordBotClient("test-token")

        async def handler(message: Any) -> None:
            pass

        client.set_message_handler(handler)
        assert client._message_handler is handler


class TestDiscordBotClientClose:
    """Test DiscordBotClient close method."""

    @pytest.mark.anyio
    async def test_close_without_bot_does_nothing(self) -> None:
        """Test that close does nothing when bot is not created."""
        client = DiscordBotClient("test-token")
        await client.close()
        assert client._bot is None


class TestDiscordBotClientSendMessage:
    """Test DiscordBotClient send_message method."""

    @pytest.mark.anyio
    async def test_send_message_returns_none_if_channel_not_found(self) -> None:
        """Test that send_message returns None if channel not found."""
        client = DiscordBotClient("test-token")
        mock_bot = MagicMock()
        client._bot = mock_bot

        import discord

        mock_bot.get_channel = MagicMock(return_value=None)
        mock_bot.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        result = await client.send_message(
            channel_id=999,
            content="Hello",
        )

        assert result is None

    @pytest.mark.anyio
    async def test_send_message_returns_none_if_not_messageable(self) -> None:
        """Test that send_message returns None if channel is not messageable."""
        client = DiscordBotClient("test-token")
        mock_bot = MagicMock()
        client._bot = mock_bot

        mock_bot.get_channel = MagicMock(return_value=MagicMock())

        result = await client.send_message(
            channel_id=123,
            content="Hello",
        )

        assert result is None


class TestDiscordBotClientEditMessage:
    """Test DiscordBotClient edit_message method."""

    @pytest.mark.anyio
    async def test_edit_message_returns_none_if_channel_not_found(self) -> None:
        """Test that edit_message returns None if channel not found."""
        client = DiscordBotClient("test-token")
        mock_bot = MagicMock()
        client._bot = mock_bot

        import discord

        mock_bot.get_channel = MagicMock(return_value=None)
        mock_bot.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        result = await client.edit_message(
            channel_id=999,
            message_id=456,
            content="Edited",
        )

        assert result is None


class TestDiscordBotClientDeleteMessage:
    """Test DiscordBotClient delete_message method."""

    @pytest.mark.anyio
    async def test_delete_message_returns_false_if_channel_not_found(self) -> None:
        """Test that delete_message returns False if channel not found."""
        client = DiscordBotClient("test-token")
        mock_bot = MagicMock()
        client._bot = mock_bot

        import discord

        mock_bot.get_channel = MagicMock(return_value=None)
        mock_bot.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        result = await client.delete_message(
            channel_id=999,
            message_id=456,
        )

        assert result is False


class TestDiscordBotClientGetGuild:
    """Test DiscordBotClient get_guild method."""

    def test_get_guild_delegates_to_bot(self) -> None:
        """Test that get_guild delegates to bot."""
        client = DiscordBotClient("test-token")
        mock_bot = MagicMock()
        client._bot = mock_bot

        mock_guild = MagicMock()
        mock_guild.id = 123
        mock_bot.get_guild = MagicMock(return_value=mock_guild)

        result = client.get_guild(123)

        assert result == mock_guild
        mock_bot.get_guild.assert_called_once_with(123)


class TestDiscordBotClientGetChannel:
    """Test DiscordBotClient get_channel method."""

    def test_get_channel_delegates_to_bot(self) -> None:
        """Test that get_channel delegates to bot."""
        client = DiscordBotClient("test-token")
        mock_bot = MagicMock()
        client._bot = mock_bot

        import discord

        mock_channel = MagicMock(spec=discord.abc.GuildChannel)
        mock_bot.get_channel = MagicMock(return_value=mock_channel)

        result = client.get_channel(123)

        assert result == mock_channel

    def test_get_channel_returns_none_for_non_guild_channel(self) -> None:
        """Test that get_channel returns None for non-guild channel."""
        client = DiscordBotClient("test-token")
        mock_bot = MagicMock()
        client._bot = mock_bot

        mock_bot.get_channel = MagicMock(return_value=MagicMock())

        result = client.get_channel(123)

        assert result is None


class TestSentMessage:
    """Test SentMessage dataclass."""

    def test_sent_message_creation(self) -> None:
        """Test SentMessage creation."""
        msg = SentMessage(message_id=123, channel_id=456)
        assert msg.message_id == 123
        assert msg.channel_id == 456
        assert msg.thread_id is None

    def test_sent_message_with_thread_id(self) -> None:
        """Test SentMessage with thread_id."""
        msg = SentMessage(message_id=123, channel_id=456, thread_id=789)
        assert msg.thread_id == 789


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
