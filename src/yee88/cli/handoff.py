from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import anyio
import typer

from ..context import RunContext
from ..model import ResumeToken
from ..settings import load_settings_if_exists
from ..telegram.client import TelegramClient
from ..telegram.topic_state import TopicStateStore, resolve_state_path

app = typer.Typer(help="Handoff session context to Telegram")

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


def _format_handoff_message(
    session_id: str,
    messages: list[dict],
    project: str | None = None,
) -> str:
    lines = ["📱 **会话接力**", ""]
    
    if project:
        lines.append(f"📁 项目: `{project}`")
    lines.append(f"🔗 Session: `{session_id}`")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    for msg in messages:
        role = msg.get("role", "unknown")
        text = msg.get("text", "")
        role_label = "👤" if role == "user" else "🤖"
        if len(text) > 500:
            text = text[:500] + "..."
        lines.append(f"{role_label} **{role}**:")
        lines.append(text)
        lines.append("")
    
    total_len = sum(len(line) for line in lines)
    if total_len > 3500:
        lines = lines[:20]
        lines.append("... (truncated)")
    
    lines.append("---")
    lines.append("")
    lines.append("💡 直接在此 Topic 发消息即可继续对话")
    
    return "\n".join(lines)


async def _create_handoff_topic(
    token: str,
    chat_id: int,
    session_id: str,
    project: str,
    config_path: Path,
) -> int | None:
    title = f"📱 {project} handoff"
    
    client = TelegramClient(token)
    try:
        result = await client.create_forum_topic(chat_id, title)
        if result is None:
            return None
        
        thread_id = result.message_thread_id
        
        state_path = resolve_state_path(config_path)
        store = TopicStateStore(state_path)
        
        context = RunContext(project=project.lower(), branch=None)
        await store.set_context(chat_id, thread_id, context, topic_title=title)
        
        resume_token = ResumeToken(engine="opencode", value=session_id)
        await store.set_session_resume(chat_id, thread_id, resume_token)
        
        return thread_id
    finally:
        await client.close()


async def _send_to_telegram(
    token: str,
    chat_id: int,
    message: str,
    thread_id: int | None = None,
) -> bool:
    client = TelegramClient(token)
    try:
        result = await client.send_message(
            chat_id=chat_id,
            text=message,
            message_thread_id=thread_id,
            parse_mode="Markdown",
        )
        return result is not None
    finally:
        await client.close()


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
    telegram_cfg = settings.transports.telegram
    
    token = telegram_cfg.bot_token
    chat_id = telegram_cfg.chat_id
    
    if not token or not chat_id:
        typer.echo("❌ Telegram 配置不完整 (需要 bot_token 和 chat_id)", err=True)
        raise typer.Exit(1)
    
    if not telegram_cfg.topics.enabled:
        typer.echo("❌ Topics 未启用，请先运行: yee88 config set transports.telegram.topics.enabled true", err=True)
        raise typer.Exit(1)
    
    session_id = session
    session_project = project
    if session_id is None:
        sessions = _get_recent_sessions(limit=10)
        if not sessions:
            typer.echo("❌ 未找到 OpenCode 会话", err=True)
            raise typer.Exit(1)
        
        typer.echo("\n📲 会话接力 - 将电脑端会话发送到 Telegram 继续对话")
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
    
    typer.echo("🆕 创建新 Topic...")
    
    async def do_handoff() -> tuple[bool, int | None]:
        thread_id = await _create_handoff_topic(
            token=token,
            chat_id=chat_id,
            session_id=session_id,
            project=session_project or "unknown",
            config_path=config_path,
        )
        if thread_id is None:
            return False, None
        
        handoff_msg = _format_handoff_message(
            session_id=session_id,
            messages=messages,
            project=session_project,
        )
        
        success = await _send_to_telegram(
            token=token,
            chat_id=chat_id,
            message=handoff_msg,
            thread_id=thread_id,
        )
        return success, thread_id
    
    success, thread_id = anyio.run(do_handoff)
    
    if success:
        typer.echo("✅ 已发送到 Telegram！")
        typer.echo(f"   Session: {session_id}")
        typer.echo(f"   Project: {session_project}")
        typer.echo(f"   Topic ID: {thread_id}")
        typer.echo(f"   消息数: {limit}")
    else:
        typer.echo("❌ 发送失败", err=True)
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Handoff session context to Telegram for mobile continuation."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(send, session=None, limit=3, project=None)