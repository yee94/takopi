"""Tests for Discord render module."""

from __future__ import annotations

import pytest

from yee88.discord.render import (
    MAX_BODY_CHARS,
    MAX_MESSAGE_CHARS,
    _close_fence_chunk,
    _ensure_trailing_newline,
    _FenceState,
    _reopen_fence_prefix,
    _scan_fence_state,
    _split_block,
    _split_long_line,
    _update_fence_state,
    prepare_discord,
    prepare_discord_multi,
    split_markdown_body,
    trim_body,
)
from yee88.markdown import MarkdownParts


class TestFenceState:
    """Test code fence state tracking."""

    def test_update_fence_state_opens_fence(self) -> None:
        """Test that fence state opens when encountering a code fence."""
        state = _update_fence_state("```python", None)
        assert state is not None
        assert state.fence == "```"
        assert state.indent == ""
        assert state.header == "```python"

    def test_update_fence_state_closes_fence(self) -> None:
        """Test that fence state closes when encountering matching fence."""
        initial = _FenceState(fence="```", indent="", header="```python")
        state = _update_fence_state("```", initial)
        assert state is None

    def test_update_fence_state_preserves_indent(self) -> None:
        """Test that fence state preserves indentation."""
        state = _update_fence_state("    ```json", None)
        assert state is not None
        assert state.fence == "```"
        assert state.indent == "    "

    def test_update_fence_state_different_fence_type(self) -> None:
        """Test that backtick fence doesn't close tilde fence."""
        initial = _FenceState(fence="~~~", indent="", header="~~~")
        state = _update_fence_state("```", initial)
        # Different fence type, should not close
        assert state is not None

    def test_update_fence_state_longer_fence_closes(self) -> None:
        """Test that longer fence closes shorter fence."""
        initial = _FenceState(fence="``", indent="", header="``")
        state = _update_fence_state("```", initial)
        # Longer fence of same type closes it
        assert state is None


class TestScanFenceState:
    """Test fence state scanning across multiple lines."""

    def test_scan_empty_text(self) -> None:
        """Test scanning empty text."""
        state = _scan_fence_state("", None)
        assert state is None

    def test_scan_single_fence(self) -> None:
        """Test scanning text with single fence."""
        text = "```python\ncode\n```"
        state = _scan_fence_state(text, None)
        assert state is None  # Fence is closed

    def test_scan_unclosed_fence(self) -> None:
        """Test scanning text with unclosed fence."""
        text = "```python\ncode\nmore code"
        state = _scan_fence_state(text, None)
        assert state is not None
        assert state.fence == "```"


class TestEnsureTrailingNewline:
    """Test trailing newline helper."""

    def test_adds_newline_when_missing(self) -> None:
        """Test that newline is added when missing."""
        result = _ensure_trailing_newline("hello")
        assert result == "hello\n"

    def test_preserves_existing_newline(self) -> None:
        """Test that existing newline is preserved."""
        result = _ensure_trailing_newline("hello\n")
        assert result == "hello\n"

    def test_preserves_crlf(self) -> None:
        """Test that CRLF is preserved."""
        result = _ensure_trailing_newline("hello\r\n")
        assert result == "hello\r\n"


class TestCloseFenceChunk:
    """Test fence chunk closing."""

    def test_closes_fence(self) -> None:
        """Test that fence is properly closed."""
        state = _FenceState(fence="```", indent="  ", header="```python")
        result = _close_fence_chunk("code", state)
        assert result == "code\n  ```\n"


class TestReopenFencePrefix:
    """Test fence reopening."""

    def test_reopens_fence(self) -> None:
        """Test that fence header is returned for reopening."""
        state = _FenceState(fence="```", indent="", header="```python")
        result = _reopen_fence_prefix(state)
        assert result == "```python\n"


class TestSplitLongLine:
    """Test long line splitting."""

    def test_short_line_unchanged(self) -> None:
        """Test that short lines are not split."""
        result = _split_long_line("hello", max_chars=100)
        assert result == ["hello"]

    def test_long_line_split(self) -> None:
        """Test that long lines are split."""
        line = "a" * 150
        result = _split_long_line(line, max_chars=50)
        assert len(result) == 3
        assert all(len(r) <= 50 for r in result)

    def test_preserves_newline_ending(self) -> None:
        """Test that newline endings are preserved on last chunk."""
        line = "a" * 100 + "\n"
        result = _split_long_line(line, max_chars=50)
        assert result[-1].endswith("\n")


class TestSplitBlock:
    """Test block splitting."""

    def test_short_block_unchanged(self) -> None:
        """Test that short blocks are not split."""
        result = _split_block("hello", max_chars=100)
        assert result == ["hello"]

    def test_long_block_split(self) -> None:
        """Test that long blocks are split at boundaries."""
        block = "line1\nline2\nline3\n" + "x" * 200
        result = _split_block(block, max_chars=50)
        assert len(result) > 1


class TestSplitMarkdownBody:
    """Test markdown body splitting."""

    def test_empty_body(self) -> None:
        """Test that empty body returns empty list."""
        result = split_markdown_body("", max_chars=1000)
        assert result == []

    def test_whitespace_only_body(self) -> None:
        """Test that whitespace-only body returns empty list."""
        result = split_markdown_body("   \n  ", max_chars=1000)
        assert result == []

    def test_short_body_unchanged(self) -> None:
        """Test that short body is not split."""
        result = split_markdown_body("Hello world", max_chars=1000)
        assert result == ["Hello world"]

    def test_respects_code_fences(self) -> None:
        """Test that code fences are respected when splitting."""
        body = "```python\n" + "x" * 3000 + "\n```"
        result = split_markdown_body(body, max_chars=1000)
        # Should have multiple chunks with fences properly closed/reopened
        assert len(result) > 1
        # All chunks should start or end properly
        for chunk in result:
            assert chunk.strip()  # Non-empty after stripping

    def test_splits_at_paragraphs(self) -> None:
        """Test that splits happen at paragraph boundaries."""
        body = "Para 1\n\nPara 2\n\nPara 3"
        result = split_markdown_body(body, max_chars=10)
        # Should split at paragraph boundaries
        assert len(result) >= 3


class TestTrimBody:
    """Test body trimming."""

    def test_none_returns_none(self) -> None:
        """Test that None returns None."""
        result = trim_body(None)
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        """Test that empty string returns None."""
        result = trim_body("")
        assert result is None

    def test_short_body_unchanged(self) -> None:
        """Test that short body is not trimmed."""
        result = trim_body("Hello world", max_chars=100)
        assert result == "Hello world"

    def test_long_body_trimmed(self) -> None:
        """Test that long body is trimmed with ellipsis."""
        long_text = "x" * 2000
        result = trim_body(long_text, max_chars=100)
        assert result is not None
        assert len(result) <= 100
        assert result.endswith("…")

    def test_uses_default_max_chars(self) -> None:
        """Test that default MAX_BODY_CHARS is used."""
        body = "x" * (MAX_BODY_CHARS + 100)
        result = trim_body(body)
        assert result is not None
        assert len(result) <= MAX_BODY_CHARS


class TestPrepareDiscord:
    """Test Discord message preparation."""

    def test_prepares_simple_message(self) -> None:
        """Test preparing a simple message."""
        parts = MarkdownParts(header="Hello", body="World", footer="Bye")
        result = prepare_discord(parts)
        assert "Hello" in result
        assert "World" in result
        assert "Bye" in result

    def test_trims_long_body(self) -> None:
        """Test that long body is trimmed."""
        long_body = "x" * 2000
        parts = MarkdownParts(header="Header", body=long_body, footer=None)
        result = prepare_discord(parts)
        assert len(result) <= MAX_MESSAGE_CHARS

    def test_handles_none_body(self) -> None:
        """Test handling None body."""
        parts = MarkdownParts(header="Header", body=None, footer="Footer")
        result = prepare_discord(parts)
        assert "Header" in result
        assert "Footer" in result


class TestPrepareDiscordMulti:
    """Test multi-message Discord preparation."""

    def test_single_short_message(self) -> None:
        """Test that short message returns single item."""
        parts = MarkdownParts(header="Hello", body="World", footer=None)
        result = prepare_discord_multi(parts, max_body_chars=1000)
        assert len(result) == 1
        assert "Hello" in result[0]

    def test_splits_long_body(self) -> None:
        """Test that long body is split into multiple messages."""
        long_body = "x" * 5000
        parts = MarkdownParts(header="Header", body=long_body, footer=None)
        result = prepare_discord_multi(parts, max_body_chars=1000)
        assert len(result) > 1
        # First message has header
        assert "Header" in result[0]
        # Continuation messages have continuation indicator
        assert any("continued" in msg for msg in result[1:])

    def test_empty_body_returns_single_message(self) -> None:
        """Test that empty body returns single message."""
        parts = MarkdownParts(header="Hello", body=None, footer=None)
        result = prepare_discord_multi(parts, max_body_chars=1000)
        assert len(result) == 1

    def test_whitespace_body_returns_single_message(self) -> None:
        """Test that whitespace-only body returns single empty message."""
        parts = MarkdownParts(header="Hello", body="   \n  ", footer=None)
        result = prepare_discord_multi(parts, max_body_chars=1000)
        assert len(result) == 1

    def test_continuation_formatting(self) -> None:
        """Test that continuation messages are properly formatted."""
        long_body = "x" * 3000
        parts = MarkdownParts(header="Header", body=long_body, footer="Footer")
        result = prepare_discord_multi(parts, max_body_chars=1000)
        # Check first message
        assert result[0].startswith("Header")
        # Check continuation messages have proper header
        for i, msg in enumerate(result[1:-1], start=2):
            assert f"continued ({i}/{len(result)})" in msg
        # Last message has footer
        assert result[-1].endswith("Footer")


class TestConstants:
    """Test module constants."""

    def test_max_message_chars(self) -> None:
        """Test that MAX_MESSAGE_CHARS is 2000."""
        assert MAX_MESSAGE_CHARS == 2000

    def test_max_body_chars(self) -> None:
        """Test that MAX_BODY_CHARS is 1500."""
        assert MAX_BODY_CHARS == 1500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
