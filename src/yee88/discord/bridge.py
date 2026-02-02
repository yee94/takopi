"""Discord transport and presenter implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from ..markdown import MarkdownFormatter
from ..progress import ProgressState
from ..transport import MessageRef, RenderedMessage, SendOptions
from .client import DiscordBotClient
from .render import MAX_BODY_CHARS, prepare_discord, prepare_discord_multi

if TYPE_CHECKING:
    from ..runner_bridge import ExecBridgeConfig
    from ..transport_runtime import TransportRuntime

__all__ = [
    "DiscordBridgeConfig",
    "DiscordPresenter",
    "DiscordTransport",
]


class DiscordPresenter:
    """Presenter for rendering messages to Discord format."""

    def __init__(
        self,
        *,
        formatter: MarkdownFormatter | None = None,
        message_overflow: str = "split",
    ) -> None:
        self._formatter = formatter or MarkdownFormatter()
        self._message_overflow = message_overflow

    def render_progress(
        self,
        state: ProgressState,
        *,
        elapsed_s: float,
        label: str = "working",
    ) -> RenderedMessage:
        """Render a progress update message."""
        parts = self._formatter.render_progress_parts(
            state, elapsed_s=elapsed_s, label=label
        )
        text = prepare_discord(parts)
        return RenderedMessage(
            text=text,
            extra={},
        )

    def render_final(
        self,
        state: ProgressState,
        *,
        elapsed_s: float,
        status: str,
        answer: str,
    ) -> RenderedMessage:
        """Render a final response message."""
        parts = self._formatter.render_final_parts(
            state, elapsed_s=elapsed_s, status=status, answer=answer
        )
        if self._message_overflow == "split":
            messages = prepare_discord_multi(parts, max_body_chars=MAX_BODY_CHARS)
            text = messages[0]
            extra: dict = {}
            if len(messages) > 1:
                followups = [
                    RenderedMessage(text=msg, extra={})
                    for msg in messages[1:]
                ]
                extra["followups"] = followups
            return RenderedMessage(text=text, extra=extra)
        text = prepare_discord(parts)
        return RenderedMessage(text=text, extra={})


@dataclass(frozen=True, slots=True)
class DiscordBridgeConfig:
    """Configuration for the Discord bridge."""

    bot: DiscordBotClient
    runtime: TransportRuntime
    guild_id: int | None
    channel_id: int | None
    startup_msg: str
    exec_cfg: ExecBridgeConfig
    session_mode: Literal["stateless", "chat"] = "stateless"
    show_resume_line: bool = True
    message_overflow: Literal["trim", "split"] = "split"


class DiscordTransport:
    """Transport implementation for Discord."""

    def __init__(self, bot: DiscordBotClient) -> None:
        self._bot = bot

    async def close(self) -> None:
        """Close the transport."""
        await self._bot.close()

    async def send(
        self,
        *,
        channel_id: int | str,
        message: RenderedMessage,
        options: SendOptions | None = None,
    ) -> MessageRef | None:
        """Send a message."""
        cid = cast(int, channel_id)
        reply_to_message_id: int | None = None
        thread_id: int | None = None

        if options is not None:
            reply_to_message_id = (
                cast(int, options.reply_to.message_id)
                if options.reply_to is not None
                else None
            )
            thread_id = (
                cast(int | None, options.thread_id)
                if options.thread_id is not None
                else None
            )

        followups = message.extra.get("followups")
        sent = await self._bot.send_message(
            channel_id=cid,
            content=message.text,
            reply_to_message_id=reply_to_message_id,
            thread_id=thread_id,
        )
        if sent is None:
            return None

        # Delete the old message if replace is specified
        if options is not None and options.replace is not None:
            await self.delete(ref=options.replace)

        # Send followup messages if any
        if isinstance(followups, list) and followups:
            for followup in followups:
                if isinstance(followup, RenderedMessage):
                    await self._bot.send_message(
                        channel_id=cid,
                        content=followup.text,
                        reply_to_message_id=None,
                        thread_id=thread_id,
                    )

        return MessageRef(
            channel_id=cid,
            message_id=sent.message_id,
            raw=sent,
            thread_id=thread_id or sent.thread_id,
        )

    async def edit(
        self,
        *,
        ref: MessageRef,
        message: RenderedMessage,
        wait: bool = True,
    ) -> MessageRef | None:
        """Edit an existing message."""
        channel_id = cast(int, ref.channel_id)
        message_id = cast(int, ref.message_id)

        followups = message.extra.get("followups")
        edited = await self._bot.edit_message(
            channel_id=ref.thread_id or channel_id,
            message_id=message_id,
            content=message.text,
            wait=wait,
        )
        if edited is None:
            return ref if not wait else None

        # Send followup messages if any
        if isinstance(followups, list) and followups:
            for followup in followups:
                if isinstance(followup, RenderedMessage):
                    await self._bot.send_message(
                        channel_id=channel_id,
                        content=followup.text,
                        reply_to_message_id=None,
                        thread_id=ref.thread_id,
                    )

        return MessageRef(
            channel_id=channel_id,
            message_id=edited.message_id,
            raw=edited,
            thread_id=ref.thread_id,
        )

    async def delete(self, *, ref: MessageRef) -> bool:
        """Delete a message."""
        return await self._bot.delete_message(
            channel_id=cast(int, ref.thread_id or ref.channel_id),
            message_id=cast(int, ref.message_id),
        )
