from pathlib import Path
from typing import Callable, Awaitable, List

import anyio
from watchfiles import watch

from ..logging import get_logger
from .manager import CronManager

logger = get_logger()


async def watch_cron_config(
    cron_file: Path,
    manager: CronManager,
    on_reload: Callable[[List[str]], Awaitable[None]] | None = None,
) -> None:
    if not cron_file.exists():
        logger.warning("cron.watch.file_not_found", path=str(cron_file))
        return

    logger.info("cron.watch.started", path=str(cron_file))

    try:
        for changes in watch(str(cron_file)):
            for change_type, path in changes:
                if Path(path).name == "cron.toml":
                    logger.info(
                        "cron.watch.file_changed",
                        path=path,
                        change_type=change_type.name,
                    )

                    changed_jobs = manager.reload_jobs()

                    if changed_jobs:
                        logger.info(
                            "cron.watch.reloaded",
                            changed_count=len(changed_jobs),
                            changed_jobs=changed_jobs,
                        )

                        if on_reload:
                            await on_reload(changed_jobs)
                    else:
                        logger.debug("cron.watch.no_changes_detected")

                    break
    except anyio.get_cancelled_exc_class():
        logger.info("cron.watch.cancelled")
        raise
    except Exception as exc:
        logger.error("cron.watch.error", error=str(exc))
        raise
