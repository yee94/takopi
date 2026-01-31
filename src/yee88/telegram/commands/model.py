from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from ...context import RunContext
from ..chat_prefs import ChatPrefsStore
from ..engine_overrides import EngineOverrides, resolve_override_value
from ..files import split_command_args
from ..topic_state import TopicStateStore
from ..topics import _topic_key
from ..types import TelegramCallbackQuery, TelegramIncomingMessage
from .overrides import (
    ENGINE_SOURCE_LABELS,
    OVERRIDE_SOURCE_LABELS,
    apply_engine_override,
    parse_set_args,
    require_admin_or_private,
    resolve_engine_selection,
)
from .reply import make_reply

if TYPE_CHECKING:
    from ..bridge import TelegramBridgeConfig

# Callback data prefix for model selection
MODEL_SELECT_CALLBACK_PREFIX = "yee88:model_select:"

MODEL_USAGE = (
    "usage: `/model`, `/model status`, `/model set <model>`, "
    "`/model set <engine> <model>`, or `/model clear [engine]`"
)


async def _get_opencode_models() -> list[str]:
    """Fetch available models from opencode CLI."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "opencode",
            "models",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return []
        models = stdout.decode().strip().split("\n")
        return [m.strip() for m in models if m.strip()]
    except Exception:
        return []


async def _send_model_selector(
    cfg: TelegramBridgeConfig,
    msg: TelegramIncomingMessage,
    engine: str,
    models: list[str],
) -> None:
    """Send a copyable model list for selection."""
    if not models:
        await cfg.bot.send_message(
            chat_id=msg.chat_id,
            text="No models available.",
            reply_to_message_id=msg.message_id,
            message_thread_id=msg.thread_id,
        )
        return

    header = f"Models for {engine}:\n\n"
    max_len = 4000
    chunks: list[str] = []
    current = header

    for model in models:
        line = f"<code>/model set {model}</code>\n"
        if len(current) + len(line) > max_len:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line

    if current.strip():
        chunks.append(current.rstrip())

    for i, chunk in enumerate(chunks):
        await cfg.bot.send_message(
            chat_id=msg.chat_id,
            text=chunk,
            reply_to_message_id=msg.message_id if i == 0 else None,
            message_thread_id=msg.thread_id,
            parse_mode="HTML",
        )


async def handle_model_select_callback(
    cfg: TelegramBridgeConfig,
    query: TelegramCallbackQuery,
) -> None:
    """Handle model selection from inline keyboard."""
    if not query.data:
        return

    # Parse callback data: yee88:model_select:<engine>:<model>
    prefix = MODEL_SELECT_CALLBACK_PREFIX
    if not query.data.startswith(prefix):
        return

    data = query.data[len(prefix):]
    if ":" not in data:
        return

    engine, model = data.split(":", 1)

    # Answer the callback query
    await cfg.bot.answer_callback_query(
        callback_query_id=query.callback_query_id,
        text=f"Setting model to {model}...",
    )

    # Send the model set command as a new message
    await cfg.bot.send_message(
        chat_id=query.chat_id,
        text=f"/model set {engine} {model}",
    )


async def _handle_model_command(
    cfg: TelegramBridgeConfig,
    msg: TelegramIncomingMessage,
    args_text: str,
    ambient_context: RunContext | None,
    topic_store: TopicStateStore | None,
    chat_prefs: ChatPrefsStore | None,
    *,
    resolved_scope: str | None = None,
    scope_chat_ids: frozenset[int] | None = None,
) -> None:
    reply = make_reply(cfg, msg)
    tkey = (
        _topic_key(msg, cfg, scope_chat_ids=scope_chat_ids)
        if topic_store is not None
        else None
    )
    tokens = split_command_args(args_text)
    action = tokens[0].lower() if tokens else ""
    engine_ids = {engine.lower() for engine in cfg.runtime.engine_ids}

    if action == "":
        selection = await resolve_engine_selection(
            cfg,
            msg,
            ambient_context=ambient_context,
            topic_store=topic_store,
            chat_prefs=chat_prefs,
            topic_key=tkey,
        )
        if selection is None:
            return
        engine, _ = selection

        if engine == "opencode":
            models = await _get_opencode_models()
            opencode_cfg = cfg.runtime.engine_config("opencode")
            model_filter = opencode_cfg.get("model_filter")
            if model_filter and isinstance(model_filter, str):
                try:
                    pattern = re.compile(model_filter, re.IGNORECASE)
                    models = [m for m in models if pattern.search(m)]
                except re.error:
                    pass
            if models:
                await _send_model_selector(cfg, msg, engine, models)
                return

        action = "status"

    if action == "status":
        selection = await resolve_engine_selection(
            cfg,
            msg,
            ambient_context=ambient_context,
            topic_store=topic_store,
            chat_prefs=chat_prefs,
            topic_key=tkey,
        )
        if selection is None:
            return
        engine, engine_source = selection

        topic_override = None
        if tkey is not None and topic_store is not None:
            topic_override = await topic_store.get_engine_override(
                tkey[0], tkey[1], engine
            )
        chat_override = None
        if chat_prefs is not None:
            chat_override = await chat_prefs.get_engine_override(msg.chat_id, engine)
        resolution = resolve_override_value(
            topic_override=topic_override,
            chat_override=chat_override,
            field="model",
        )
        engine_line = f"engine: {engine} ({ENGINE_SOURCE_LABELS[engine_source]})"
        model_value = resolution.value or "default"
        model_line = (
            f"model: {model_value} ({OVERRIDE_SOURCE_LABELS[resolution.source]})"
        )
        topic_label = resolution.topic_value or "none"
        if tkey is None:
            topic_label = "none"
        chat_label = (
            "unavailable" if chat_prefs is None else resolution.chat_value or "none"
        )
        defaults_line = f"defaults: topic: {topic_label}, chat: {chat_label}"
        available_line = f"available engines: {', '.join(cfg.runtime.engine_ids)}"
        await reply(
            text="\n\n".join([engine_line, model_line, defaults_line, available_line])
        )
        return

    if action == "set":
        engine_arg, model = parse_set_args(tokens, engine_ids=engine_ids)
        if model is None:
            await reply(text=MODEL_USAGE)
            return
        if not await require_admin_or_private(
            cfg,
            msg,
            missing_sender="cannot verify sender for model overrides.",
            failed_member="failed to verify model override permissions.",
            denied="changing model overrides is restricted to group admins.",
        ):
            return
        if engine_arg is None:
            selection = await resolve_engine_selection(
                cfg,
                msg,
                ambient_context=ambient_context,
                topic_store=topic_store,
                chat_prefs=chat_prefs,
                topic_key=tkey,
            )
            if selection is None:
                return
            engine, _ = selection
        else:
            engine = engine_arg
            if engine not in engine_ids:
                available = ", ".join(cfg.runtime.engine_ids)
                await reply(
                    text=f"unknown engine `{engine}`.\navailable engines: `{available}`"
                )
                return
        scope = await apply_engine_override(
            reply=reply,
            tkey=tkey,
            topic_store=topic_store,
            chat_prefs=chat_prefs,
            chat_id=msg.chat_id,
            engine=engine,
            update=lambda current: EngineOverrides(
                model=model,
                reasoning=current.reasoning if current is not None else None,
            ),
            topic_unavailable="topic model overrides are unavailable.",
            chat_unavailable="chat model overrides are unavailable (no config path).",
        )
        if scope is None:
            return
        if scope == "topic":
            await reply(
                text=(
                    f"topic model override set to `{model}` for `{engine}`.\n"
                    "If you want a clean start on the new model, run `/new`."
                )
            )
            return
        await reply(
            text=(
                f"chat model override set to `{model}` for `{engine}`.\n"
                "If you want a clean start on the new model, run `/new`."
            )
        )
        return

    if action == "clear":
        engine = None
        if len(tokens) > 2:
            await reply(text=MODEL_USAGE)
            return
        if len(tokens) == 2:
            engine = tokens[1].strip().lower() or None
        if not await require_admin_or_private(
            cfg,
            msg,
            missing_sender="cannot verify sender for model overrides.",
            failed_member="failed to verify model override permissions.",
            denied="changing model overrides is restricted to group admins.",
        ):
            return
        if engine is None:
            selection = await resolve_engine_selection(
                cfg,
                msg,
                ambient_context=ambient_context,
                topic_store=topic_store,
                chat_prefs=chat_prefs,
                topic_key=tkey,
            )
            if selection is None:
                return
            engine, _ = selection
        if engine not in engine_ids:
            available = ", ".join(cfg.runtime.engine_ids)
            await reply(
                text=f"unknown engine `{engine}`.\navailable engines: `{available}`"
            )
            return
        scope = await apply_engine_override(
            reply=reply,
            tkey=tkey,
            topic_store=topic_store,
            chat_prefs=chat_prefs,
            chat_id=msg.chat_id,
            engine=engine,
            update=lambda current: EngineOverrides(
                model=None,
                reasoning=current.reasoning if current is not None else None,
            ),
            topic_unavailable="topic model overrides are unavailable.",
            chat_unavailable="chat model overrides are unavailable (no config path).",
        )
        if scope is None:
            return
        if scope == "topic":
            await reply(text="topic model override cleared (using chat default).")
            return
        await reply(text="chat model override cleared.")
        return

    await reply(text=MODEL_USAGE)
