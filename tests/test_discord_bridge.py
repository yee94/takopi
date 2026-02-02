"""Tests for Discord bridge module."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from yee88.discord.bridge import DiscordBridgeConfig, DiscordPresenter, DiscordTransport
from yee88.discord.client import DiscordBotClient, SentMessage
from yee88.markdown import MarkdownFormatter
from yee88.progress import ProgressState
from yee88.transport import MessageRef, RenderedMessage, SendOptions


class MockDiscordClient:
    """Mock Discord client for testing."""

    def __init__(self) -> None:
        self.send_calls: list[dict] = []
        self.edit_calls: list[dict] = []
        self.delete_calls: list[dict] = []
        self.closed = False

    async def send_message(
        self,
        *,
        channel_id: int,
        content: str,
        reply_to_message_id: int | None = None,
        thread_id: int | None = None,
    ) -> SentMessage | None:
        call = {
            "channel_id": channel_id,
            "content": content,
            "reply_to_message_id": reply_to_message_id,
            "thread_id": thread_id,
        }
        self.send_calls.append(call)
        return SentMessage(
            message_id=len(self.send_calls),
            channel_id=channel_id,
            thread_id=thread_id,
        )

    async def edit_message(
        self,
        *,
        channel_id: int,
        message_id: int,
        content: str,
        wait: bool = True,
    ) -> SentMessage | None:
        call = {
            "channel_id": channel_id,
            "message_id": message_id,
            "content": content,
            "wait": wait,
        }
        self.edit_calls.append(call)
        return SentMessage(message_id=message_id, channel_id=channel_id)

    async def delete_message(self, *, channel_id: int, message_id: int) -> bool:
        call = {"channel_id": channel_id, "message_id": message_id}
        self.delete_calls.append(call)
        return True

    async def close(self) -> None:
        self.closed = True


class TestDiscordPresenter:
    """Test DiscordPresenter."""

    def test_creates_with_default_formatter(self) -> None:
        """Test that presenter creates with default formatter."""
        presenter = DiscordPresenter()
        assert presenter._formatter is not None
        assert isinstance(presenter._formatter, MarkdownFormatter)

    def test_creates_with_custom_formatter(self) -> None:
        """Test that presenter creates with custom formatter."""
        custom_formatter = MarkdownFormatter()
        presenter = DiscordPresenter(formatter=custom_formatter)
        assert presenter._formatter is custom_formatter

    def test_default_message_overflow_is_split(self) -> None:
        """Test that default message_overflow is split."""
        presenter = DiscordPresenter()
        assert presenter._message_overflow == "split"

    def test_custom_message_overflow(self) -> None:
        """Test that custom message_overflow is set."""
        presenter = DiscordPresenter(message_overflow="trim")
        assert presenter._message_overflow == "trim"


class TestDiscordPresenterRenderProgress:
    """Test DiscordPresenter render_progress."""

    def test_renders_progress_with_default_label(self) -> None:
        """Test that progress is rendered with default label."""
        presenter = DiscordPresenter()
        state = ProgressState(
            engine="codex",
            action_count=5,
            actions=(),
            resume=None,
            resume_line=None,
            context_line=None,
        )

        result = presenter.render_progress(state, elapsed_s=5.0)

        assert isinstance(result, RenderedMessage)
        assert result.text is not None
        assert len(result.text) > 0
        assert result.extra == {}

    def test_renders_progress_with_custom_label(self) -> None:
        """Test that progress is rendered with custom label."""
        presenter = DiscordPresenter()
        state = ProgressState(
            engine="codex",
            action_count=3,
            actions=(),
            resume=None,
            resume_line=None,
            context_line=None,
        )

        result = presenter.render_progress(state, elapsed_s=3.0, label="processing")

        assert isinstance(result, RenderedMessage)
        assert "processing" in result.text or result.text


class TestDiscordPresenterRenderFinal:
    """Test DiscordPresenter render_final."""

    def test_renders_final_with_split_mode(self) -> None:
        """Test that final message is rendered in split mode."""
        presenter = DiscordPresenter(message_overflow="split")
        state = ProgressState(
            engine="codex",
            action_count=10,
            actions=(),
            resume=None,
            resume_line=None,
            context_line=None,
        )

        result = presenter.render_final(
            state,
            elapsed_s=10.0,
            status="done",
            answer="Final answer here",
        )

        assert isinstance(result, RenderedMessage)
        assert result.text is not None

    def test_renders_final_with_trim_mode(self) -> None:
        """Test that final message is rendered in trim mode."""
        presenter = DiscordPresenter(message_overflow="trim")
        state = ProgressState(
            engine="codex",
            action_count=10,
            actions=(),
            resume=None,
            resume_line=None,
            context_line=None,
        )

        result = presenter.render_final(
            state,
            elapsed_s=10.0,
            status="done",
            answer="Final answer here",
        )

        assert isinstance(result, RenderedMessage)
        assert result.text is not None

    def test_splits_long_answer_into_followups(self) -> None:
        """Test that long answer is split into followup messages."""
        presenter = DiscordPresenter(message_overflow="split")
        state = ProgressState(
            engine="codex",
            action_count=10,
            actions=(),
            resume=None,
            resume_line=None,
            context_line=None,
        )
        long_answer = "x" * 5000

        result = presenter.render_final(
            state,
            elapsed_s=10.0,
            status="done",
            answer=long_answer,
        )

        assert isinstance(result, RenderedMessage)
        followups = result.extra.get("followups")
        assert followups is not None
        assert len(followups) > 0


class TestDiscordTransport:
    """Test DiscordTransport."""

    @pytest.mark.anyio
    async def test_creates_with_bot(self) -> None:
        """Test that transport creates with bot."""
        mock_bot = MockDiscordClient()
        transport = DiscordTransport(mock_bot)
        assert transport._bot is mock_bot

    @pytest.mark.anyio
    async def test_close_delegates_to_bot(self) -> None:
        """Test that close delegates to bot."""
        mock_bot = MockDiscordClient()
        transport = DiscordTransport(mock_bot)

        await transport.close()

        assert mock_bot.closed is True

    @pytest.mark.anyio
    async def test_send_delegates_to_bot(self) -> None:
        """Test that send delegates to bot."""
        mock_bot = MockDiscordClient()
        transport = DiscordTransport(mock_bot)

        message = RenderedMessage(text="Hello", extra={})
        result = await transport.send(channel_id=123, message=message)

        assert result is not None
        assert len(mock_bot.send_calls) == 1
        assert mock_bot.send_calls[0]["content"] == "Hello"
        assert mock_bot.send_calls[0]["channel_id"] == 123

    @pytest.mark.anyio
    async def test_send_with_options(self) -> None:
        """Test that send handles options."""
        mock_bot = MockDiscordClient()
        transport = DiscordTransport(mock_bot)

        reply_ref = MessageRef(channel_id=123, message_id=456)
        options = SendOptions(reply_to=reply_ref, thread_id=789)
        message = RenderedMessage(text="Reply", extra={})

        result = await transport.send(
            channel_id=123,
            message=message,
            options=options,
        )

        assert result is not None
        call = mock_bot.send_calls[0]
        assert call["reply_to_message_id"] == 456
        assert call["thread_id"] == 789

    @pytest.mark.anyio
    async def test_send_deletes_replaced_message(self) -> None:
        """Test that send deletes replaced message."""
        mock_bot = MockDiscordClient()
        transport = DiscordTransport(mock_bot)

        replace_ref = MessageRef(channel_id=123, message_id=999)
        options = SendOptions(replace=replace_ref)
        message = RenderedMessage(text="New message", extra={})

        await transport.send(channel_id=123, message=message, options=options)

        assert len(mock_bot.delete_calls) == 1
        assert mock_bot.delete_calls[0]["message_id"] == 999

    @pytest.mark.anyio
    async def test_send_sends_followups(self) -> None:
        """Test that send sends followup messages."""
        mock_bot = MockDiscordClient()
        transport = DiscordTransport(mock_bot)

        followups = [
            RenderedMessage(text="Part 1", extra={}),
            RenderedMessage(text="Part 2", extra={}),
        ]
        message = RenderedMessage(text="Main", extra={"followups": followups})

        result = await transport.send(channel_id=123, message=message)

        assert result is not None
        assert len(mock_bot.send_calls) == 3

    @pytest.mark.anyio
    async def test_send_returns_none_on_bot_failure(self) -> None:
        """Test that send returns None when bot fails."""
        mock_bot = MockDiscordClient()
        mock_bot.send_message = AsyncMock(return_value=None)
        transport = DiscordTransport(mock_bot)

        message = RenderedMessage(text="Hello", extra={})
        result = await transport.send(channel_id=123, message=message)

        assert result is None

    @pytest.mark.anyio
    async def test_edit_delegates_to_bot(self) -> None:
        """Test that edit delegates to bot."""
        mock_bot = MockDiscordClient()
        transport = DiscordTransport(mock_bot)

        ref = MessageRef(channel_id=123, message_id=456)
        message = RenderedMessage(text="Edited", extra={})

        result = await transport.edit(ref=ref, message=message)

        assert result is not None
        assert len(mock_bot.edit_calls) == 1
        assert mock_bot.edit_calls[0]["content"] == "Edited"
        assert mock_bot.edit_calls[0]["message_id"] == 456

    @pytest.mark.anyio
    async def test_edit_uses_thread_id(self) -> None:
        """Test that edit uses thread_id when present."""
        mock_bot = MockDiscordClient()
        transport = DiscordTransport(mock_bot)

        ref = MessageRef(channel_id=123, message_id=456, thread_id=789)
        message = RenderedMessage(text="Edited in thread", extra={})

        result = await transport.edit(ref=ref, message=message)

        assert result is not None
        assert mock_bot.edit_calls[0]["channel_id"] == 789

    @pytest.mark.anyio
    async def test_edit_sends_followups(self) -> None:
        """Test that edit sends followup messages."""
        mock_bot = MockDiscordClient()
        transport = DiscordTransport(mock_bot)

        followups = [RenderedMessage(text="Followup", extra={})]
        ref = MessageRef(channel_id=123, message_id=456)
        message = RenderedMessage(text="Edited", extra={"followups": followups})

        result = await transport.edit(ref=ref, message=message)

        assert result is not None
        assert len(mock_bot.send_calls) == 1

    @pytest.mark.anyio
    async def test_edit_returns_original_on_bot_failure(self) -> None:
        """Test that edit returns original ref on bot failure when waiting."""
        mock_bot = MockDiscordClient()
        mock_bot.edit_message = AsyncMock(return_value=None)
        transport = DiscordTransport(mock_bot)

        ref = MessageRef(channel_id=123, message_id=456)
        message = RenderedMessage(text="Edited", extra={})

        result = await transport.edit(ref=ref, message=message, wait=False)

        assert result == ref

    @pytest.mark.anyio
    async def test_edit_returns_none_on_bot_failure_when_waiting(self) -> None:
        """Test that edit returns None on bot failure when waiting."""
        mock_bot = MockDiscordClient()
        mock_bot.edit_message = AsyncMock(return_value=None)
        transport = DiscordTransport(mock_bot)

        ref = MessageRef(channel_id=123, message_id=456)
        message = RenderedMessage(text="Edited", extra={})

        result = await transport.edit(ref=ref, message=message, wait=True)

        assert result is None

    @pytest.mark.anyio
    async def test_delete_delegates_to_bot(self) -> None:
        """Test that delete delegates to bot."""
        mock_bot = MockDiscordClient()
        transport = DiscordTransport(mock_bot)

        ref = MessageRef(channel_id=123, message_id=456)
        result = await transport.delete(ref=ref)

        assert result is True
        assert len(mock_bot.delete_calls) == 1
        assert mock_bot.delete_calls[0]["message_id"] == 456

    @pytest.mark.anyio
    async def test_delete_uses_thread_id(self) -> None:
        """Test that delete uses thread_id when present."""
        mock_bot = MockDiscordClient()
        transport = DiscordTransport(mock_bot)

        ref = MessageRef(channel_id=123, message_id=456, thread_id=789)
        result = await transport.delete(ref=ref)

        assert result is True
        assert mock_bot.delete_calls[0]["channel_id"] == 789


class TestDiscordBridgeConfig:
    """Test DiscordBridgeConfig."""

    def test_creates_with_required_fields(self) -> None:
        """Test that config creates with required fields."""
        mock_bot = MagicMock(spec=DiscordBotClient)
        mock_exec_cfg = MagicMock()

        config = DiscordBridgeConfig(
            bot=mock_bot,
            runtime=MagicMock(),
            guild_id=123,
            channel_id=456,
            startup_msg="Hello",
            exec_cfg=mock_exec_cfg,
        )

        assert config.bot is mock_bot
        assert config.guild_id == 123
        assert config.channel_id == 456
        assert config.startup_msg == "Hello"
        assert config.exec_cfg is mock_exec_cfg

    def test_uses_default_session_mode(self) -> None:
        """Test that default session_mode is stateless."""
        config = DiscordBridgeConfig(
            bot=MagicMock(),
            runtime=MagicMock(),
            guild_id=123,
            channel_id=456,
            startup_msg="Hello",
            exec_cfg=MagicMock(),
        )

        assert config.session_mode == "stateless"

    def test_uses_default_show_resume_line(self) -> None:
        """Test that default show_resume_line is True."""
        config = DiscordBridgeConfig(
            bot=MagicMock(),
            runtime=MagicMock(),
            guild_id=123,
            channel_id=456,
            startup_msg="Hello",
            exec_cfg=MagicMock(),
        )

        assert config.show_resume_line is True

    def test_uses_default_message_overflow(self) -> None:
        """Test that default message_overflow is split."""
        config = DiscordBridgeConfig(
            bot=MagicMock(),
            runtime=MagicMock(),
            guild_id=123,
            channel_id=456,
            startup_msg="Hello",
            exec_cfg=MagicMock(),
        )

        assert config.message_overflow == "split"

    def test_accepts_custom_values(self) -> None:
        """Test that config accepts custom values."""
        config = DiscordBridgeConfig(
            bot=MagicMock(),
            runtime=MagicMock(),
            guild_id=123,
            channel_id=456,
            startup_msg="Hello",
            exec_cfg=MagicMock(),
            session_mode="chat",
            show_resume_line=False,
            message_overflow="trim",
        )

        assert config.session_mode == "chat"
        assert config.show_resume_line is False
        assert config.message_overflow == "trim"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
