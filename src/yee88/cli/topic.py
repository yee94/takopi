"""CLI command to create and bind a topic/thread from the command line."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from ..config import ConfigError, HOME_CONFIG_PATH, load_or_init_config, write_config
from ..config_migrations import migrate_config
from ..engines import list_backend_ids
from ..ids import RESERVED_CHAT_COMMANDS, RESERVED_CLI_COMMANDS
from ..settings import load_settings, validate_settings_data
from ..topics.factory import create_topic_backend
from ..utils.git import resolve_default_base, resolve_main_worktree_root


def _get_current_branch(cwd: Path) -> str | None:
    """Get current git branch name."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            return branch if branch else None
    except FileNotFoundError:
        pass
    return None


def _get_project_root(cwd: Path) -> Path:
    """Get git project root, handling worktrees."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            common_dir = result.stdout.strip()
            if common_dir:
                bare_result = subprocess.run(
                    ["git", "rev-parse", "--is-bare-repository"],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if bare_result.stdout.strip() == "true":
                    return cwd
                return Path(common_dir).parent
    except FileNotFoundError:
        pass
    return cwd


def _check_alias_conflict(alias: str) -> str | None:
    """Check if project alias conflicts with engine IDs or reserved commands."""
    reserved = RESERVED_CLI_COMMANDS | RESERVED_CHAT_COMMANDS
    engine_ids = set(list_backend_ids())

    alias_lower = alias.lower()
    if alias_lower in engine_ids:
        return f"engine ID '{alias_lower}'"
    if alias_lower in reserved:
        return f"reserved command '{alias_lower}'"
    return None


def _generate_topic_title(project: str, branch: str | None) -> str:
    """Generate topic title like 'project @branch'."""
    if branch:
        return f"{project} @{branch}"
    return project


def _ensure_project(
    project: str,
    project_root: Path,
    config_path: Path,
) -> None:
    """Ensure project is registered in config, auto-init if needed."""
    config, cfg_path = load_or_init_config()

    if cfg_path.exists():
        applied = migrate_config(config, config_path=cfg_path)
        if applied:
            write_config(config, cfg_path)

    projects = config.setdefault("projects", {})
    if not isinstance(projects, dict):
        raise ConfigError(f"Invalid `projects` in {cfg_path}; expected a table.")

    if project in projects:
        return

    worktree_base = resolve_default_base(project_root)

    entry: dict[str, object] = {
        "path": str(project_root),
        "worktrees_dir": ".worktrees",
    }
    if worktree_base:
        entry["worktree_base"] = worktree_base

    projects[project] = entry
    write_config(config, cfg_path)
    typer.echo(f"auto-registered project '{project}'")


def run_topic(
    *,
    project: str | None,
    branch: str | None,
    delete: bool,
    config_path: Path | None,
) -> None:
    """Create or delete a topic/thread bound to project/branch."""
    cwd = Path.cwd()

    project_root = _get_project_root(cwd)

    cfg_path = config_path or HOME_CONFIG_PATH
    try:
        settings, cfg_path = load_settings(cfg_path)
    except ConfigError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from None

    if project is None:
        project = project_root.name.lower()
        if project.endswith(".git"):
            project = project[:-4]

    project_key = project.lower()

    project_exists = project_key in settings.projects or project in settings.projects

    if not project_exists:
        conflict_reason = _check_alias_conflict(project)
        if conflict_reason:
            typer.echo(
                f"error: project alias '{project}' conflicts with {conflict_reason}.\n"
                f"please specify a different alias: yee88 topic init <alias>",
                err=True,
            )
            raise typer.Exit(code=1)

    if branch is None:
        branch = _get_current_branch(cwd)

    if not delete and not project_exists:
        try:
            _ensure_project(project_key, project_root, cfg_path)
            settings, cfg_path = load_settings(cfg_path)
        except ConfigError as e:
            typer.echo(f"warning: failed to auto-init project: {e}", err=True)

    if project_key not in settings.projects and project not in settings.projects:
        typer.echo(
            f"error: project '{project}' not found in config. "
            f"Run `yee88 init {project}` first.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        backend = create_topic_backend(settings, cfg_path)
    except ConfigError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"project: {project}")
    typer.echo(f"branch: {branch or '<none>'}")
    typer.echo(f"transport: {backend.name}")
    typer.echo("")

    if delete:
        typer.echo("deleting topic binding...")
        result = asyncio.run(
            backend.delete_topic(
                project=project,
                branch=branch,
                config_path=cfg_path,
            )
        )

        if not result:
            typer.echo(f"error: no topic found for {project}{' @' + branch if branch else ''}", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"deleted topic binding for: {project}{' @' + branch if branch else ''}")
        typer.echo("")
        typer.echo("done! the topic has been unbound from yee88.")
    else:
        typer.echo("creating topic...")
        result = asyncio.run(
            backend.create_topic(
                project=project,
                branch=branch,
                config_path=cfg_path,
            )
        )

        if result is None:
            typer.echo("error: failed to create topic", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"created topic: {result.title} (thread_id: {result.thread_id})")
        typer.echo("")
        typer.echo("done! check your chat for the new topic.")
