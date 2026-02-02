from dataclasses import dataclass
from typing import Optional


@dataclass
class CronJob:
    id: str
    schedule: str
    message: str
    project: str
    enabled: bool = True
    last_run: str = ""
    next_run: str = ""
    one_time: bool = False
    engine: Optional[str] = None
    model: Optional[str] = None
