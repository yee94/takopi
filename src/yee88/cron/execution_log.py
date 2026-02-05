from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from ..utils.json_state import atomic_write_json


@dataclass
class CronExecutionRecord:
    job_id: str
    scheduled_time: str
    executed_at: str
    status: str
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "scheduled_time": self.scheduled_time,
            "executed_at": self.executed_at,
            "status": self.status,
            "error_message": self.error_message,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> CronExecutionRecord:
        return cls(
            job_id=data["job_id"],
            scheduled_time=data["scheduled_time"],
            executed_at=data["executed_at"],
            status=data["status"],
            error_message=data.get("error_message"),
        )


@dataclass
class CronExecutionLog:
    records: List[CronExecutionRecord] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "records": [r.to_dict() for r in self.records],
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> CronExecutionLog:
        return cls(
            records=[CronExecutionRecord.from_dict(r) for r in data.get("records", [])],
        )


class ExecutionLogger:
    def __init__(self, config_dir: Path):
        self.file = config_dir / "cron_execution_log.json"
        self._log = CronExecutionLog()
        self._load()
    
    def _load(self) -> None:
        if not self.file.exists():
            self._log = CronExecutionLog()
            return
        
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._log = CronExecutionLog.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            self._log = CronExecutionLog()
    
    def _save(self) -> None:
        atomic_write_json(self.file, self._log.to_dict())
    
    def record_pending(self, job_id: str, scheduled_time: datetime) -> None:
        record = CronExecutionRecord(
            job_id=job_id,
            scheduled_time=scheduled_time.isoformat(),
            executed_at=datetime.now().isoformat(),
            status="pending",
        )
        self._log.records.append(record)
        self._save()
    
    def update_completed(self, job_id: str, scheduled_time: datetime) -> None:
        for record in reversed(self._log.records):
            if (record.job_id == job_id 
                and record.scheduled_time == scheduled_time.isoformat()
                and record.status == "pending"):
                record.status = "completed"
                self._save()
                return
    
    def update_failed(self, job_id: str, scheduled_time: datetime, error: str) -> None:
        for record in reversed(self._log.records):
            if (record.job_id == job_id 
                and record.scheduled_time == scheduled_time.isoformat()
                and record.status == "pending"):
                record.status = "failed"
                record.error_message = error
                self._save()
                return
    
    def get_missed_executions(
        self, 
        job_id: str, 
        schedule: str, 
        last_run: Optional[str],
        timezone,
    ) -> List[datetime]:
        from croniter import croniter
        
        now = datetime.now(timezone)
        
        if last_run:
            start_time = datetime.fromisoformat(last_run)
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone)
        else:
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        missed_times = []
        itr = croniter(schedule, start_time)
        
        while True:
            next_time = itr.get_next(datetime)
            if next_time > now:
                break
            
            if not self._is_executed(job_id, next_time):
                missed_times.append(next_time)
        
        return missed_times
    
    def _is_executed(self, job_id: str, scheduled_time: datetime) -> bool:
        scheduled_iso = scheduled_time.isoformat()
        for record in reversed(self._log.records):
            if record.job_id == job_id and record.scheduled_time == scheduled_iso:
                return record.status in ("completed", "failed")
        return False
    
    def cleanup_old_records(self, days: int = 7) -> None:
        cutoff = datetime.now() - timedelta(days=days)
        self._log.records = [
            r for r in self._log.records 
            if datetime.fromisoformat(r.scheduled_time) > cutoff
        ]
        self._save()