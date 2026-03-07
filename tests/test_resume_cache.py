"""Tests for ResumeTokenCache."""

from yee88.model import ResumeToken
from yee88.resume_cache import ResumeTokenCache


def _token(engine: str = "opencode", value: str = "ses_abc") -> ResumeToken:
    return ResumeToken(engine=engine, value=value)


def test_set_and_get() -> None:
    cache = ResumeTokenCache()
    token = _token()
    cache.set(123, 100, token)
    assert cache.get(123, 100) is token


def test_get_missing_returns_none() -> None:
    cache = ResumeTokenCache()
    assert cache.get(123, 999) is None


def test_different_chat_ids_are_independent() -> None:
    cache = ResumeTokenCache()
    t1 = _token(value="ses_1")
    t2 = _token(value="ses_2")
    cache.set(111, 100, t1)
    cache.set(222, 100, t2)
    assert cache.get(111, 100) is t1
    assert cache.get(222, 100) is t2


def test_overwrite_existing_key() -> None:
    cache = ResumeTokenCache()
    t1 = _token(value="ses_old")
    t2 = _token(value="ses_new")
    cache.set(123, 100, t1)
    cache.set(123, 100, t2)
    assert cache.get(123, 100) is t2
    assert len(cache) == 1


def test_lru_eviction() -> None:
    cache = ResumeTokenCache(max_size=3)
    for i in range(4):
        cache.set(1, i, _token(value=f"ses_{i}"))
    # First entry should be evicted
    assert cache.get(1, 0) is None
    assert cache.get(1, 1) is not None
    assert cache.get(1, 2) is not None
    assert cache.get(1, 3) is not None
    assert len(cache) == 3


def test_lru_access_refreshes_entry() -> None:
    cache = ResumeTokenCache(max_size=3)
    cache.set(1, 10, _token(value="ses_10"))
    cache.set(1, 20, _token(value="ses_20"))
    cache.set(1, 30, _token(value="ses_30"))
    # Access entry 10 to refresh it
    cache.get(1, 10)
    # Add new entry – should evict 20 (oldest untouched), not 10
    cache.set(1, 40, _token(value="ses_40"))
    assert cache.get(1, 10) is not None  # refreshed, still present
    assert cache.get(1, 20) is None  # evicted
    assert cache.get(1, 30) is not None
    assert cache.get(1, 40) is not None


def test_str_keys() -> None:
    """Cache supports str keys (matching transport ChannelId/MessageId types)."""
    cache = ResumeTokenCache()
    token = _token()
    cache.set("chat_123", "msg_456", token)
    assert cache.get("chat_123", "msg_456") is token
    assert cache.get(123, 456) is None  # different key type


def test_len() -> None:
    cache = ResumeTokenCache()
    assert len(cache) == 0
    cache.set(1, 1, _token(value="a"))
    assert len(cache) == 1
    cache.set(1, 2, _token(value="b"))
    assert len(cache) == 2
    # Overwrite doesn't increase length
    cache.set(1, 1, _token(value="c"))
    assert len(cache) == 2
