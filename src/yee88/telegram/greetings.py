"""Random, human-like startup greetings for the Telegram bot.

The greeting is composed of three optional layers:

1. **Time-aware greeting** – different pools for morning / afternoon / evening / late-night.
2. **Weekday & holiday seasoning** – Monday blues, Friday vibes, weekend surprise,
   and a handful of Chinese holidays / solar terms.
3. **Absence quip** – a playful remark about how long the bot has been idle,
   derived from the lockfile's mtime.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Time-of-day pools
# ---------------------------------------------------------------------------

_MORNING: list[str] = [
    "早上好老板，新的一天开始了 ☀️",
    "早啊，今天也要加油鸭 🦆",
    "起得挺早嘛，咖啡喝了没? ☕",
    "清晨打卡，精神满满 💪",
]

_AFTERNOON: list[str] = [
    "下午好，午觉睡够了没? 😪",
    "下午茶时间到，顺便干点活? 🍵",
    "午后开工，效率拉满 🚀",
    "下午好老板，来活儿了是吧 🤓",
]

_EVENING: list[str] = [
    "晚上好，还在肝呢? 🌙",
    "这个点了还在忙，注意身体啊 🫶",
    "夜间模式启动，悄悄干活 🤫",
    "晚上好老板，夜猫子模式开启 🦉",
]

_LATE_NIGHT: list[str] = [
    "都这个点了还不睡? 你是真的卷 🥲",
    "凌晨了啊老板，身体要紧 😴",
    "深夜食堂开张，有啥急活? 🌃",
    "这么晚了...不会又出 bug 了吧 🫠",
]

# ---------------------------------------------------------------------------
# Weekday seasoning
# ---------------------------------------------------------------------------

_WEEKDAY_EXTRAS: dict[int, list[str]] = {
    # Monday = 0
    0: [
        "周一综合征发作中... 😮‍💨",
        "又到周一了，深呼吸 🫁",
    ],
    4: [
        "周五了! 再撑一下就解放 🎉",
        "Friday! 摸鱼的心蠢蠢欲动 🐟",
    ],
    5: [
        "周末还在干活? 老板你太拼了 😳",
        "周六也不休息，卷王就是你 👑",
    ],
    6: [
        "周日了还开工? 明天又是周一啊 😱",
        "难得周日，轻松点搞 🛋️",
    ],
}

# ---------------------------------------------------------------------------
# Holiday / special-date pool  (month, day) -> list of greetings
# ---------------------------------------------------------------------------

_HOLIDAYS: dict[tuple[int, int], list[str]] = {
    (1, 1): ["新年快乐! 新的一年继续搞事 🎆"],
    (2, 14): ["情人节快乐~ 不过你选择了和我一起加班 💔"],
    (3, 8): ["女神节/妇女节快乐 🌹"],
    (4, 1): ["愚人节快乐，今天说的话别太当真 🤡"],
    (5, 1): ["劳动节快乐! ...等等你在劳动? 🛠️"],
    (5, 4): ["五四青年节，年轻人就是要奋斗 ✊"],
    (6, 1): ["儿童节快乐，谁还不是个宝宝呢 🍭"],
    (10, 1): ["国庆快乐! 祖国生日也在加班 🇨🇳"],
    (10, 31): ["万圣节快乐，别被 bug 吓到 🎃"],
    (12, 24): ["平安夜快乐 🎄"],
    (12, 25): ["圣诞快乐! Merry Christmas 🎅"],
}

# ---------------------------------------------------------------------------
# Absence quips
# ---------------------------------------------------------------------------


def _absence_quip(last_seen: datetime | None, now: datetime) -> str | None:
    """Return a playful remark about how long the bot has been idle."""
    if last_seen is None:
        return None
    delta = now - last_seen
    if delta < timedelta(minutes=5):
        return None  # just restarted, skip
    if delta < timedelta(hours=1):
        mins = max(int(delta.total_seconds() / 60), 1)
        return f"才走了 {mins} 分钟就想我了? 🤭"
    if delta < timedelta(hours=24):
        hours = int(delta.total_seconds() / 3600)
        return f"离开了 {hours} 小时，还以为你把我忘了 😢"
    days = delta.days
    if days == 1:
        return "一天没见，有点想你 🥺"
    if days < 7:
        return f"消失了 {days} 天，我还以为被裁了 😭"
    if days < 30:
        return f"整整 {days} 天没理我，我都长蜘蛛网了 🕸️"
    return f"老板你丢下我 {days} 天了，我差点以为自己被删了 💀"


# ---------------------------------------------------------------------------
# Lockfile mtime helper
# ---------------------------------------------------------------------------


def _lockfile_mtime(config_path: Path | None) -> datetime | None:
    """Try to read the lockfile mtime as a proxy for last startup time."""
    if config_path is None:
        return None
    lock_path = config_path.expanduser().resolve().with_suffix(".lock")
    try:
        stat = lock_path.stat()
        return datetime.fromtimestamp(stat.st_mtime)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_greeting(
    *,
    now: datetime | None = None,
    config_path: Path | None = None,
) -> str:
    """Build a random, context-aware startup greeting.

    Parameters
    ----------
    now:
        Override the current time (useful for testing).
    config_path:
        Path to the yee88 config file; used to find the lockfile and
        compute how long the bot has been idle.
    """
    if now is None:
        now = datetime.now()

    # 1. Pick a time-of-day greeting.
    hour = now.hour
    if 6 <= hour < 12:
        pool = _MORNING
    elif 12 <= hour < 18:
        pool = _AFTERNOON
    elif 18 <= hour < 23:
        pool = _EVENING
    else:
        pool = _LATE_NIGHT
    greeting = random.choice(pool)

    # 2. Maybe add a weekday or holiday extra.
    extra: str | None = None
    key = (now.month, now.day)
    if key in _HOLIDAYS:
        extra = random.choice(_HOLIDAYS[key])
    elif now.weekday() in _WEEKDAY_EXTRAS:
        extra = random.choice(_WEEKDAY_EXTRAS[now.weekday()])

    # 3. Maybe add an absence quip.
    last_seen = _lockfile_mtime(config_path)
    quip = _absence_quip(last_seen, now)

    # Assemble.
    parts = [greeting]
    if extra:
        parts.append(extra)
    if quip:
        parts.append(quip)
    return "\n".join(parts)