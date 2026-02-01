"""Tests for CronScheduler - verify scheduler starts and executes jobs correctly."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from yee88.cron.scheduler import CronScheduler
from yee88.cron.manager import CronManager
from yee88.cron.models import CronJob


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def cron_manager(tmp_config_dir: Path) -> CronManager:
    return CronManager(tmp_config_dir, timezone="Asia/Shanghai")


@pytest.fixture
def mock_callback() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_task_group() -> MagicMock:
    tg = MagicMock()
    tg.start_soon = MagicMock()
    return tg


class TestCronSchedulerBasic:

    def test_scheduler_init(
        self,
        cron_manager: CronManager,
        mock_callback: AsyncMock,
        mock_task_group: MagicMock,
    ) -> None:
        scheduler = CronScheduler(cron_manager, mock_callback, mock_task_group)
        
        assert scheduler.manager is cron_manager
        assert scheduler.callback is mock_callback
        assert scheduler.task_group is mock_task_group
        assert scheduler.running is False

    def test_scheduler_stop(
        self,
        cron_manager: CronManager,
        mock_callback: AsyncMock,
        mock_task_group: MagicMock,
    ) -> None:
        scheduler = CronScheduler(cron_manager, mock_callback, mock_task_group)
        scheduler.running = True
        
        scheduler.stop()
        
        assert scheduler.running is False


class TestCronSchedulerJobExecution:

    @pytest.mark.anyio
    async def test_run_job_safe_calls_callback(
        self,
        cron_manager: CronManager,
        mock_callback: AsyncMock,
        mock_task_group: MagicMock,
    ) -> None:
        scheduler = CronScheduler(cron_manager, mock_callback, mock_task_group)
        
        job = CronJob(
            id="test-job",
            schedule="* * * * *",
            message="Test",
            project="",
            enabled=True,
        )
        
        await scheduler._run_job_safe(job)
        
        mock_callback.assert_called_once_with(job)

    @pytest.mark.anyio
    async def test_run_job_safe_handles_exception(
        self,
        cron_manager: CronManager,
        mock_task_group: MagicMock,
    ) -> None:
        async def failing_callback(job: CronJob) -> None:
            raise RuntimeError("Callback failed")
        
        scheduler = CronScheduler(cron_manager, failing_callback, mock_task_group)
        
        job = CronJob(
            id="test-job",
            schedule="* * * * *",
            message="Test",
            project="",
            enabled=True,
        )
        
        await scheduler._run_job_safe(job)


class TestCronSchedulerTimezone:

    def test_manager_uses_beijing_timezone(self, tmp_config_dir: Path) -> None:
        manager = CronManager(tmp_config_dir, timezone="Asia/Shanghai")
        
        assert manager.timezone == ZoneInfo("Asia/Shanghai")

    def test_manager_default_timezone_is_beijing(self, tmp_config_dir: Path) -> None:
        manager = CronManager(tmp_config_dir)
        
        assert manager.timezone == ZoneInfo("Asia/Shanghai")

    def test_get_due_jobs_with_timezone(self, tmp_config_dir: Path) -> None:
        manager = CronManager(tmp_config_dir, timezone="Asia/Shanghai")
        
        past_time = datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(hours=1)
        job = CronJob(
            id="past-job",
            schedule=past_time.isoformat(),
            message="Past job",
            project="",
            enabled=True,
            one_time=True,
        )
        manager.jobs.append(job)
        manager.save()
        
        due_jobs = manager.get_due_jobs()
        
        assert len(due_jobs) == 1
        assert due_jobs[0].id == "past-job"