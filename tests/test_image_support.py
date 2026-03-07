"""Tests for Markdown image extraction and Telegram photo URL sending."""

from __future__ import annotations

from typing import Any

import pytest

from yee88.markdown import MarkdownFormatter
from yee88.progress import ProgressState
from yee88.telegram.bridge import TelegramPresenter, TelegramTransport
from yee88.telegram.render import extract_image_urls
from yee88.transport import MessageRef, RenderedMessage, SendOptions
from tests.telegram_fakes import FakeBot


# ---------------------------------------------------------------------------
# extract_image_urls tests
# ---------------------------------------------------------------------------


class TestExtractImageUrls:
    def test_no_images(self) -> None:
        text = "Hello world, no images here."
        cleaned, urls = extract_image_urls(text)
        assert cleaned == text
        assert urls == []

    def test_single_image(self) -> None:
        text = "Before ![alt](https://example.com/img.png) after"
        cleaned, urls = extract_image_urls(text)
        assert urls == ["https://example.com/img.png"]
        assert "![" not in cleaned
        assert "example.com" not in cleaned
        assert "Before" in cleaned
        assert "after" in cleaned

    def test_multiple_images(self) -> None:
        text = (
            "![a](https://example.com/1.png)\n\n"
            "Some text\n\n"
            "![b](https://example.com/2.jpg)"
        )
        cleaned, urls = extract_image_urls(text)
        assert urls == ["https://example.com/1.png", "https://example.com/2.jpg"]
        assert "![" not in cleaned
        assert "Some text" in cleaned

    def test_image_only(self) -> None:
        text = "![chart](https://example.com/chart.png)"
        cleaned, urls = extract_image_urls(text)
        assert urls == ["https://example.com/chart.png"]
        assert cleaned == ""

    def test_blank_lines_collapsed(self) -> None:
        text = "Before\n\n![img](https://example.com/x.png)\n\nAfter"
        cleaned, urls = extract_image_urls(text)
        assert urls == ["https://example.com/x.png"]
        # Should not have triple+ blank lines
        assert "\n\n\n" not in cleaned

    def test_http_url(self) -> None:
        text = "![img](http://example.com/pic.jpg)"
        cleaned, urls = extract_image_urls(text)
        assert urls == ["http://example.com/pic.jpg"]

    def test_non_http_url_ignored(self) -> None:
        text = "![img](ftp://example.com/pic.jpg)"
        cleaned, urls = extract_image_urls(text)
        assert urls == []
        assert "![img]" in cleaned

    def test_image_in_code_fence_still_extracted(self) -> None:
        # Note: we do simple regex extraction, not AST-aware.
        # Images inside code fences will still be extracted.
        # This is acceptable for now.
        text = "```\n![img](https://example.com/pic.png)\n```"
        cleaned, urls = extract_image_urls(text)
        assert urls == ["https://example.com/pic.png"]


# ---------------------------------------------------------------------------
# TelegramPresenter.render_final with images
# ---------------------------------------------------------------------------


def _make_state() -> ProgressState:
    return ProgressState(
        engine="test",
        action_count=0,
        actions=(),
        resume=None,
        resume_line=None,
        context_line=None,
    )


class TestPresenterImageExtraction:
    def test_render_final_extracts_photo_urls(self) -> None:
        presenter = TelegramPresenter(message_overflow="trim")
        state = _make_state()
        msg = presenter.render_final(
            state,
            elapsed_s=1.0,
            status="done",
            answer="Here is the result:\n\n![chart](https://example.com/chart.png)\n\nDone.",
        )
        assert "photo_urls" in msg.extra
        assert msg.extra["photo_urls"] == ["https://example.com/chart.png"]
        # The image markdown should be removed from the rendered text
        assert "![" not in msg.text
        assert "example.com/chart.png" not in msg.text

    def test_render_final_no_images(self) -> None:
        presenter = TelegramPresenter(message_overflow="trim")
        state = _make_state()
        msg = presenter.render_final(
            state,
            elapsed_s=1.0,
            status="done",
            answer="Just plain text.",
        )
        assert "photo_urls" not in msg.extra

    def test_render_final_split_mode_extracts_photo_urls(self) -> None:
        presenter = TelegramPresenter(message_overflow="split")
        state = _make_state()
        msg = presenter.render_final(
            state,
            elapsed_s=1.0,
            status="done",
            answer="Result:\n\n![img](https://example.com/pic.jpg)",
        )
        assert "photo_urls" in msg.extra
        assert msg.extra["photo_urls"] == ["https://example.com/pic.jpg"]


# ---------------------------------------------------------------------------
# TelegramTransport.send with photo_urls
# ---------------------------------------------------------------------------


class TestTransportSendPhotos:
    @pytest.mark.anyio
    async def test_send_with_photo_urls(self) -> None:
        bot = FakeBot()
        transport = TelegramTransport(bot)
        message = RenderedMessage(
            text="Here is the analysis.",
            extra={
                "entities": [],
                "reply_markup": {},
                "photo_urls": [
                    "https://example.com/img1.png",
                    "https://example.com/img2.png",
                ],
            },
        )
        ref = await transport.send(
            channel_id=123,
            message=message,
            options=None,
        )
        assert ref is not None
        # Should have sent 2 photos
        assert len(bot.photo_url_calls) == 2
        assert bot.photo_url_calls[0]["photo_url"] == "https://example.com/img1.png"
        assert bot.photo_url_calls[1]["photo_url"] == "https://example.com/img2.png"
        assert bot.photo_url_calls[0]["chat_id"] == 123
        # Should also have sent the text message
        assert len(bot.send_calls) == 1
        assert bot.send_calls[0]["text"] == "Here is the analysis."

    @pytest.mark.anyio
    async def test_send_without_photo_urls(self) -> None:
        bot = FakeBot()
        transport = TelegramTransport(bot)
        message = RenderedMessage(
            text="No images here.",
            extra={"entities": [], "reply_markup": {}},
        )
        ref = await transport.send(
            channel_id=123,
            message=message,
            options=None,
        )
        assert ref is not None
        assert len(bot.photo_url_calls) == 0
        assert len(bot.send_calls) == 1

    @pytest.mark.anyio
    async def test_send_photo_urls_with_options(self) -> None:
        bot = FakeBot()
        transport = TelegramTransport(bot)
        reply_ref = MessageRef(channel_id=123, message_id=42)
        message = RenderedMessage(
            text="Result with image.",
            extra={
                "entities": [],
                "reply_markup": {},
                "photo_urls": ["https://example.com/pic.png"],
            },
        )
        ref = await transport.send(
            channel_id=123,
            message=message,
            options=SendOptions(reply_to=reply_ref, notify=False),
        )
        assert ref is not None
        assert len(bot.photo_url_calls) == 1
        assert bot.photo_url_calls[0]["reply_to_message_id"] == 42
        assert bot.photo_url_calls[0]["disable_notification"] is True
