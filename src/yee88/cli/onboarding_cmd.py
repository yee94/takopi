"""Onboarding commands for multiple transports."""

from __future__ import annotations

import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, cast

import anyio
import typer

from ..config import ConfigError, load_or_init_config, write_config
from ..config_migrations import migrate_config
from ..logging import setup_logging
from ..settings import TakopiSettings
from .init import _ensure_projects_table
from .run import _load_settings_optional


def _get_transport_onboarding(transport: str):
    if transport == "telegram":
        from ..telegram import onboarding as telegram_onboarding

        return telegram_onboarding
    elif transport == "discord":
        from ..discord import onboarding as discord_onboarding

        return discord_onboarding
    else:
        raise ConfigError(f"Unsupported transport: {transport!r}")


def chat_id(
    token: str | None = typer.Option(
        None,
        "--token",
        help="Bot token (defaults to config if available).",
    ),
    project: str | None = typer.Option(
        None,
        "--project",
        help="Project alias to print a chat_id snippet for.",
    ),
) -> None:
    setup_logging_fn = cast(
        Callable[..., None],
        _resolve_cli_attr("setup_logging") or setup_logging,
    )
    load_settings_optional_fn = cast(
        Callable[[], tuple[TakopiSettings | None, Path | None]],
        _resolve_cli_attr("_load_settings_optional") or _load_settings_optional,
    )
    load_or_init_config_fn = cast(
        Callable[[], tuple[dict, Path]],
        _resolve_cli_attr("load_or_init_config") or load_or_init_config,
    )
    ensure_projects_table_fn = cast(
        Callable[[dict, Path], dict],
        _resolve_cli_attr("_ensure_projects_table") or _ensure_projects_table,
    )
    migrate_config_fn = cast(
        Callable[..., object],
        _resolve_cli_attr("migrate_config") or migrate_config,
    )
    write_config_fn = cast(
        Callable[[dict, Path], None],
        _resolve_cli_attr("write_config") or write_config,
    )

    setup_logging_fn(debug=False, cache_logger_on_first_use=False)

    # Determine transport type from settings
    settings, _ = load_settings_optional_fn()
    transport = "telegram"  # Default to telegram for backward compatibility
    if settings is not None:
        transport = settings.transport
        # Get token from config if not provided
        if token is None:
            if transport == "telegram":
                tg = settings.transports.telegram
                token = tg.bot_token or None
            elif transport == "discord":
                extra = settings.transports.model_extra or {}
                discord_cfg = extra.get("discord", {})
                if isinstance(discord_cfg, dict):
                    token = discord_cfg.get("bot_token")

    # Get transport-specific onboarding module
    try:
        onboarding_mod = _get_transport_onboarding(transport)
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    chat = anyio.run(partial(onboarding_mod.capture_chat_id, token=token))
    if chat is None:
        raise typer.Exit(code=1)

    if project:
        project = project.strip()
        if not project:
            raise ConfigError("Invalid `--project`; expected a non-empty string.")

        config, config_path = load_or_init_config_fn()
        if config_path.exists():
            applied = migrate_config_fn(config, config_path=config_path)
            if applied:
                write_config_fn(config, config_path)

        projects = ensure_projects_table_fn(config, config_path)
        entry = projects.get(project)
        if entry is None:
            lowered = project.lower()
            for key, value in projects.items():
                if isinstance(key, str) and key.lower() == lowered:
                    entry = value
                    project = key
                    break
        if entry is None:
            raise ConfigError(
                f"Unknown project {project!r}; run `yee88 init {project}` first."
            )
        if not isinstance(entry, dict):
            raise ConfigError(
                f"Invalid `projects.{project}` in {config_path}; expected a table."
            )
        entry["chat_id"] = chat.chat_id
        write_config_fn(config, config_path)
        typer.echo(f"updated projects.{project}.chat_id = {chat.chat_id}")
        return

    typer.echo(f"chat_id = {chat.chat_id}")


def onboarding_paths() -> None:
    setup_logging_fn = cast(
        Callable[..., None],
        _resolve_cli_attr("setup_logging") or setup_logging,
    )

    # Determine transport type from settings
    load_settings_optional_fn = cast(
        Callable[[], tuple[TakopiSettings | None, Path | None]],
        _resolve_cli_attr("_load_settings_optional") or _load_settings_optional,
    )

    settings, _ = load_settings_optional_fn()
    transport = "telegram"  # Default to telegram
    if settings is not None:
        transport = settings.transport

    try:
        onboarding_mod = _get_transport_onboarding(transport)
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    setup_logging_fn(debug=False, cache_logger_on_first_use=False)
    onboarding_mod.debug_onboarding_paths()


def _resolve_cli_attr(name: str) -> object | None:
    cli_module = sys.modules.get("yee88.cli")
    if cli_module is None:
        return None
    return getattr(cli_module, name, None)
