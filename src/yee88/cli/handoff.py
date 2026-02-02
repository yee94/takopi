"""Handoff command - transfer session context to chat platform."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import anyio
import typer

from ..config import ConfigError
from ..handoff import SessionContext
from ..handoff.factory import create_handoff_backend
from ..settings import load_settings_if_exists

app = typer.Typer(help="Handoff session context to chat platform")

OPENCODE_STORAGE = Path.home() / ".local" / "share" / "opencode" / "storage"


@dataclass
class SessionInfo:
    id: str
    directory: str
    updated: float
    title: str

    @property
    def project_name(self) -> str:
        return Path(self.directory).name if self.directory else "unknown"

    @property
    def updated_str(self) -> str:
        return datetime.fromtimestamp(self.updated / 1000).strftime("%m-%d %H:%M")


def _get_recent_sessions(limit: int = 10) -> list[SessionInfo]:
    try:
        result = subprocess.run(
            ["opencode", "session", "list", "--format", "json", "-n", str(limit)],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        return [
            SessionInfo(
                id=s.get("id", ""),
                directory=s.get("directory", ""),
                updated=s.get("updated", 0),
                title=s.get("title", ""),
            )
            for s in data
        ]
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
        return []


def _get_session_messages(session_id: str, limit: int = 5) -> list[dict]:
    message_dir = OPENCODE_STORAGE / "message" / session_id
    if not message_dir.exists():
        return []

    messages: list[tuple[int, str, str]] = []
    for msg_file in message_dir.glob("msg_*.json"):
        try:
            data = json.loads(msg_file.read_text())
            created = data.get("time", {}).get("created", 0)
            role = data.get("role", "unknown")
            msg_id = data.get("id", "")
            messages.append((created, role, msg_id))
        except (json.JSONDecodeError, OSError):
            continue

    messages.sort(key=lambda x: x[0], reverse=True)
    messages = messages[:limit]
    messages.reverse()

    result = []
    for _, role, msg_id in messages:
        part_dir = OPENCODE_STORAGE / "part" / msg_id
        if not part_dir.exists():
            continue
        for part_file in part_dir.glob("prt_*.json"):
            try:
                part_data = json.loads(part_file.read_text())
                if part_data.get("type") == "text":
                    text = part_data.get("text", "")
                    if text.startswith('"') and text.endswith('"\n'):
                        text = json.loads(text.rstrip('\n'))
                    result.append({"role": role, "text": text})
                    break
            except (json.JSONDecodeError, OSError):
                continue

    return result


@app.command()
def send(
    session: str | None = typer.Option(
        None, "--session", "-s", help="Session ID (defaults to latest)"
    ),
    limit: int = typer.Option(
        3, "--limit", "-n", help="Number of messages to include"
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name for context"
    ),
) -> None:
    result = load_settings_if_exists()
    if result is None:
        typer.echo("❌ 未找到 yee88 配置文件", err=True)
        raise typer.Exit(1)

    settings, config_path = result

    try:
        backend = create_handoff_backend(settings, config_path)
    except ConfigError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1) from None

    if not backend.is_available():
        typer.echo("❌ 后端未配置或不可用", err=True)
        raise typer.Exit(1)

    session_id = session
    session_project = project
    if session_id is None:
        sessions = _get_recent_sessions(limit=10)
        if not sessions:
            typer.echo("❌ 未找到 OpenCode 会话", err=True)
            raise typer.Exit(1)

        transport_name = backend.name
        typer.echo(f"\n📲 会话接力 - 将电脑端会话发送到 {transport_name} 继续对话")
        typer.echo("━" * 50)
        typer.echo("\n📋 最近的会话:\n")
        for i, s in enumerate(sessions[:10], 1):
            title_display = s.title[:40] if s.title else s.project_name
            typer.echo(f"  [{i}] {s.updated_str}  {title_display}")
        typer.echo("")

        choice = typer.prompt("选择会话 (1-10)", default="1")
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(sessions):
                typer.echo("❌ 无效选择", err=True)
                raise typer.Exit(1)
        except ValueError:
            typer.echo("❌ 请输入数字", err=True)
            raise typer.Exit(1)

        selected = sessions[idx]
        session_id = selected.id
        if session_project is None:
            session_project = selected.project_name

    if not session_id:
        typer.echo("❌ 会话 ID 为空", err=True)
        raise typer.Exit(1)

    typer.echo(f"📖 读取会话 {session_id[:20]}...")

    messages = _get_session_messages(session_id, limit=limit)
    if not messages:
        typer.echo("❌ 无法读取会话消息", err=True)
        raise typer.Exit(1)

    typer.echo("🆕 创建新 Topic/Thread...")

    context = SessionContext(
        session_id=session_id,
        project=session_project or "unknown",
        messages=messages,
    )

    async def do_handoff():
        return await backend.handoff(
            context=context,
            config_path=config_path,
        )

    result = anyio.run(do_handoff)

    if result.success:
        typer.echo("✅ 已发送！")
        typer.echo(f"   Session: {session_id}")
        typer.echo(f"   Project: {session_project}")
        typer.echo(f"   Thread ID: {result.thread_id}")
        typer.echo(f"   消息数: {limit}")
    else:
        typer.echo("❌ 发送失败", err=True)
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Handoff session context to chat platform for mobile continuation."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(send, session=None, limit=3, project=None)
