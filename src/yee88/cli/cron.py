from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import typer

from ..config import HOME_CONFIG_PATH
from ..cron.manager import CronManager
from ..cron.models import CronJob
from ..settings import load_settings_if_exists
from ..engines import list_backend_ids

app = typer.Typer(help="Manage yee88 cron jobs")


def get_cron_manager() -> CronManager:
    return CronManager(HOME_CONFIG_PATH.parent)


def _validate_project(project: str) -> None:
    if not project:
        return
    result = load_settings_if_exists()
    if result is None:
        raise ValueError(f"未找到配置文件，无法验证项目: {project}")
    settings, config_path = result
    engine_ids = list_backend_ids()
    projects_config = settings.to_projects_config(config_path=config_path, engine_ids=engine_ids)
    if project.lower() not in projects_config.projects:
        available = list(projects_config.projects.keys())
        if available:
            raise ValueError(f"未知项目: {project}。可用项目: {', '.join(available)}")
        else:
            raise ValueError(f"未知项目: {project}。请先使用 'yee88 init' 注册项目")


def _parse_one_time(schedule: str) -> str:
    """解析一次性任务时间，支持相对时间和 ISO 8601 格式。"""
    now = datetime.now()

    # 相对时间格式: +30s, +5m, +2h, +1d
    if schedule.startswith("+"):
        match = re.match(r"\+(\d+)([smhd])", schedule)
        if not match:
            raise ValueError(
                f"无效的时间格式: {schedule}。使用 +30s, +5m, +2h, +1d 或 ISO 8601 (2026-02-01T10:00:00)"
            )

        value, unit = int(match.group(1)), match.group(2)
        delta = {
            "s": timedelta(seconds=value),
            "m": timedelta(minutes=value),
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
        }[unit]

        return (now + delta).isoformat()

    # ISO 8601 格式
    try:
        dt = datetime.fromisoformat(schedule)
        if dt <= now:
            raise ValueError("执行时间必须在未来")
        return dt.isoformat()
    except ValueError as e:
        if "执行时间必须在未来" in str(e):
            raise
        raise ValueError(
            f"无效的时间格式: {schedule}。使用 +30s, +5m, +2h, +1d 或 ISO 8601 (2026-02-01T10:00:00)"
        )


@app.command()
def add(
    id: str = typer.Argument(...),
    schedule: str = typer.Argument(...),
    message: str = typer.Argument(...),
    project: str = typer.Option("", "--project", "-p", help="项目别名（可选，如 takopi）"),
    one_time: bool = typer.Option(False, "--one-time", "-o", help="一次性任务，执行后自动删除"),
):
    try:
        manager = get_cron_manager()
        manager.load()

        _validate_project(project)

        if one_time:
            schedule = _parse_one_time(schedule)

        job = CronJob(
            id=id,
            schedule=schedule,
            message=message,
            project=project,
            enabled=True,
            one_time=one_time,
        )

        manager.add(job)

        if one_time:
            typer.echo(f"✅ 已添加一次性任务: {id}")
            typer.echo(f"   执行时间: {schedule[:19]}")
        else:
            typer.echo(f"✅ 已添加定时任务: {id}")
            typer.echo(f"   时间: {schedule}")
        if project:
            typer.echo(f"   项目: {project}")
        typer.echo(f"   消息: {message}")

    except ValueError as e:
        typer.echo(f"❌ 错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def list(
    show_all: bool = typer.Option(False, "--all", "-a"),
):
    manager = get_cron_manager()
    manager.load()

    jobs = manager.list()

    if not jobs:
        typer.echo("暂无定时任务")
        return

    if not show_all:
        jobs = [j for j in jobs if j.enabled]

    typer.echo(f"{'ID':<20} {'TYPE':<8} {'SCHEDULE':<20} {'STATUS':<10} {'PROJECT'}")
    typer.echo("-" * 90)

    for job in jobs:
        status = "✓ enabled" if job.enabled else "✗ disabled"
        job_type = "once" if job.one_time else "cron"
        schedule_display = job.schedule[:19] if job.one_time else job.schedule
        if len(schedule_display) > 20:
            schedule_display = schedule_display[:17] + "..."
        project_display = job.project
        if len(project_display) > 25:
            project_display = "..." + project_display[-22:]
        typer.echo(f"{job.id:<20} {job_type:<8} {schedule_display:<20} {status:<10} {project_display}")


@app.command()
def enable(
    id: str = typer.Argument(...),
):
    manager = get_cron_manager()
    manager.load()

    if manager.enable(id):
        typer.echo(f"✅ 已启用: {id}")
    else:
        typer.echo(f"❌ 未找到任务: {id}", err=True)
        raise typer.Exit(1)


@app.command()
def disable(
    id: str = typer.Argument(...),
):
    manager = get_cron_manager()
    manager.load()

    if manager.disable(id):
        typer.echo(f"⏸️  已禁用: {id}")
    else:
        typer.echo(f"❌ 未找到任务: {id}", err=True)
        raise typer.Exit(1)


@app.command()
def remove(
    id: str = typer.Argument(...),
    force: bool = typer.Option(False, "--force", "-f"),
):
    manager = get_cron_manager()
    manager.load()

    if not force:
        confirm = typer.confirm(f"确定要删除任务 '{id}' 吗？")
        if not confirm:
            typer.echo("已取消")
            raise typer.Exit(0)

    if manager.remove(id):
        typer.echo(f"🗑️  已删除: {id}")
    else:
        typer.echo(f"❌ 未找到任务: {id}", err=True)
        raise typer.Exit(1)


@app.command()
def run(
    id: str = typer.Argument(...),
):
    manager = get_cron_manager()
    manager.load()

    job = manager.get(id)
    if not job:
        typer.echo(f"❌ 未找到任务: {id}", err=True)
        raise typer.Exit(1)

    typer.echo(f"🚀 执行任务: {id}")
    typer.echo(f"   路径: {job.project}")
    typer.echo(f"   消息: {job.message}")
    typer.echo(f"   计划时间: {job.schedule}")
    typer.echo("✅ 测试执行完成")
