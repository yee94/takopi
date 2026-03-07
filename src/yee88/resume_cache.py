"""In-memory LRU cache mapping (chat_id, message_id) → ResumeToken.

When the bot sends a final message, the resume token is stored here keyed
by the message reference.  When a user replies to that message, the token
can be looked up by ``reply_to_message_id`` instead of parsing it from the
message text.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from .model import ResumeToken


@dataclass(frozen=True, slots=True)
class _Key:
    chat_id: int | str
    message_id: int | str


class ResumeTokenCache:
    """LRU cache for message_id → ResumeToken mapping."""

    def __init__(self, max_size: int = 10000) -> None:
        self._cache: OrderedDict[_Key, ResumeToken] = OrderedDict()
        self._max_size = max_size

    def set(
        self, chat_id: int | str, message_id: int | str, token: ResumeToken
    ) -> None:
        key = _Key(chat_id, message_id)
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = token
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def get(self, chat_id: int | str, message_id: int | str) -> ResumeToken | None:
        key = _Key(chat_id, message_id)
        token = self._cache.get(key)
        if token is not None:
            self._cache.move_to_end(key)
        return token

    def __len__(self) -> int:
        return len(self._cache)
