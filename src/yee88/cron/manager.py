import tomllib
import tomli_w
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo
from croniter import croniter
from datetime import datetime
from .models import CronJob

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


class CronManager:
    def __init__(self, config_dir: Path, timezone: str = "Asia/Shanghai"):
        self.file = config_dir / "cron.toml"
        self.jobs: List[CronJob] = []
        self.timezone = ZoneInfo(timezone)

    def _validate_project(self, project: str) -> None:
        if not project:
            return
        
        path = Path(project).expanduser().resolve()
        if path.exists() and path.is_dir():
            return
        
        from ..settings import load_settings_if_exists
        from ..engines import list_backend_ids
        
        result = load_settings_if_exists()
        if result is None:
            return
        
        settings, config_path = result
        engine_ids = list_backend_ids()
        projects_config = settings.to_projects_config(
            config_path=config_path,
            engine_ids=engine_ids
        )
        
        if project.lower() in projects_config.projects:
            return
        
        available = list(projects_config.projects.keys())
        if available:
            raise ValueError(
                f"未知项目: {project}。可用项目: {', '.join(available)}"
            )
        else:
            raise ValueError(
                f"未知项目: {project}。请先使用 'yee88 init' 注册项目"
            )

    def load(self):
        if not self.file.exists():
            self.jobs = []
            return

        with open(self.file, "rb") as f:
            data = tomllib.load(f)

        self.jobs = [
            CronJob(**job)
            for job in data.get("jobs", [])
        ]

    def save(self):
        data = {
            "jobs": [
                {
                    "id": job.id,
                    "schedule": job.schedule,
                    "message": job.message,
                    "project": job.project,
                    "enabled": job.enabled,
                    "last_run": job.last_run,
                    "next_run": job.next_run,
                    "one_time": job.one_time,
                }
                for job in self.jobs
            ]
        }

        with open(self.file, "wb") as f:
            tomli_w.dump(data, f)

    def add(self, job: CronJob) -> None:
        self._validate_project(job.project)

        if any(j.id == job.id for j in self.jobs):
            raise ValueError(f"任务 ID 已存在: {job.id}")

        self.jobs.append(job)
        self.save()

    def remove(self, job_id: str) -> bool:
        original_len = len(self.jobs)
        self.jobs = [j for j in self.jobs if j.id != job_id]

        if len(self.jobs) < original_len:
            self.save()
            return True
        return False

    def get(self, job_id: str) -> Optional[CronJob]:
        for job in self.jobs:
            if job.id == job_id:
                return job
        return None

    def list(self) -> List[CronJob]:
        return self.jobs

    def enable(self, job_id: str) -> bool:
        for job in self.jobs:
            if job.id == job_id:
                job.enabled = True
                self.save()
                return True
        return False

    def disable(self, job_id: str) -> bool:
        for job in self.jobs:
            if job.id == job_id:
                job.enabled = False
                self.save()
                return True
        return False

    def get_due_jobs(self) -> List[CronJob]:
        now = datetime.now(self.timezone)
        due = []
        one_time_completed = []

        for job in self.jobs:
            if not job.enabled:
                continue

            if job.one_time:
                try:
                    exec_time = datetime.fromisoformat(job.schedule)
                    if exec_time.tzinfo is None:
                        exec_time = exec_time.replace(tzinfo=self.timezone)
                    if exec_time <= now:
                        due.append(job)
                        one_time_completed.append(job.id)
                except Exception:
                    continue
            else:
                try:
                    if job.last_run:
                        base = datetime.fromisoformat(job.last_run)
                        if base.tzinfo is None:
                            base = base.replace(tzinfo=self.timezone)
                        itr = croniter(job.schedule, base)
                        next_run = itr.get_next(datetime)
                        if next_run <= now:
                            due.append(job)
                            job.last_run = now.isoformat()
                            job.next_run = itr.get_next(datetime).isoformat()
                    else:
                        itr = croniter(job.schedule, now)
                        prev_run = itr.get_prev(datetime)
                        if prev_run.date() == now.date():
                            due.append(job)
                            job.last_run = now.isoformat()
                            job.next_run = itr.get_next(datetime).isoformat()
                except Exception:
                    continue

        if one_time_completed:
            self.jobs = [j for j in self.jobs if j.id not in one_time_completed]

        if due:
            self.save()

        return due
