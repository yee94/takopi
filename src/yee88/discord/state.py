"""State management for Discord transport."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio

from .types import DiscordChannelContext, DiscordThreadContext

STATE_VERSION = 2


class DiscordChannelStateData:
    """State data for a single channel or thread."""

    def __init__(
        self,
        context: dict[str, str] | None = None,
        sessions: dict[str, str] | None = None,
        model_overrides: dict[str, str] | None = None,
        reasoning_overrides: dict[str, str] | None = None,
        trigger_mode: str | None = None,
        default_engine: str | None = None,
    ) -> None:
        self.context = context
        self.sessions = sessions
        self.model_overrides = model_overrides
        self.reasoning_overrides = reasoning_overrides
        self.trigger_mode = trigger_mode
        self.default_engine = default_engine


class DiscordGuildData:
    """State data for a guild."""

    def __init__(self, startup_channel_id: int | None = None) -> None:
        self.startup_channel_id = startup_channel_id


class DiscordState:
    """Root state structure."""

    def __init__(
        self,
        version: int = STATE_VERSION,
        channels: dict[str, DiscordChannelStateData] | None = None,
        guilds: dict[str, DiscordGuildData] | None = None,
    ) -> None:
        self.version = version
        self.channels = channels or {}
        self.guilds = guilds or {}


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically using a temp file."""
    tmp_path = path.with_suffix(".tmp")
    content = json.dumps(data, indent=2, ensure_ascii=False)
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


DEFAULT_STATE_PATH = Path.home() / ".yee88" / "discord_state.json"


class DiscordStateStore:
    """State store for Discord channel mappings and sessions."""

    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is not None:
            self._path = config_path.parent / "discord_state.json"
        else:
            self._path = DEFAULT_STATE_PATH
        self._lock = anyio.Lock()
        self._loaded = False
        self._mtime_ns: int | None = None
        self._state = DiscordState()

    def _stat_mtime_ns(self) -> int | None:
        try:
            return self._path.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def _reload_if_needed(self) -> None:
        current = self._stat_mtime_ns()
        if self._loaded and current == self._mtime_ns:
            return
        self._load()

    def _load(self) -> None:
        self._loaded = True
        self._mtime_ns = self._stat_mtime_ns()
        if self._mtime_ns is None:
            self._state = DiscordState()
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._state = self._parse_state(data)
        except Exception:
            self._state = DiscordState()
            return

    def _parse_state(self, data: dict[str, Any]) -> DiscordState:
        """Parse state from JSON data."""
        version = data.get("version", 1)
        channels: dict[str, DiscordChannelStateData] = {}
        guilds: dict[str, DiscordGuildData] = {}

        for key, ch_data in data.get("channels", {}).items():
            channels[key] = DiscordChannelStateData(
                context=ch_data.get("context"),
                sessions=ch_data.get("sessions"),
                model_overrides=ch_data.get("model_overrides"),
                reasoning_overrides=ch_data.get("reasoning_overrides"),
                trigger_mode=ch_data.get("trigger_mode"),
                default_engine=ch_data.get("default_engine"),
            )

        for key, g_data in data.get("guilds", {}).items():
            guilds[key] = DiscordGuildData(
                startup_channel_id=g_data.get("startup_channel_id")
            )

        return DiscordState(version=version, channels=channels, guilds=guilds)

    def _serialize_state(self) -> dict[str, Any]:
        """Serialize state to JSON-compatible dict."""
        channels: dict[str, Any] = {}
        for key, ch in self._state.channels.items():
            channels[key] = {
                "context": ch.context,
                "sessions": ch.sessions,
                "model_overrides": ch.model_overrides,
                "reasoning_overrides": ch.reasoning_overrides,
                "trigger_mode": ch.trigger_mode,
                "default_engine": ch.default_engine,
            }

        guilds: dict[str, Any] = {}
        for key, g in self._state.guilds.items():
            guilds[key] = {"startup_channel_id": g.startup_channel_id}

        return {
            "version": self._state.version,
            "channels": channels,
            "guilds": guilds,
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._serialize_state()
        _atomic_write_json(self._path, payload)
        self._mtime_ns = self._stat_mtime_ns()

    @staticmethod
    def _channel_key(guild_id: int | None, channel_id: int) -> str:
        if guild_id is not None:
            return f"{guild_id}:{channel_id}"
        return str(channel_id)

    async def get_context(
        self, guild_id: int | None, channel_id: int
    ) -> DiscordChannelContext | DiscordThreadContext | None:
        """Get the context for a channel or thread."""
        async with self._lock:
            self._reload_if_needed()
            key = self._channel_key(guild_id, channel_id)
            channel_data = self._state.channels.get(key)
            if channel_data is None or channel_data.context is None:
                return None
            ctx = channel_data.context
            project = ctx.get("project")
            if project is None:
                return None

            branch = ctx.get("branch")
            if branch is not None:
                return DiscordThreadContext(
                    project=project,
                    branch=branch,
                    worktrees_dir=ctx.get("worktrees_dir", ".worktrees"),
                    default_engine=ctx.get("default_engine", "opencode"),
                )
            else:
                return DiscordChannelContext(
                    project=project,
                    worktrees_dir=ctx.get("worktrees_dir", ".worktrees"),
                    default_engine=ctx.get("default_engine", "opencode"),
                    worktree_base=ctx.get("worktree_base", "master"),
                )

    async def set_context(
        self,
        guild_id: int | None,
        channel_id: int,
        context: DiscordChannelContext | DiscordThreadContext | None,
    ) -> None:
        """Set the context for a channel or thread."""
        async with self._lock:
            self._reload_if_needed()
            key = self._channel_key(guild_id, channel_id)
            if key not in self._state.channels:
                self._state.channels[key] = DiscordChannelStateData()
            if context is None:
                self._state.channels[key].context = None
            elif isinstance(context, DiscordThreadContext):
                self._state.channels[key].context = {
                    "project": context.project,
                    "branch": context.branch,
                    "worktrees_dir": context.worktrees_dir,
                    "default_engine": context.default_engine,
                }
            else:
                self._state.channels[key].context = {
                    "project": context.project,
                    "worktrees_dir": context.worktrees_dir,
                    "default_engine": context.default_engine,
                    "worktree_base": context.worktree_base,
                }
            self._save()

    async def get_session(
        self, guild_id: int | None, channel_id: int, engine_id: str
    ) -> str | None:
        """Get the resume token for a session."""
        async with self._lock:
            self._reload_if_needed()
            key = self._channel_key(guild_id, channel_id)
            channel_data = self._state.channels.get(key)
            if channel_data is None or channel_data.sessions is None:
                return None
            return channel_data.sessions.get(engine_id)

    async def set_session(
        self,
        guild_id: int | None,
        channel_id: int,
        engine_id: str,
        resume_token: str | None,
    ) -> None:
        """Set or clear the resume token for a session."""
        async with self._lock:
            self._reload_if_needed()
            key = self._channel_key(guild_id, channel_id)
            if key not in self._state.channels:
                self._state.channels[key] = DiscordChannelStateData()
            if self._state.channels[key].sessions is None:
                self._state.channels[key].sessions = {}
            if resume_token is None:
                self._state.channels[key].sessions.pop(engine_id, None)
            else:
                self._state.channels[key].sessions[engine_id] = resume_token
            self._save()

    async def clear_channel(self, guild_id: int | None, channel_id: int) -> None:
        """Clear all state for a channel."""
        async with self._lock:
            self._reload_if_needed()
            key = self._channel_key(guild_id, channel_id)
            self._state.channels.pop(key, None)
            self._save()

    async def clear_sessions(self, guild_id: int | None, channel_id: int) -> None:
        """Clear all session tokens for a channel/thread."""
        async with self._lock:
            self._reload_if_needed()
            key = self._channel_key(guild_id, channel_id)
            channel_data = self._state.channels.get(key)
            if channel_data is not None:
                channel_data.sessions = None
                self._save()

    async def get_trigger_mode(
        self, guild_id: int | None, channel_id: int
    ) -> str | None:
        """Get trigger mode for a channel/thread."""
        async with self._lock:
            self._reload_if_needed()
            key = self._channel_key(guild_id, channel_id)
            channel_data = self._state.channels.get(key)
            if channel_data is None:
                return None
            return channel_data.trigger_mode

    async def set_trigger_mode(
        self, guild_id: int | None, channel_id: int, mode: str | None
    ) -> None:
        """Set or clear trigger mode for a channel/thread."""
        async with self._lock:
            self._reload_if_needed()
            key = self._channel_key(guild_id, channel_id)
            if key not in self._state.channels:
                self._state.channels[key] = DiscordChannelStateData()
            self._state.channels[key].trigger_mode = mode
            self._save()

    async def get_startup_channel(self, guild_id: int) -> int | None:
        """Get the startup channel for a guild."""
        async with self._lock:
            self._reload_if_needed()
            key = str(guild_id)
            guild_data = self._state.guilds.get(key)
            if guild_data is None:
                return None
            return guild_data.startup_channel_id

    async def set_startup_channel(self, guild_id: int, channel_id: int | None) -> None:
        """Set the startup channel for a guild."""
        async with self._lock:
            self._reload_if_needed()
            key = str(guild_id)
            if key not in self._state.guilds:
                self._state.guilds[key] = DiscordGuildData()
            self._state.guilds[key].startup_channel_id = channel_id
            self._save()