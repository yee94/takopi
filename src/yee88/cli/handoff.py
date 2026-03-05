from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

import anyio
import typer

from ..context import RunContext
from ..engines import list_backend_ids
from ..model import ResumeToken
from ..settings import load_settings_if_exists
from ..telegram.client import TelegramClient
from ..telegram.topic_state import TopicStateStore, resolve_state_path
from ..telegram.engine_overrides import EngineOverrides

app = typer.Typer(help="Handoff session context to Telegram")

# Engine type
EngineType = Literal["opencode", "claude"]

# OpenCode paths
OPENCODE_STORAGE = Path.home() / ".local" / "share" / "opencode" / "storage"
OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

# Claude paths
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


@dataclass
class SessionInfo:
    id: str
    directory: str
    updated: float
    title: str
    engine: EngineType = "opencode"
    
    @property
    def project_name(self) -> str:
        return Path(self.directory).name if self.directory else "unknown"
    
    @property
    def updated_str(self) -> str:
        # OpenCode uses milliseconds, Claude uses ISO format parsed to seconds
        ts = self.updated / 1000 if self.updated > 1e12 else self.updated
        return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


# =============================================================================
# OpenCode Session Functions
# =============================================================================

def _get_opencode_sessions(limit: int = 10) -> list[SessionInfo]:
    """通过 opencode session list 命令获取最近会话"""
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
                engine="opencode",
            )
            for s in data
        ]
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
        return []


def _get_opencode_messages_sqlite(session_id: str, limit: int = 5) -> list[dict]:
    """从 SQLite 数据库读取 OpenCode session 消息"""
    try:
        conn = sqlite3.connect(str(OPENCODE_DB))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 取最近 limit 条 user/assistant 消息
        cursor.execute(
            "SELECT id, data FROM message "
            "WHERE session_id = ? "
            "ORDER BY time_created DESC LIMIT ?",
            (session_id, limit),
        )
        rows = cursor.fetchall()
        rows.reverse()  # 按时间正序

        result = []
        for row in rows:
            msg_data = json.loads(row["data"])
            role = msg_data.get("role", "unknown")
            msg_id = row["id"]

            # 从 part 表读取文本内容
            cursor.execute(
                "SELECT data FROM part "
                "WHERE message_id = ? "
                "ORDER BY time_created ASC",
                (msg_id,),
            )
            for part_row in cursor.fetchall():
                part_data = json.loads(part_row["data"])
                if part_data.get("type") == "text":
                    text = part_data.get("text", "")
                    result.append({"role": role, "text": text})
                    break

        conn.close()
        return result
    except (sqlite3.Error, json.JSONDecodeError, OSError):
        return []


def _get_opencode_messages_fs(session_id: str, limit: int = 5) -> list[dict]:
    """旧版文件系统格式读取（兼容）"""
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


def _get_opencode_messages(session_id: str, limit: int = 5) -> list[dict]:
    """获取 OpenCode session 消息"""
    # 优先从 SQLite 数据库读取（新版 OpenCode 格式）
    if OPENCODE_DB.exists():
        result = _get_opencode_messages_sqlite(session_id, limit)
        if result:
            return result

    # 回退到旧版文件系统格式
    return _get_opencode_messages_fs(session_id, limit)


def _get_opencode_model_id(session_id: str) -> str | None:
    """从 OpenCode session 最近的 assistant 消息中提取完整模型 ID (providerID/modelID)。"""
    if not OPENCODE_DB.exists():
        return None
    try:
        conn = sqlite3.connect(str(OPENCODE_DB))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # 取最近一条 assistant 消息的 modelID 和 providerID
        cursor.execute(
            "SELECT data FROM message "
            "WHERE session_id = ? "
            "ORDER BY time_created DESC LIMIT 20",
            (session_id,),
        )
        for row in cursor.fetchall():
            msg_data = json.loads(row["data"])
            model_id = msg_data.get("modelID")
            if model_id and msg_data.get("role") == "assistant":
                provider_id = msg_data.get("providerID")
                conn.close()
                # 拼接完整模型 ID: providerID/modelID
                if provider_id:
                    return f"{provider_id}/{model_id}"
                return model_id
        conn.close()
    except (sqlite3.Error, json.JSONDecodeError, OSError):
        pass
    return None


# =============================================================================
# Claude Session Functions
# =============================================================================

def _decode_claude_project_path(encoded: str) -> str:
    """将 Claude 编码的项目路径解码为原始路径"""
    # -Users-yee-wang-ZCodeProject -> /Users/yee.wang/ZCodeProject
    return encoded.replace("-", "/")


def _get_claude_sessions(limit: int = 10) -> list[SessionInfo]:
    """从 ~/.claude/projects/ 读取 Claude sessions"""
    if not CLAUDE_PROJECTS.exists():
        return []
    
    sessions: list[SessionInfo] = []
    
    # 遍历所有项目目录
    for project_dir in CLAUDE_PROJECTS.iterdir():
        if not project_dir.is_dir():
            continue
        
        # 解码项目路径
        directory = _decode_claude_project_path(project_dir.name)
        
        # 遍历项目下的 session 文件
        for session_file in project_dir.glob("*.jsonl"):
            # 跳过 agent- 开头的文件（子代理 session）
            if session_file.name.startswith("agent-"):
                continue
            
            session_id = session_file.stem
            
            # 读取第一行和最后一行获取时间和标题
            try:
                lines = session_file.read_text().strip().split("\n")
                if not lines:
                    continue
                
                # 从最后一行获取时间戳
                last_line = json.loads(lines[-1])
                timestamp_str = last_line.get("timestamp", "")
                if timestamp_str:
                    # ISO format: 2026-01-04T06:12:46.787Z
                    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    updated = dt.timestamp()
                else:
                    updated = session_file.stat().st_mtime
                
                # 尝试从消息中提取标题（第一条 user 消息）
                title = ""
                for line in lines:
                    try:
                        data = json.loads(line)
                        if data.get("type") == "user":
                            msg = data.get("message", {})
                            content = msg.get("content", [])
                            if isinstance(content, list):
                                for part in content:
                                    if isinstance(part, dict) and part.get("type") == "text":
                                        title = part.get("text", "")[:50]
                                        break
                            elif isinstance(content, str):
                                title = content[:50]
                            if title:
                                break
                    except json.JSONDecodeError:
                        continue
                
                sessions.append(SessionInfo(
                    id=session_id,
                    directory=directory,
                    updated=updated,
                    title=title,
                    engine="claude",
                ))
            except (OSError, json.JSONDecodeError):
                continue
    
    # 按更新时间排序，取最近的
    sessions.sort(key=lambda s: s.updated, reverse=True)
    return sessions[:limit]


def _get_claude_messages(session_id: str, limit: int = 5) -> list[dict]:
    """从 Claude session JSONL 文件读取消息"""
    if not CLAUDE_PROJECTS.exists():
        return []
    
    # 查找 session 文件
    session_file: Path | None = None
    for project_dir in CLAUDE_PROJECTS.iterdir():
        if not project_dir.is_dir():
            continue
        candidate = project_dir / f"{session_id}.jsonl"
        if candidate.exists():
            session_file = candidate
            break
    
    if session_file is None:
        return []
    
    try:
        lines = session_file.read_text().strip().split("\n")
        
        # 提取 user/assistant 消息
        messages: list[dict] = []
        for line in lines:
            try:
                data = json.loads(line)
                msg_type = data.get("type")
                if msg_type not in ("user", "assistant"):
                    continue
                
                msg = data.get("message", {})
                role = msg.get("role", msg_type)
                content = msg.get("content", [])
                
                # 提取文本内容
                text = ""
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = part.get("text", "")
                            break
                elif isinstance(content, str):
                    text = content
                
                if text:
                    messages.append({"role": role, "text": text})
            except json.JSONDecodeError:
                continue
        
        # 返回最后 limit 条消息
        return messages[-limit:] if len(messages) > limit else messages
    except OSError:
        return []


def _get_claude_model_id(session_id: str) -> str | None:
    """从 Claude session 提取模型 ID"""
    if not CLAUDE_PROJECTS.exists():
        return None
    
    # 查找 session 文件
    session_file: Path | None = None
    for project_dir in CLAUDE_PROJECTS.iterdir():
        if not project_dir.is_dir():
            continue
        candidate = project_dir / f"{session_id}.jsonl"
        if candidate.exists():
            session_file = candidate
            break
    
    if session_file is None:
        return None
    
    try:
        lines = session_file.read_text().strip().split("\n")
        
        # 从后往前找 assistant 消息的 model
        for line in reversed(lines):
            try:
                data = json.loads(line)
                if data.get("type") == "assistant":
                    msg = data.get("message", {})
                    model = msg.get("model")
                    if model and model != "<synthetic>":
                        return model
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    
    return None


# =============================================================================
# Unified Session Functions
# =============================================================================

def _get_recent_sessions(engine: EngineType | None = None, limit: int = 10) -> list[SessionInfo]:
    """获取最近的 sessions，支持指定引擎或获取所有引擎的 sessions"""
    sessions: list[SessionInfo] = []
    
    if engine is None or engine == "opencode":
        sessions.extend(_get_opencode_sessions(limit))
    
    if engine is None or engine == "claude":
        sessions.extend(_get_claude_sessions(limit))
    
    # 按更新时间排序
    sessions.sort(key=lambda s: s.updated, reverse=True)
    return sessions[:limit]


def _get_session_messages(session: SessionInfo, limit: int = 5) -> list[dict]:
    """根据 session 的引擎类型获取消息"""
    if session.engine == "opencode":
        return _get_opencode_messages(session.id, limit)
    elif session.engine == "claude":
        return _get_claude_messages(session.id, limit)
    return []


def _get_session_model_id(session: SessionInfo) -> str | None:
    """根据 session 的引擎类型获取模型 ID"""
    if session.engine == "opencode":
        return _get_opencode_model_id(session.id)
    elif session.engine == "claude":
        return _get_claude_model_id(session.id)
    return None


# =============================================================================
# Message Formatting
# =============================================================================

import re


def _escape_markdown(text: str) -> str:
    """转义 Telegram Markdown V1 特殊字符，避免解析错误。"""
    # Markdown V1 特殊字符: _ * ` [
    return re.sub(r'([_*`\[\]])', r'\\\1', text)


def _format_handoff_message(
    session_id: str,
    messages: list[dict],
    project: str | None = None,
    engine: EngineType = "opencode",
) -> str:
    lines = ["📱 **会话接力**", ""]
    
    if project:
        lines.append(f"📁 项目: `{project}`")
    lines.append(f"🔗 Session: `{session_id}`")
    lines.append(f"🤖 引擎: `{engine}`")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    for msg in messages:
        role = msg.get("role", "unknown")
        text = msg.get("text", "")
        role_label = "👤" if role == "user" else "🤖"
        if len(text) > 500:
            text = text[:500]
            # 确保截断不会留下未闭合的反引号
            if text.count('`') % 2 != 0:
                text = text.rsplit('`', 1)[0]
            text += "..."
        text = _escape_markdown(text)
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
    engine: EngineType = "opencode",
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
        
        resume_token = ResumeToken(engine=engine, value=session_id)
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
        # 先尝试 Markdown 格式发送
        result = await client.send_message(
            chat_id=chat_id,
            text=message,
            message_thread_id=thread_id,
            parse_mode="Markdown",
        )
        if result is not None:
            return True
        # Markdown 解析失败时降级为纯文本
        result = await client.send_message(
            chat_id=chat_id,
            text=message,
            message_thread_id=thread_id,
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
    engine: str | None = typer.Option(
        None, "--engine", "-e", help="Engine filter: opencode, claude, or all (default: all)"
    ),
) -> None:
    """Handoff a session to Telegram for mobile continuation."""
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
    
    # 解析引擎过滤器
    engine_filter: EngineType | None = None
    if engine is not None:
        engine_lower = engine.lower()
        if engine_lower in ("opencode", "claude"):
            engine_filter = cast(EngineType, engine_lower)
        elif engine_lower != "all":
            typer.echo(f"❌ 无效的引擎: {engine}，可选: opencode, claude, all", err=True)
            raise typer.Exit(1)
    
    session_id = session
    session_project = project
    selected_session: SessionInfo | None = None
    
    if session_id is None:
        sessions = _get_recent_sessions(engine=engine_filter, limit=10)
        if not sessions:
            engine_hint = f" ({engine_filter})" if engine_filter else ""
            typer.echo(f"❌ 未找到会话{engine_hint}", err=True)
            raise typer.Exit(1)
        
        typer.echo("\n📲 会话接力 - 将电脑端会话发送到 Telegram 继续对话")
        typer.echo("━" * 50)
        typer.echo("\n📋 最近的会话:\n")
        for i, s in enumerate(sessions[:10], 1):
            title_display = s.title[:35] if s.title else s.project_name
            engine_icon = "🔷" if s.engine == "opencode" else "🟣"
            typer.echo(f"  [{i}] {engine_icon} {s.updated_str}  {title_display}")
        typer.echo("")
        typer.echo("  🔷 = opencode  🟣 = claude")
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
        
        selected_session = sessions[idx]
        session_id = selected_session.id
        if session_project is None:
            session_project = selected_session.project_name
    else:
        # 用户指定了 session ID，需要找到对应的 SessionInfo
        # 先尝试从 opencode 找
        opencode_sessions = _get_opencode_sessions(limit=50)
        for s in opencode_sessions:
            if s.id == session_id:
                selected_session = s
                break
        
        # 再尝试从 claude 找
        if selected_session is None:
            claude_sessions = _get_claude_sessions(limit=50)
            for s in claude_sessions:
                if s.id == session_id:
                    selected_session = s
                    break
        
        if selected_session is None:
            # 创建一个默认的 SessionInfo（假设是 opencode）
            selected_session = SessionInfo(
                id=session_id,
                directory="",
                updated=0,
                title="",
                engine="opencode",
            )
    
    if not session_id:
        typer.echo("❌ 会话 ID 为空", err=True)
        raise typer.Exit(1)
    
    # 验证 project 是否已注册（未注册时仅警告，不阻止 handoff）
    if session_project:
        engine_ids = list_backend_ids()
        projects_config = settings.to_projects_config(
            config_path=config_path, engine_ids=engine_ids
        )
        project_key = session_project.lower()
        if project_key not in projects_config.projects:
            available = list(projects_config.projects.keys())
            typer.echo(f"⚠️  项目 {session_project!r} 未注册，将使用原始名称继续", err=True)
            if available:
                typer.echo(f"   已注册项目: {', '.join(available)}", err=True)
            typer.echo(f"   提示: 可运行 yee88 init {session_project} 注册项目", err=True)
        else:
            # 使用规范化的 project key
            session_project = project_key
    
    session_engine = selected_session.engine
    typer.echo(f"📖 读取会话 {session_id[:20]}... ({session_engine})")
    
    messages = _get_session_messages(selected_session, limit=limit)
    if not messages:
        typer.echo("❌ 无法读取会话消息", err=True)
        raise typer.Exit(1)
    
    async def do_handoff() -> tuple[bool, int | None, bool]:
        project_name = session_project or "unknown"
        context = RunContext(project=project_name.lower(), branch=None)
        
        # 先查找已有的同项目 topic，避免重复创建
        state_path = resolve_state_path(config_path)
        store = TopicStateStore(state_path)
        existing_thread_id = await store.find_thread_for_context(chat_id, context)
        
        thread_id: int | None = None
        reused = False
        
        if existing_thread_id is not None:
            # 尝试复用已有 topic，先验证它在 Telegram 端是否还存在
            resume_token = ResumeToken(engine=session_engine, value=session_id)
            await store.set_session_resume(chat_id, existing_thread_id, resume_token)
            thread_id = existing_thread_id
            reused = True
        
        if thread_id is None:
            # 创建新 topic
            thread_id = await _create_handoff_topic(
                token=token,
                chat_id=chat_id,
                session_id=session_id,
                project=project_name,
                config_path=config_path,
                engine=session_engine,
            )
            reused = False
        
        if thread_id is None:
            return False, None, False
        
        # 设置 topic 默认引擎，确保 Telegram 端继续对话时使用正确引擎
        await store.set_default_engine(chat_id, thread_id, session_engine)
        
        # 从原 session 提取模型 ID，设置为 topic 的 engine override
        model_id = _get_session_model_id(selected_session)
        if model_id:
            override = EngineOverrides(model=model_id)
            await store.set_engine_override(chat_id, thread_id, session_engine, override)
        
        handoff_msg = _format_handoff_message(
            session_id=session_id,
            messages=messages,
            project=session_project,
            engine=session_engine,
        )
        
        success = await _send_to_telegram(
            token=token,
            chat_id=chat_id,
            message=handoff_msg,
            thread_id=thread_id,
        )
        
        # 如果复用的 topic 发送失败（可能已被删除），清理 state 并创建新 topic 重试
        if not success and reused:
            await store.delete_thread(chat_id, thread_id)
            thread_id = await _create_handoff_topic(
                token=token,
                chat_id=chat_id,
                session_id=session_id,
                project=project_name,
                config_path=config_path,
                engine=session_engine,
            )
            if thread_id is None:
                return False, None, False
            reused = False
            await store.set_default_engine(chat_id, thread_id, session_engine)
            if model_id:
                override = EngineOverrides(model=model_id)
                await store.set_engine_override(chat_id, thread_id, session_engine, override)
            success = await _send_to_telegram(
                token=token,
                chat_id=chat_id,
                message=handoff_msg,
                thread_id=thread_id,
            )
        
        return success, thread_id, reused
    
    success, thread_id, reused = anyio.run(do_handoff)
    
    if success:
        if reused:
            typer.echo("✅ 已发送到已有 Topic！")
        else:
            typer.echo("✅ 已创建新 Topic 并发送！")
        typer.echo(f"   Session: {session_id}")
        typer.echo(f"   Engine: {session_engine}")
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
        ctx.invoke(send, session=None, limit=3, project=None, engine=None)