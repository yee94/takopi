"""Tests for Discord backend module."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yee88.backends import EngineBackend
from yee88.config import ProjectsConfig
from yee88.discord.backend import DiscordBackend, _build_startup_message, _get_discord_settings
from yee88.router import AutoRouter, RunnerEntry
from yee88.runners.mock import Return, ScriptRunner
from yee88.transport_runtime import TransportRuntime


class TestGetDiscordSettings:
    """Test _get_discord_settings helper."""

    def test_extracts_from_dict(self) -> None:
        """Test that settings are extracted from dict."""
        config = {"bot_token": "test-token", "guild_id": 123}
        result = _get_discord_settings(config)
        assert result == config

    def test_extracts_from_pydantic_model(self) -> None:
        """Test that settings are extracted from pydantic model."""
        from pydantic import BaseModel

        class MockModel(BaseModel):
            bot_token: str
            guild_id: int

        model = MockModel(bot_token="test-token", guild_id=123)
        result = _get_discord_settings(model)
        assert result["bot_token"] == "test-token"
        assert result["guild_id"] == 123

    def test_raises_on_invalid_type(self) -> None:
        """Test that invalid type raises TypeError."""
        with pytest.raises(TypeError):
            _get_discord_settings("invalid")


class TestBuildStartupMessage:
    """Test _build_startup_message."""

    def test_includes_ready_message(self, tmp_path: Path) -> None:
        """Test that message includes ready indicator."""
        codex = "codex"
        runner = ScriptRunner([Return(answer="ok")], engine=codex)
        router = AutoRouter(
            entries=[RunnerEntry(engine=codex, runner=runner)],
            default_engine=codex,
        )
        runtime = TransportRuntime(
            router=router,
            projects=ProjectsConfig(projects={}, default_project=None),
            watch_config=True,
        )

        message = _build_startup_message(
            runtime,
            startup_pwd=str(tmp_path),
        )

        assert "yee88-discord is ready" in message

    def test_includes_default_engine(self, tmp_path: Path) -> None:
        """Test that message includes default engine."""
        codex = "codex"
        runner = ScriptRunner([Return(answer="ok")], engine=codex)
        router = AutoRouter(
            entries=[RunnerEntry(engine=codex, runner=runner)],
            default_engine=codex,
        )
        runtime = TransportRuntime(
            router=router,
            projects=ProjectsConfig(projects={}, default_project=None),
            watch_config=True,
        )

        message = _build_startup_message(
            runtime,
            startup_pwd=str(tmp_path),
        )

        assert "default: `codex`" in message

    def test_includes_available_engines(self, tmp_path: Path) -> None:
        """Test that message includes available engines."""
        codex = "codex"
        claude = "claude"
        codex_runner = ScriptRunner([Return(answer="ok")], engine=codex)
        claude_runner = ScriptRunner([Return(answer="ok")], engine=claude)
        router = AutoRouter(
            entries=[
                RunnerEntry(engine=codex, runner=codex_runner),
                RunnerEntry(engine=claude, runner=claude_runner),
            ],
            default_engine=codex,
        )
        runtime = TransportRuntime(
            router=router,
            projects=ProjectsConfig(projects={}, default_project=None),
            watch_config=True,
        )

        message = _build_startup_message(
            runtime,
            startup_pwd=str(tmp_path),
        )

        assert "agents:" in message
        assert "codex" in message
        assert "claude" in message

    def test_includes_missing_engines(self, tmp_path: Path) -> None:
        """Test that message includes missing engines note."""
        codex = "codex"
        pi = "pi"
        runner = ScriptRunner([Return(answer="ok")], engine=codex)
        missing = ScriptRunner([Return(answer="ok")], engine=pi)
        router = AutoRouter(
            entries=[
                RunnerEntry(engine=codex, runner=runner),
                RunnerEntry(
                    engine=pi,
                    runner=missing,
                    status="missing_cli",
                    issue="missing",
                ),
            ],
            default_engine=codex,
        )
        runtime = TransportRuntime(
            router=router,
            projects=ProjectsConfig(projects={}, default_project=None),
            watch_config=True,
        )

        message = _build_startup_message(
            runtime,
            startup_pwd=str(tmp_path),
        )

        assert "not installed: pi" in message

    def test_includes_misconfigured_engines(self, tmp_path: Path) -> None:
        """Test that message includes misconfigured engines note."""
        codex = "codex"
        claude = "claude"
        runner = ScriptRunner([Return(answer="ok")], engine=codex)
        bad_cfg = ScriptRunner([Return(answer="ok")], engine=claude)
        router = AutoRouter(
            entries=[
                RunnerEntry(engine=codex, runner=runner),
                RunnerEntry(engine=claude, runner=bad_cfg, status="bad_config", issue="bad"),
            ],
            default_engine=codex,
        )
        runtime = TransportRuntime(
            router=router,
            projects=ProjectsConfig(projects={}, default_project=None),
            watch_config=True,
        )

        message = _build_startup_message(
            runtime,
            startup_pwd=str(tmp_path),
        )

        assert "misconfigured: claude" in message

    def test_includes_failed_engines(self, tmp_path: Path) -> None:
        """Test that message includes failed engines note."""
        codex = "codex"
        opencode = "opencode"
        runner = ScriptRunner([Return(answer="ok")], engine=codex)
        failed = ScriptRunner([Return(answer="ok")], engine=opencode)
        router = AutoRouter(
            entries=[
                RunnerEntry(engine=codex, runner=runner),
                RunnerEntry(
                    engine=opencode,
                    runner=failed,
                    status="load_error",
                    issue="failed",
                ),
            ],
            default_engine=codex,
        )
        runtime = TransportRuntime(
            router=router,
            projects=ProjectsConfig(projects={}, default_project=None),
            watch_config=True,
        )

        message = _build_startup_message(
            runtime,
            startup_pwd=str(tmp_path),
        )

        assert "failed to load: opencode" in message

    def test_includes_projects(self, tmp_path: Path) -> None:
        """Test that message includes project aliases."""
        codex = "codex"
        runner = ScriptRunner([Return(answer="ok")], engine=codex)
        router = AutoRouter(
            entries=[RunnerEntry(engine=codex, runner=runner)],
            default_engine=codex,
        )
        runtime = TransportRuntime(
            router=router,
            projects=ProjectsConfig(
                projects={
                    "myproject": MagicMock(alias="myproject"),
                    "another": MagicMock(alias="another"),
                },
                default_project=None,
            ),
            watch_config=True,
        )

        message = _build_startup_message(
            runtime,
            startup_pwd=str(tmp_path),
        )

        assert "projects:" in message
        assert "myproject" in message
        assert "another" in message

    def test_includes_working_directory(self, tmp_path: Path) -> None:
        """Test that message includes working directory."""
        codex = "codex"
        runner = ScriptRunner([Return(answer="ok")], engine=codex)
        router = AutoRouter(
            entries=[RunnerEntry(engine=codex, runner=runner)],
            default_engine=codex,
        )
        runtime = TransportRuntime(
            router=router,
            projects=ProjectsConfig(projects={}, default_project=None),
            watch_config=True,
        )

        message = _build_startup_message(
            runtime,
            startup_pwd=str(tmp_path),
        )

        assert f"working in: `{tmp_path}`" in message


class TestDiscordBackend:
    """Test DiscordBackend."""

    def test_backend_id(self) -> None:
        """Test that backend has correct id."""
        backend = DiscordBackend()
        assert backend.id == "discord"

    def test_backend_description(self) -> None:
        """Test that backend has correct description."""
        backend = DiscordBackend()
        assert backend.description == "Discord bot"

    def test_backend_is_transport_backend(self) -> None:
        """Test that backend is a TransportBackend."""
        from yee88.transports import TransportBackend

        backend = DiscordBackend()
        assert isinstance(backend, TransportBackend)


class TestDiscordBackendCheckSetup:
    """Test DiscordBackend check_setup."""

    @patch("yee88.discord.backend.check_setup")
    def test_delegates_to_helper(self, mock_check_setup: MagicMock) -> None:
        """Test that check_setup delegates to helper."""
        backend = DiscordBackend()
        engine_backend = MagicMock(spec=EngineBackend)
        expected_result = MagicMock()
        mock_check_setup.return_value = expected_result

        result = backend.check_setup(engine_backend, transport_override="discord")

        mock_check_setup.assert_called_once_with(engine_backend, transport_override="discord")
        assert result == expected_result


class TestDiscordBackendInteractiveSetup:
    """Test DiscordBackend interactive_setup."""

    @patch("yee88.discord.backend.interactive_setup")
    def test_delegates_to_helper(self, mock_interactive_setup: AsyncMock) -> None:
        """Test that interactive_setup delegates to helper."""
        backend = DiscordBackend()
        mock_interactive_setup.return_value = True

        import asyncio

        result = asyncio.run(backend.interactive_setup(force=True))

        mock_interactive_setup.assert_called_once_with(force=True)
        assert result is True


class TestDiscordBackendLockToken:
    """Test DiscordBackend lock_token."""

    def test_returns_bot_token(self, tmp_path: Path) -> None:
        """Test that lock_token returns bot_token."""
        backend = DiscordBackend()
        config = {"bot_token": "test-token", "guild_id": 123}

        result = backend.lock_token(transport_config=config, _config_path=tmp_path)

        assert result == "test-token"

    def test_returns_none_if_no_token(self, tmp_path: Path) -> None:
        """Test that lock_token returns None if no token."""
        backend = DiscordBackend()
        config = {"guild_id": 123}

        result = backend.lock_token(transport_config=config, _config_path=tmp_path)

        assert result is None


class TestDiscordBackendBuildAndRun:
    """Test DiscordBackend build_and_run."""

    @patch("yee88.discord.backend.DiscordBotClient")
    @patch("yee88.discord.backend.run_main_loop")
    @patch("yee88.discord.backend.anyio.run")
    def test_extracts_settings(
        self,
        mock_anyio_run: MagicMock,
        mock_run_main_loop: AsyncMock,
        mock_client_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that build_and_run extracts settings correctly."""
        backend = DiscordBackend()
        codex = "codex"
        runner = ScriptRunner([Return(answer="ok")], engine=codex)
        router = AutoRouter(
            entries=[RunnerEntry(engine=codex, runner=runner)],
            default_engine=codex,
        )
        runtime = TransportRuntime(
            router=router,
            projects=ProjectsConfig(projects={}, default_project=None),
            watch_config=False,
        )

        transport_config = {
            "bot_token": "test-token",
            "guild_id": 123,
            "channel_id": 456,
            "message_overflow": "trim",
            "session_mode": "chat",
            "show_resume_line": False,
        }

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        backend.build_and_run(
            transport_config=transport_config,
            config_path=tmp_path,
            runtime=runtime,
            final_notify=False,
            default_engine_override=None,
        )

        mock_anyio_run.assert_called_once()
        mock_client_class.assert_called_once_with("test-token", guild_id=123)

    @patch("yee88.discord.backend.DiscordBotClient")
    @patch("yee88.discord.backend.run_main_loop")
    @patch("yee88.discord.backend.anyio.run")
    def test_uses_default_settings(
        self,
        mock_anyio_run: MagicMock,
        mock_run_main_loop: AsyncMock,
        mock_client_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that build_and_run uses default settings when not specified."""
        backend = DiscordBackend()
        codex = "codex"
        runner = ScriptRunner([Return(answer="ok")], engine=codex)
        router = AutoRouter(
            entries=[RunnerEntry(engine=codex, runner=runner)],
            default_engine=codex,
        )
        runtime = TransportRuntime(
            router=router,
            projects=ProjectsConfig(projects={}, default_project=None),
            watch_config=False,
        )

        transport_config = {
            "bot_token": "test-token",
        }

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        backend.build_and_run(
            transport_config=transport_config,
            config_path=tmp_path,
            runtime=runtime,
            final_notify=False,
            default_engine_override=None,
        )

        mock_anyio_run.assert_called_once()
        mock_client_class.assert_called_once_with("test-token", guild_id=None)


if __name__ == "__main__":
    import asyncio

    pytest.main([__file__, "-v"])
