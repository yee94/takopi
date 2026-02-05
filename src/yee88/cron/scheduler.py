import asyncio
from datetime import datetime
from typing import Callable, Awaitable, Optional
from anyio.abc import TaskGroup
from .manager import CronManager
from .models import CronJob
from .execution_log import ExecutionLogger
from ..logging import get_logger

logger = get_logger()


CRON_PROMPT_PREFIX = "[这是一个定时任务的触发动作，不是用户主动询问。请直接处理并返回要求的内容即可，不需要添加任何前缀或声明。]\n\n"


class CronScheduler:
    def __init__(
        self,
        manager: CronManager,
        callback: Callable[[CronJob, Optional[datetime]], Awaitable[None]],
        task_group: TaskGroup,
    ):
        self.manager = manager
        self.callback = callback
        self.task_group = task_group
        self.running = False
        self.execution_logger = ExecutionLogger(manager.file.parent)

    async def start(self):
        self.running = True
        self.manager.load()
        
        await self._compensate_missed_executions()
        
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

            now = datetime.now(self.manager.timezone)
            for job in due_jobs:
                logger.info("cron.scheduler.dispatching_job", job_id=job.id, message=job.message[:50])
                scheduled_time = now if not job.one_time else datetime.fromisoformat(job.schedule)
                self.task_group.start_soon(self._run_job_safe, job, scheduled_time)

            logger.info("cron.scheduler.sleeping", cycle=cycle, seconds=60)
            await asyncio.sleep(60)

    async def _compensate_missed_executions(self) -> None:
        for job in self.manager.jobs:
            if not job.enabled or job.one_time:
                continue
            
            missed_times = self.execution_logger.get_missed_executions(
                job_id=job.id,
                schedule=job.schedule,
                last_run=job.last_run,
                timezone=self.manager.timezone,
            )
            
            if missed_times:
                logger.info(
                    "cron.compensation.found_missed",
                    job_id=job.id,
                    missed_count=len(missed_times),
                )
                for missed_time in missed_times:
                    logger.info(
                        "cron.compensation.dispatching",
                        job_id=job.id,
                        missed_time=missed_time.isoformat(),
                    )
                    self.task_group.start_soon(self._run_job_safe, job, missed_time)

    async def _run_job_safe(self, job: CronJob, scheduled_time: datetime | None) -> None:
        time_str = scheduled_time.isoformat() if scheduled_time else "now"
        logger.info("cron.job.executing", job_id=job.id, scheduled_time=time_str)
        
        if scheduled_time is not None:
            self.execution_logger.record_pending(job.id, scheduled_time)
        
        try:
            await self.callback(job, scheduled_time)
            if scheduled_time is not None:
                self.execution_logger.update_completed(job.id, scheduled_time)
            logger.info("cron.job.completed", job_id=job.id)
        except Exception as exc:
            if scheduled_time is not None:
                self.execution_logger.update_failed(job.id, scheduled_time, str(exc))
            logger.error("cron.job.failed", job_id=job.id, error=str(exc))

    def stop(self):
        self.running = False
        logger.info("cron.scheduler.stopped")