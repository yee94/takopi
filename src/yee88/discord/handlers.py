"""Slash command and message handlers for Discord."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ..logging import get_logger

if TYPE_CHECKING:
    from ..runner_bridge import RunningTasks
    from ..transport_runtime import TransportRuntime

    from .bridge import DiscordBridgeConfig
    from .client import DiscordBotClient
    from .state import DiscordStateStore

logger = get_logger(__name__)


def _is_admin(ctx: discord.ApplicationContext) -> bool:
    """Check if the user has admin permissions in the guild."""
    if ctx.guild is None:
        return False
    member = ctx.author
    if isinstance(member, discord.Member):
        return member.guild_permissions.administrator
    return False


async def _require_admin(ctx: discord.ApplicationContext) -> bool:
    """Check admin permission and respond with error if not admin."""
    if not _is_admin(ctx):
        await ctx.respond(
            "This command requires administrator permissions.",
            ephemeral=True,
        )
        return False
    return True


def register_slash_commands(
    bot: DiscordBotClient,
    *,
    state_store: DiscordStateStore,
    get_running_task: callable,
    cancel_task: callable,
    runtime: TransportRuntime | None = None,
) -> None:
    """Register slash commands with the bot."""
    pycord_bot = bot.bot

    @pycord_bot.slash_command(
        name="status", description="Show current channel context and status"
    )
    async def status_command(ctx: discord.ApplicationContext) -> None:
        """Show current channel context and running tasks."""
        from .types import DiscordThreadContext

        if ctx.guild is None:
            await ctx.respond(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        channel_id = ctx.channel_id
        guild_id = ctx.guild.id

        context = await state_store.get_context(guild_id, channel_id)

        if context is None:
            await ctx.respond(
                "No context configured for this channel.\n"
                "Use `/bind <project>` to set up this channel.",
                ephemeral=True,
            )
            return

        running = get_running_task(channel_id)
        status_line = "idle"
        if running is not None:
            status_line = f"running (message #{running})"

        if isinstance(context, DiscordThreadContext):
            message = (
                f"**Thread Status**\n"
                f"- Project: `{context.project}`\n"
                f"- Branch: `{context.branch}`\n"
                f"- Worktrees dir: `{context.worktrees_dir}`\n"
                f"- Engine: `{context.default_engine}`\n"
                f"- Status: {status_line}"
            )
        else:
            message = (
                f"**Channel Status**\n"
                f"- Project: `{context.project}`\n"
                f"- Default branch: `{context.worktree_base}`\n"
                f"- Worktrees dir: `{context.worktrees_dir}`\n"
                f"- Engine: `{context.default_engine}`\n"
                f"- Status: {status_line}\n\n"
                f"_Use `@branch-name` to create a thread for a specific branch._"
            )
        await ctx.respond(message, ephemeral=True)

    @pycord_bot.slash_command(name="bind", description="Bind this channel to a project")
    async def bind_command(
        ctx: discord.ApplicationContext,
        project: str = discord.Option(
            description="The project name (must be registered in yee88 config)"
        ),
        worktrees_dir: str = discord.Option(
            default=".worktrees",
            description="Directory for git worktrees (default: .worktrees)",
        ),
        default_engine: str = discord.Option(
            default="opencode",
            description="Default engine to use (default: opencode)",
        ),
        worktree_base: str = discord.Option(
            default="master",
            description="Base branch for worktrees (default: master)",
        ),
    ) -> None:
        """Bind a channel to a project."""
        if ctx.guild is None:
            await ctx.respond(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        channel_id = ctx.channel_id
        guild_id = ctx.guild.id

        from .types import DiscordChannelContext

        context = DiscordChannelContext(
            project=project,
            worktrees_dir=worktrees_dir,
            default_engine=default_engine,
            worktree_base=worktree_base,
        )
        await state_store.set_context(guild_id, channel_id, context)

        await ctx.respond(
            f"Bound channel to project `{project}`\n"
            f"- Default branch: `{worktree_base}`\n"
            f"- Worktrees dir: `{worktrees_dir}`\n"
            f"- Engine: `{default_engine}`\n\n"
            f"_Use `@branch-name` to create threads for specific branches._",
            ephemeral=True,
        )

    @pycord_bot.slash_command(
        name="unbind", description="Remove project binding from this channel"
    )
    async def unbind_command(ctx: discord.ApplicationContext) -> None:
        """Unbind a channel from its project."""
        if ctx.guild is None:
            await ctx.respond(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        channel_id = ctx.channel_id
        guild_id = ctx.guild.id

        await state_store.clear_channel(guild_id, channel_id)
        await ctx.respond("Channel binding removed.", ephemeral=True)

    @pycord_bot.slash_command(
        name="cancel", description="Cancel the currently running task"
    )
    async def cancel_command(ctx: discord.ApplicationContext) -> None:
        """Cancel a running task."""
        if ctx.guild is None:
            await ctx.respond(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        channel_id = ctx.channel_id

        running = get_running_task(channel_id)
        if running is None:
            await ctx.respond(
                "No task is currently running in this channel.", ephemeral=True
            )
            return

        await cancel_task(channel_id)
        await ctx.respond("Cancellation requested.", ephemeral=True)

    @pycord_bot.slash_command(
        name="new", description="Clear conversation session for this channel/thread"
    )
    async def new_command(ctx: discord.ApplicationContext) -> None:
        """Clear stored resume tokens to start fresh."""
        if ctx.guild is None:
            await ctx.respond(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        channel_id = ctx.channel_id
        guild_id = ctx.guild.id

        await state_store.clear_sessions(guild_id, channel_id)
        await ctx.respond("Session cleared. Starting fresh.", ephemeral=True)

    @pycord_bot.slash_command(name="ctx", description="Show or manage context binding")
    async def ctx_command(
        ctx: discord.ApplicationContext,
        action: str | None = discord.Option(
            default=None,
            description="Action to perform (show or clear)",
            choices=["show", "clear"],
        ),
    ) -> None:
        """Show or clear context binding."""
        if ctx.guild is None:
            await ctx.respond(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        guild_id = ctx.guild.id
        channel_id = ctx.channel_id

        if action == "clear":
            if not await _require_admin(ctx):
                return
            await state_store.set_context(guild_id, channel_id, None)
            await ctx.respond("Context binding cleared.", ephemeral=True)
            return

        from .types import DiscordThreadContext

        context = await state_store.get_context(guild_id, channel_id)
        if context is None:
            await ctx.respond(
                "No context bound to this channel/thread.\n"
                "Use `/bind <project>` to set up this channel.",
                ephemeral=True,
            )
            return

        if isinstance(context, DiscordThreadContext):
            msg = (
                f"**Context**\n"
                f"- Project: `{context.project}`\n"
                f"- Branch: `{context.branch}`\n"
                f"- Engine: `{context.default_engine}`"
            )
        else:
            msg = (
                f"**Context**\n"
                f"- Project: `{context.project}`\n"
                f"- Default branch: `{context.worktree_base}`\n"
                f"- Engine: `{context.default_engine}`"
            )
        await ctx.respond(msg, ephemeral=True)


def register_engine_commands(
    bot: DiscordBotClient,
    *,
    cfg: DiscordBridgeConfig,
    state_store: DiscordStateStore,
    running_tasks: RunningTasks,
    default_engine_override: str | None = None,
) -> list[str]:
    """Register dynamic slash commands for each available engine."""
    pycord_bot = bot.bot
    runtime = cfg.runtime

    registered: list[str] = []

    for engine_id in runtime.available_engine_ids():
        cmd_name = engine_id.lower()
        description = f"Use agent: {cmd_name}"

        def make_engine_command(eng_id: str, cmd: str, desc: str):
            @pycord_bot.slash_command(name=cmd, description=desc)
            async def engine_command(
                ctx: discord.ApplicationContext,
                prompt: str = discord.Option(
                    description="The prompt to send to the agent"
                ),
            ) -> None:
                await _handle_engine_command(
                    ctx,
                    engine_id=eng_id,
                    prompt=prompt,
                    cfg=cfg,
                    state_store=state_store,
                    running_tasks=running_tasks,
                )

            return engine_command

        make_engine_command(engine_id, cmd_name, description)
        registered.append(cmd_name)
        logger.info("engine_command.registered", engine=engine_id, command=cmd_name)

    return registered


async def _handle_engine_command(
    ctx: discord.ApplicationContext,
    *,
    engine_id: str,
    prompt: str,
    cfg: DiscordBridgeConfig,
    state_store: DiscordStateStore,
    running_tasks: RunningTasks,
) -> None:
    """Handle a dynamic engine slash command invocation."""
    from ..context import RunContext
    from ..runner_bridge import IncomingMessage
    from ..runner_bridge import handle_message as yee88_handle_message
    from ..utils.paths import reset_run_base_dir, set_run_base_dir

    from .types import DiscordChannelContext, DiscordThreadContext

    if ctx.guild is None:
        await ctx.respond("This command can only be used in a server.", ephemeral=True)
        return

    await ctx.defer()

    guild_id = ctx.guild.id
    channel_id = ctx.channel_id
    thread_id = None

    if isinstance(ctx.channel, discord.Thread):
        thread_id = ctx.channel_id
        if ctx.channel.parent_id:
            channel_id = ctx.channel.parent_id

    # Resolve context from state
    run_context: RunContext | None = None
    channel_context: DiscordChannelContext | None = None
    thread_context: DiscordThreadContext | None = None

    if thread_id:
        ctx_data = await state_store.get_context(guild_id, thread_id)
        if isinstance(ctx_data, DiscordThreadContext):
            thread_context = ctx_data

    ctx_data = await state_store.get_context(guild_id, channel_id)
    if isinstance(ctx_data, DiscordChannelContext):
        channel_context = ctx_data

    if thread_context:
        run_context = RunContext(
            project=thread_context.project,
            branch=thread_context.branch,
        )
    elif channel_context:
        run_context = RunContext(
            project=channel_context.project,
            branch=channel_context.worktree_base,
        )

    effective_channel_id = thread_id or channel_id

    logger.info(
        "engine_command.run",
        engine=engine_id,
        guild_id=guild_id,
        channel_id=effective_channel_id,
        prompt_length=len(prompt),
        has_context=run_context is not None,
    )

    # Resolve working directory
    from ..config import ConfigError

    try:
        cwd = cfg.runtime.resolve_run_cwd(run_context)
    except ConfigError as exc:
        await ctx.followup.send(f"Error: {exc}", ephemeral=True)
        return

    run_base_token = set_run_base_dir(cwd)
    try:
        # Resolve the runner
        resolved = cfg.runtime.resolve_runner(
            resume_token=None,
            engine_override=engine_id,
        )
        if not resolved.available:
            await ctx.followup.send(
                f"Engine `{engine_id}` is not available: {resolved.issue}",
                ephemeral=True,
            )
            return

        incoming = IncomingMessage(
            channel_id=effective_channel_id,
            message_id=0,
            text=prompt,
            reply_to=None,
            thread_id=thread_id,
        )

        context_line = cfg.runtime.format_context_line(run_context)

        await yee88_handle_message(
            cfg.exec_cfg,
            runner=resolved.runner,
            incoming=incoming,
            resume_token=None,
            context=run_context,
            context_line=context_line,
            strip_resume_line=cfg.runtime.is_resume_line,
            running_tasks=running_tasks,
            on_thread_known=None,
        )
    finally:
        reset_run_base_dir(run_base_token)

    await ctx.followup.send(f"✓ `/{engine_id.lower()}` completed", ephemeral=True)


def is_bot_mentioned(message: discord.Message, bot_user: discord.User | None) -> bool:
    """Check if the bot is mentioned in the message."""
    if bot_user is None:
        return False
    return bot_user in message.mentions


def should_process_message(
    message: discord.Message,
    bot_user: discord.User | None,
    *,
    require_mention: bool = False,
) -> bool:
    """Determine if a message should be processed by the bot."""
    if message.author.bot:
        return False

    if not message.content.strip() and not message.attachments:
        return False

    if isinstance(message.channel, discord.Thread):
        return True

    if require_mention:
        return is_bot_mentioned(message, bot_user)

    return True


def extract_prompt_from_message(
    message: discord.Message,
    bot_user: discord.User | None,
) -> str:
    """Extract the prompt text from a message, removing bot mentions."""
    content = message.content

    if bot_user is not None:
        content = content.replace(f"<@{bot_user.id}>", "").strip()
        content = content.replace(f"<@!{bot_user.id}>", "").strip()

    return content


def parse_branch_prefix(content: str) -> tuple[str | None, str]:
    """Parse @branch prefix from message content."""
    content = content.strip()
    if not content.startswith("@"):
        return None, content

    parts = content[1:].split(None, 1)
    if not parts:
        return None, content

    branch = parts[0]
    if not branch:
        return None, content

    remaining = parts[1] if len(parts) > 1 else ""
    return branch, remaining.strip()