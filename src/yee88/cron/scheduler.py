import asyncio
from typing import Callable, Awaitable
from .manager import CronManager
from .models import CronJob


class CronScheduler:
    def __init__(self, manager: CronManager, callback: Callable[[CronJob], Awaitable[None]]):
        self.manager = manager
        self.callback = callback
        self.running = False

    async def start(self):
        self.running = True
        self.manager.load()

        while self.running:
            due_jobs = self.manager.get_due_jobs()

            for job in due_jobs:
                try:
                    await self.callback(job)
                except Exception:
                    pass

            await asyncio.sleep(60)

    def stop(self):
        self.running = False
