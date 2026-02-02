"""Main event loop for Discord transport."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
import discord

from ..config_watch import ConfigReload, watch_config as watch_config_changes
from ..logging import get_logger
from ..markdown import MarkdownParts
from ..model import ResumeToken
from ..runner_bridge import IncomingMessage, RunningTasks
from ..transport import MessageRef, RenderedMessage

if TYPE_CHECKING:
    from ..context import RunContext

from .bridge import DiscordBridgeConfig, DiscordTransport
from .handlers import (
    extract_prompt_from_message,
    parse_branch_prefix,
    register_engine_commands,
    register_slash_commands,
    should_process_message,
)
from .render import prepare_discord
from .state import DiscordStateStore
from .types import DiscordChannelContext, DiscordThreadContext

logger = get_logger(__name__)

__all__ = ["run_main_loop"]


async def _send_startup(cfg: DiscordBridgeConfig, channel_id: int) -> None:
    """Send startup message to the specified channel."""
    logger.debug("startup.message", text=cfg.startup_msg)
    parts = MarkdownParts(header=cfg.startup_msg)
    text = prepare_discord(parts)
    message = RenderedMessage(text=text, extra={})
    sent = await cfg.exec_cfg.transport.send(
        channel_id=channel_id,
        message=message,
    )
    if sent is not None:
        logger.info("startup.sent", channel_id=channel_id)


def _diff_keys(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Return sorted list of keys that differ between two dicts."""
    keys = set(old) | set(new)
    return sorted(key for key in keys if old.get(key) != new.get(key))


async def run_main_loop(
    cfg: DiscordBridgeConfig,
    *,
    default_engine_override: str | None = None,
    config_path: Path | None = None,
    transport_config: dict[str, Any] | None = None,
) -> None:
    """Run the main Discord event loop."""
    running_tasks: RunningTasks = {}
    state_store = DiscordStateStore(cfg.runtime.config_path)
    _ = DiscordTransport  # Used for type checking only

    logger.info(
        "loop.config",
        guild_id=cfg.guild_id,
        has_state_store=state_store is not None,
    )

    def get_running_task(channel_id: int) -> int | None:
        """Get the message ID of a running task in a channel."""
        for ref in running_tasks:
            if ref.channel_id == channel_id or ref.thread_id == channel_id:
                return ref.message_id
        return None

    async def cancel_task(channel_id: int) -> None:
        """Cancel a running task in a channel."""
        for ref, task in list(running_tasks.items()):
            if ref.channel_id == channel_id or ref.thread_id == channel_id:
                task.cancel_requested.set()
                break

    # Register slash commands
    register_slash_commands(
        cfg.bot,
        state_store=state_store,
        get_running_task=get_running_task,
        cancel_task=cancel_task,
        runtime=cfg.runtime,
    )

    # Register engine commands
    engine_commands = register_engine_commands(
        cfg.bot,
        cfg=cfg,
        state_store=state_store,
        running_tasks=running_tasks,
        default_engine_override=default_engine_override,
    )
    if engine_commands:
        logger.info(
            "engine_commands.registered",
            count=len(engine_commands),
            commands=sorted(engine_commands),
        )

    async def run_job(
        channel_id: int,
        user_msg_id: int,
        text: str,
        resume_token: ResumeToken | None,
        context: RunContext | None,
        thread_id: int | None = None,
        reply_ref: MessageRef | None = None,
        guild_id: int | None = None,
    ) -> None:
        """Run an engine job."""
        from ..logging import bind_run_context, clear_context
        from ..runner_bridge import handle_message as yee88_handle_message

        logger.info(
            "run_job.start",
            channel_id=channel_id,
            user_msg_id=user_msg_id,
            text_length=len(text),
            has_context=context is not None,
            project=context.project if context else None,
            branch=context.branch if context else None,
        )

        try:
            # Resolve the runner
            resolved = cfg.runtime.resolve_runner(
                resume_token=resume_token,
                engine_override=default_engine_override,
            )
            if not resolved.available:
                logger.error(
                    "run_job.runner_unavailable",
                    engine=resolved.engine,
                    issue=resolved.issue,
                )
                return

            # Resolve working directory
            from ..config import ConfigError

            try:
                cwd = cfg.runtime.resolve_run_cwd(context)
            except ConfigError as exc:
                logger.error("run_job.cwd_error", error=str(exc))
                return

            from ..utils.paths import reset_run_base_dir, set_run_base_dir

            run_base_token = set_run_base_dir(cwd)
            try:
                # Bind logging context
                run_fields = {
                    "chat_id": channel_id,
                    "user_msg_id": user_msg_id,
                    "engine": resolved.runner.engine,
                    "resume": resume_token.value if resume_token else None,
                }
                if context is not None:
                    run_fields["project"] = context.project
                    run_fields["branch"] = context.branch
                if cwd is not None:
                    run_fields["cwd"] = str(cwd)
                bind_run_context(**run_fields)

                # Build incoming message
                incoming = IncomingMessage(
                    channel_id=channel_id,
                    message_id=user_msg_id,
                    text=text,
                    reply_to=reply_ref,
                    thread_id=thread_id,
                )

                # Build context line if we have context
                context_line = cfg.runtime.format_context_line(context)

                # Callback to save the resume token when it becomes known
                async def on_thread_known(
                    new_token: ResumeToken, _event: anyio.Event
                ) -> None:
                    if state_store and guild_id:
                        engine_id = cfg.runtime.default_engine or "opencode"
                        save_key = thread_id if thread_id else channel_id
                        await state_store.set_session(
                            guild_id, save_key, engine_id, new_token.value
                        )
                        logger.info(
                            "session.saved",
                            guild_id=guild_id,
                            session_key=save_key,
                            engine_id=engine_id,
                        )

                await yee88_handle_message(
                    cfg.exec_cfg,
                    runner=resolved.runner,
                    incoming=incoming,
                    resume_token=resume_token,
                    context=context,
                    context_line=context_line,
                    strip_resume_line=cfg.runtime.is_resume_line,
                    running_tasks=running_tasks,
                    on_thread_known=on_thread_known,
                )
                logger.info("run_job.complete", channel_id=channel_id)
            finally:
                reset_run_base_dir(run_base_token)
        except Exception:
            logger.exception("run_job.error", channel_id=channel_id)
        finally:
            clear_context()

    async def handle_message(message: discord.Message) -> None:
        """Handle an incoming Discord message."""
        logger.debug(
            "message.raw",
            channel_type=type(message.channel).__name__,
            channel_id=message.channel.id,
            author=message.author.name,
            content_preview=message.content[:50] if message.content else "",
        )

        # Guild-only: ignore DMs
        if message.guild is None:
            logger.debug("message.skipped", reason="not in guild (DM)")
            return

        if not should_process_message(message, cfg.bot.user, require_mention=False):
            logger.debug(
                "message.skipped", reason="should_process_message returned False"
            )
            return

        channel_id = message.channel.id
        guild_id = message.guild.id
        thread_id = None

        # Check if this is a thread
        if isinstance(message.channel, discord.Thread):
            thread_id = message.channel.id
            parent = message.channel.parent
            if parent:
                channel_id = parent.id
            logger.debug(
                "message.in_thread",
                thread_id=thread_id,
                parent_channel_id=channel_id,
            )
            # Ensure we're a member of the thread so we receive future messages
            with contextlib.suppress(discord.HTTPException):
                await message.channel.join()

        # Get context from state store
        channel_context: DiscordChannelContext | None = None
        thread_context: DiscordThreadContext | None = None

        if thread_id:
            ctx = await state_store.get_context(guild_id, thread_id)
            if isinstance(ctx, DiscordThreadContext):
                thread_context = ctx

        ctx = await state_store.get_context(guild_id, channel_id)
        if isinstance(ctx, DiscordChannelContext):
            channel_context = ctx

        # Determine effective context
        run_context: RunContext | None = None
        if thread_context:
            from ..context import RunContext

            run_context = RunContext(
                project=thread_context.project,
                branch=thread_context.branch,
            )
        elif channel_context:
            from ..context import RunContext

            run_context = RunContext(
                project=channel_context.project,
                branch=channel_context.worktree_base,
            )

        # Extract prompt
        prompt = extract_prompt_from_message(message, cfg.bot.user)

        # Parse @branch prefix (only for new messages in channels, not in existing threads)
        branch_override: str | None = None
        if thread_id is None:
            branch_override, prompt = parse_branch_prefix(prompt)
            if branch_override:
                logger.info("branch.override", branch=branch_override)

        if not prompt.strip() and not branch_override:
            return

        # Apply branch override to context
        if branch_override:
            from ..context import RunContext

            if channel_context:
                run_context = RunContext(
                    project=channel_context.project,
                    branch=branch_override,
                )
            else:
                logger.warning(
                    "branch.no_project",
                    branch=branch_override,
                    channel_id=channel_id,
                )
                await message.reply(
                    f"Cannot use `@{branch_override}` - this channel has no project bound.\n"
                    "Use `/bind <project>` first to bind this channel to a project.",
                    mention_author=False,
                )
                return

        # Create thread for the response if not already in a thread
        if thread_id is None and isinstance(message.channel, discord.TextChannel):
            if branch_override:
                thread_name = branch_override
            else:
                thread_name = (
                    prompt[:100] if len(prompt) <= 100 else prompt[:97] + "..."
                )
            created_thread_id = await cfg.bot.create_thread(
                channel_id=channel_id,
                message_id=message.id,
                name=thread_name,
            )
            if created_thread_id is not None:
                thread_id = created_thread_id
                logger.info(
                    "thread.created",
                    channel_id=channel_id,
                    thread_id=thread_id,
                    name=thread_name,
                )

                # Save thread context if @branch was used
                if branch_override and channel_context:
                    new_thread_context = DiscordThreadContext(
                        project=channel_context.project,
                        branch=branch_override,
                        worktrees_dir=channel_context.worktrees_dir,
                        default_engine=channel_context.default_engine,
                    )
                    await state_store.set_context(
                        guild_id, thread_id, new_thread_context
                    )
                    logger.info(
                        "thread.context_saved",
                        thread_id=thread_id,
                        project=channel_context.project,
                        branch=branch_override,
                    )

        # Get resume token from state store
        resume_token: ResumeToken | None = None
        session_key = thread_id if thread_id else channel_id

        if thread_context:
            engine_id = thread_context.default_engine
        elif channel_context:
            engine_id = channel_context.default_engine
        else:
            engine_id = cfg.runtime.default_engine or "opencode"

        token_str = await state_store.get_session(guild_id, session_key, engine_id)
        if token_str:
            resume_token = ResumeToken(engine=engine_id, value=token_str)
            logger.info(
                "session.restored",
                guild_id=guild_id,
                session_key=session_key,
                engine_id=engine_id,
            )

        # Build reply reference
        reply_ref: MessageRef | None = MessageRef(
            channel_id=channel_id,
            message_id=message.id,
            thread_id=thread_id,
        )

        logger.info(
            "message.received",
            channel_id=channel_id,
            thread_id=thread_id,
            message_id=message.id,
            author=message.author.name,
            prompt_length=len(prompt),
            has_context=run_context is not None,
            has_resume_token=resume_token is not None,
        )

        # Use thread_id as channel_id if we're in a thread
        job_channel_id = thread_id if thread_id else channel_id

        try:
            await run_job(
                channel_id=job_channel_id,
                user_msg_id=message.id,
                text=prompt,
                resume_token=resume_token,
                context=run_context,
                thread_id=thread_id,
                reply_ref=reply_ref,
                guild_id=guild_id,
            )
        except Exception:
            logger.exception("handle_message.run_job_failed")

    # Set up message handler
    cfg.bot.set_message_handler(handle_message)

    # Auto-join new threads so we receive messages from them
    @cfg.bot.bot.event
    async def on_thread_create(thread: discord.Thread) -> None:
        with contextlib.suppress(discord.HTTPException):
            await thread.join()
            logger.debug("thread.auto_joined", thread_id=thread.id, name=thread.name)

    # Start the bot
    await cfg.bot.start()

    # Send startup message to configured channel or first available text channel
    if cfg.channel_id:
        await _send_startup(cfg, cfg.channel_id)
        logger.info("startup.configured_channel", channel_id=cfg.channel_id)
    elif cfg.guild_id:
        guild = cfg.bot.get_guild(cfg.guild_id)
        if guild:
            for channel in guild.text_channels:
                await _send_startup(cfg, channel.id)
                logger.info(
                    "startup.first_channel",
                    channel_id=channel.id,
                )
                break

    logger.info("bot.ready", user=cfg.bot.user.name if cfg.bot.user else "unknown")

    # Config file watching state
    transport_snapshot: dict[str, Any] | None = (
        dict(transport_config) if transport_config is not None else None
    )

    async def handle_reload(reload: ConfigReload) -> None:
        """Handle config file reload."""
        nonlocal transport_snapshot

        # Check for transport config changes
        if transport_snapshot is not None:
            # Discord config is in model_extra since it's a plugin transport
            new_snapshot = getattr(reload.settings.transports, "model_extra", {}).get(
                "discord"
            )
            if isinstance(new_snapshot, dict):
                changed = _diff_keys(transport_snapshot, new_snapshot)
                if changed:
                    logger.warning(
                        "config.reload.transport_config_changed",
                        transport="discord",
                        keys=changed,
                        restart_required=True,
                    )
                    transport_snapshot = new_snapshot

    watch_enabled = config_path is not None

    async def run_with_watcher() -> None:
        """Run the main loop with optional config watcher."""
        async with anyio.create_task_group() as tg:
            if watch_enabled and config_path is not None:

                async def run_config_watch() -> None:
                    await watch_config_changes(
                        config_path=config_path,
                        runtime=cfg.runtime,
                        default_engine_override=default_engine_override,
                        on_reload=handle_reload,
                    )

                tg.start_soon(run_config_watch)
                logger.info("config.watch.started", path=str(config_path))

            # Keep running until cancelled
            await anyio.sleep_forever()

    try:
        await run_with_watcher()
    finally:
        await cfg.bot.close()