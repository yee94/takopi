import asyncio
from typing import Callable, Awaitable
from anyio.abc import TaskGroup
from .manager import CronManager
from .models import CronJob
from ..logging import get_logger

logger = get_logger()


class CronScheduler:
    def __init__(
        self,
        manager: CronManager,
        callback: Callable[[CronJob], Awaitable[None]],
        task_group: TaskGroup,
    ):
        self.manager = manager
        self.callback = callback
        self.task_group = task_group
        self.running = False

    async def start(self):
        self.running = True
        self.manager.load()
        logger.info("cron.scheduler.started", job_count=len(self.manager.jobs))

        cycle = 0
        while self.running:
            cycle += 1
            self.manager.load()
            logger.info("cron.scheduler.check_cycle", cycle=cycle, job_count=len(self.manager.jobs))
            due_jobs = self.manager.get_due_jobs()

            if due_jobs:
                logger.info("cron.scheduler.due_jobs_found", cycle=cycle, count=len(due_jobs), job_ids=[j.id for j in due_jobs])
            else:
                logger.info("cron.scheduler.no_due_jobs", cycle=cycle)

            for job in due_jobs:
                logger.info("cron.scheduler.dispatching_job", job_id=job.id, message=job.message[:50])
                self.task_group.start_soon(self._run_job_safe, job)

            logger.info("cron.scheduler.sleeping", cycle=cycle, seconds=60)
            await asyncio.sleep(60)

    async def _run_job_safe(self, job: CronJob) -> None:
        logger.info("cron.job.executing", job_id=job.id)
        try:
            await self.callback(job)
            logger.info("cron.job.completed", job_id=job.id)
        except Exception as exc:
            logger.error("cron.job.failed", job_id=job.id, error=str(exc))

    def stop(self):
        self.running = False
        logger.info("cron.scheduler.stopped")
