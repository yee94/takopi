from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

from .backends import EngineBackend, EngineConfig
from .config import ConfigError

_BACKENDS: dict[str, EngineBackend] | None = None


def _discover_backends() -> dict[str, EngineBackend]:
    import takopi.runners as runners_pkg

    backends: dict[str, EngineBackend] = {}
    prefix = runners_pkg.__name__ + "."

    for module_info in pkgutil.iter_modules(runners_pkg.__path__, prefix):
        module_name = module_info.name
        mod = importlib.import_module(module_name)

        backend = getattr(mod, "BACKEND", None)
        if backend is None:
            continue
        if not isinstance(backend, EngineBackend):
            raise RuntimeError(f"{module_name}.BACKEND is not an EngineBackend")
        if backend.id in backends:
            raise RuntimeError(f"Duplicate backend id: {backend.id}")
        backends[backend.id] = backend

    return backends


def _ensure_loaded() -> None:
    global _BACKENDS
    if _BACKENDS is None:
        _BACKENDS = _discover_backends()


def get_backend(engine_id: str) -> EngineBackend:
    _ensure_loaded()
    assert _BACKENDS is not None
    try:
        return _BACKENDS[engine_id]
    except KeyError as exc:
        available = ", ".join(sorted(_BACKENDS))
        raise ConfigError(
            f"Unknown engine {engine_id!r}. Available: {available}."
        ) from exc


def list_backends() -> list[EngineBackend]:
    _ensure_loaded()
    assert _BACKENDS is not None
    return [_BACKENDS[key] for key in sorted(_BACKENDS)]


def list_backend_ids() -> list[str]:
    _ensure_loaded()
    assert _BACKENDS is not None
    return sorted(_BACKENDS)


def get_engine_config(
    config: dict[str, Any], engine_id: str, config_path: Path
) -> EngineConfig:
    engine_cfg = config.get(engine_id) or {}
    if not isinstance(engine_cfg, dict):
        raise ConfigError(
            f"Invalid `{engine_id}` config in {config_path}; expected a table."
        )
    return engine_cfg
