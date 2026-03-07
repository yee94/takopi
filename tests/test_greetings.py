from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

from yee88.telegram.greetings import (
    _AFTERNOON,
    _EVENING,
    _HOLIDAYS,
    _LATE_NIGHT,
    _MORNING,
    _WEEKDAY_EXTRAS,
    _absence_quip,
    build_greeting,
)


class TestTimeOfDayPool:
    """Greeting should come from the correct time-of-day pool."""

    def test_morning(self) -> None:
        now = datetime(2025, 3, 5, 8, 0)  # Wednesday 8am
        for _ in range(20):
            g = build_greeting(now=now)
            first_line = g.split("\n")[0]
            assert first_line in _MORNING

    def test_afternoon(self) -> None:
        now = datetime(2025, 3, 5, 14, 0)  # Wednesday 2pm
        for _ in range(20):
            g = build_greeting(now=now)
            first_line = g.split("\n")[0]
            assert first_line in _AFTERNOON

    def test_evening(self) -> None:
        now = datetime(2025, 3, 5, 20, 0)  # Wednesday 8pm
        for _ in range(20):
            g = build_greeting(now=now)
            first_line = g.split("\n")[0]
            assert first_line in _EVENING

    def test_late_night(self) -> None:
        now = datetime(2025, 3, 6, 2, 0)  # Thursday 2am
        for _ in range(20):
            g = build_greeting(now=now)
            first_line = g.split("\n")[0]
            assert first_line in _LATE_NIGHT


class TestWeekdaySeasoning:
    """Monday / Friday / weekend should get an extra line."""

    def test_monday_extra(self) -> None:
        now = datetime(2025, 3, 3, 10, 0)  # Monday 10am
        found_extra = False
        for _ in range(50):
            g = build_greeting(now=now)
            lines = g.split("\n")
            if len(lines) > 1:
                assert lines[1] in _WEEKDAY_EXTRAS[0]
                found_extra = True
        assert found_extra, "Expected Monday extra at least once in 50 tries"

    def test_friday_extra(self) -> None:
        now = datetime(2025, 3, 7, 15, 0)  # Friday 3pm
        found_extra = False
        for _ in range(50):
            g = build_greeting(now=now)
            lines = g.split("\n")
            if len(lines) > 1:
                assert lines[1] in _WEEKDAY_EXTRAS[4]
                found_extra = True
        assert found_extra, "Expected Friday extra at least once in 50 tries"

    def test_wednesday_no_weekday_extra(self) -> None:
        now = datetime(2025, 3, 5, 10, 0)  # Wednesday 10am
        for _ in range(20):
            g = build_greeting(now=now)
            # Wednesday has no weekday extra, so greeting should be single line
            assert "\n" not in g


class TestHolidays:
    """Holiday dates should produce a holiday extra line."""

    def test_new_year(self) -> None:
        now = datetime(2025, 1, 1, 10, 0)
        found = False
        for _ in range(30):
            g = build_greeting(now=now)
            lines = g.split("\n")
            if len(lines) > 1:
                assert lines[1] in _HOLIDAYS[(1, 1)]
                found = True
        assert found

    def test_labor_day(self) -> None:
        now = datetime(2025, 5, 1, 14, 0)
        found = False
        for _ in range(30):
            g = build_greeting(now=now)
            lines = g.split("\n")
            if len(lines) > 1:
                assert lines[1] in _HOLIDAYS[(5, 1)]
                found = True
        assert found

    def test_holiday_overrides_weekday(self) -> None:
        # 2027-01-01 is a Friday; holiday should take priority over Friday extra
        now = datetime(2027, 1, 1, 10, 0)
        for _ in range(30):
            g = build_greeting(now=now)
            lines = g.split("\n")
            if len(lines) > 1:
                assert lines[1] in _HOLIDAYS[(1, 1)]


class TestAbsenceQuip:
    """_absence_quip should produce human-like time-gap remarks."""

    def test_no_last_seen(self) -> None:
        assert _absence_quip(None, datetime.now()) is None

    def test_just_restarted(self) -> None:
        now = datetime(2025, 3, 5, 10, 0)
        last = now - timedelta(minutes=2)
        assert _absence_quip(last, now) is None

    def test_minutes_ago(self) -> None:
        now = datetime(2025, 3, 5, 10, 0)
        last = now - timedelta(minutes=30)
        quip = _absence_quip(last, now)
        assert quip is not None
        assert "30 分钟" in quip

    def test_hours_ago(self) -> None:
        now = datetime(2025, 3, 5, 10, 0)
        last = now - timedelta(hours=5)
        quip = _absence_quip(last, now)
        assert quip is not None
        assert "5 小时" in quip

    def test_one_day(self) -> None:
        now = datetime(2025, 3, 5, 10, 0)
        last = now - timedelta(days=1)
        quip = _absence_quip(last, now)
        assert quip is not None
        assert "一天" in quip

    def test_several_days(self) -> None:
        now = datetime(2025, 3, 5, 10, 0)
        last = now - timedelta(days=4)
        quip = _absence_quip(last, now)
        assert quip is not None
        assert "4 天" in quip

    def test_weeks(self) -> None:
        now = datetime(2025, 3, 5, 10, 0)
        last = now - timedelta(days=14)
        quip = _absence_quip(last, now)
        assert quip is not None
        assert "14 天" in quip

    def test_months(self) -> None:
        now = datetime(2025, 3, 5, 10, 0)
        last = now - timedelta(days=45)
        quip = _absence_quip(last, now)
        assert quip is not None
        assert "45 天" in quip


class TestLockfileMtime:
    """build_greeting should pick up lockfile mtime for absence quips."""

    def test_with_lockfile(self, tmp_path: Path) -> None:
        config = tmp_path / "yee88.toml"
        config.write_text("")
        lock = tmp_path / "yee88.lock"
        lock.write_text("{}")
        # Set mtime to 3 days ago
        three_days_ago = time.time() - 3 * 86400
        import os

        os.utime(lock, (three_days_ago, three_days_ago))

        now = datetime(2025, 3, 5, 10, 0)  # Wednesday, no weekday extra
        found_quip = False
        for _ in range(30):
            g = build_greeting(now=now, config_path=config)
            if "天" in g:
                found_quip = True
                break
        assert found_quip

    def test_without_lockfile(self, tmp_path: Path) -> None:
        config = tmp_path / "yee88.toml"
        config.write_text("")
        # No lock file exists
        now = datetime(2025, 3, 5, 10, 0)
        g = build_greeting(now=now, config_path=config)
        # Should still produce a greeting, just no absence quip
        assert len(g) > 0