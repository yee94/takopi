from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

import typer

from ..config import HOME_CONFIG_PATH, load_or_init_config
from ..lockfile import _pid_running, _read_lock_info, lock_path_for_config
from ..logging import get_logger

logger = get_logger(__name__)

_reload_requested = False


def _get_exec_args() -> tuple[str, list[str]]:
    import shutil
    yee88_path = shutil.which("yee88")
    if yee88_path:
        return yee88_path, ["yee88"]
    executable = sys.executable
    args = [executable, "-m", "yee88"]
    return executable, args


def request_reload() -> None:
    global _reload_requested
    _reload_requested = True


def should_reload() -> bool:
    return _reload_requested


def do_exec_restart() -> None:
    logger.info("reload.exec_restart", pid=os.getpid())
    sys.stdout.flush()
    sys.stderr.flush()
    
    executable, args = _get_exec_args()
    os.execv(executable, args)


def _handle_sighup(signum: int, frame: object) -> None:
    logger.info("reload.signal_received", signal="SIGHUP", pid=os.getpid())
    request_reload()


def install_reload_handler() -> None:
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _handle_sighup)
        logger.debug("reload.handler_installed", signal="SIGHUP")


def _find_running_instance(config_path: Path | None = None) -> tuple[int, Path] | None:
    if config_path is None:
        try:
            _, config_path = load_or_init_config()
        except Exception:
            config_path = HOME_CONFIG_PATH
    
    lock_path = lock_path_for_config(config_path)
    lock_info = _read_lock_info(lock_path)
    
    if lock_info is None or lock_info.pid is None:
        return None
    
    if not _pid_running(lock_info.pid):
        lock_path.unlink(missing_ok=True)
        return None
    
    return lock_info.pid, lock_path


def send_reload_signal(config_path: Path | None = None) -> bool:
    result = _find_running_instance(config_path)
    
    if result is None:
        return False
    
    pid, _ = result
    
    if pid == os.getpid():
        return False
    
    try:
        os.kill(pid, signal.SIGHUP)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def run_reload(
    config_path: Path | None = None,
    timeout: float = 10.0,
) -> None:
    result = _find_running_instance(config_path)
    
    if result is None:
        typer.echo("No running yee88 instance found.", err=True)
        raise typer.Exit(code=1)
    
    pid, lock_path = result
    
    if pid == os.getpid():
        typer.echo("Cannot reload self. Run from another terminal.", err=True)
        raise typer.Exit(code=1)
    
    typer.echo(f"Sending reload signal to yee88 (PID: {pid})...")
    
    try:
        os.kill(pid, signal.SIGHUP)
    except ProcessLookupError:
        typer.echo("Process already exited.", err=True)
        lock_path.unlink(missing_ok=True)
        raise typer.Exit(code=1)
    except PermissionError:
        typer.echo(f"Permission denied: cannot signal PID {pid}", err=True)
        raise typer.Exit(code=1)
    
    typer.echo("✓ Reload signal sent. Process will restart with new code.")


def reload_command(
    config_path: Path | None = typer.Option(
        None,
        "--config-path",
        help="Path to config file",
    ),
    timeout: float = typer.Option(
        10.0,
        "--timeout",
        help="Timeout in seconds",
    ),
) -> None:
    run_reload(config_path=config_path, timeout=timeout)
