from collections.abc import Callable

import pytest

from yee88.telegram.bridge import TelegramBridgeConfig
from yee88.runners.mock import ScriptRunner
from tests.telegram_fakes import FakeBot, FakeTransport, make_cfg as build_cfg


@pytest.fixture
def fake_transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def make_cfg() -> Callable[..., TelegramBridgeConfig]:
    def _factory(
        transport: FakeTransport, runner: ScriptRunner | None = None
    ) -> TelegramBridgeConfig:
        return build_cfg(transport, runner)

    return _factory
