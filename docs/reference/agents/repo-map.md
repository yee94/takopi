# Repo map

Quick pointers for navigating the Takopi codebase.

## Where things start

- CLI entry point: `src/yee88/cli.py`
- Telegram backend entry point: `src/yee88/telegram/backend.py`
- Telegram bridge loop: `src/yee88/telegram/bridge.py`
- Transport-agnostic handler: `src/yee88/runner_bridge.py`

## Core concepts

- Domain types (resume tokens, events, actions): `src/yee88/model.py`
- Runner protocol: `src/yee88/runner.py`
- Router selection and resume polling: `src/yee88/router.py`
- Per-thread scheduling: `src/yee88/scheduler.py`
- Progress reduction and rendering: `src/yee88/progress.py`, `src/yee88/markdown.py`

## Engines and streaming

- Runner implementations: `src/yee88/runners/*`
- JSONL decoding schemas: `src/yee88/schemas/*`

## Plugins

- Public API boundary (`yee88.api`): `src/yee88/api.py`
- Entrypoint discovery + lazy loading: `src/yee88/plugins.py`
- Engine/transport/command backend loading: `src/yee88/engines.py`, `src/yee88/transports.py`, `src/yee88/commands.py`

## Configuration

- Settings model + TOML/env loading: `src/yee88/settings.py`
- Config migrations: `src/yee88/config_migrations.py`

## Docs and contracts

- Normative behavior: [Specification](../specification.md)
- Runner invariants: `tests/test_runner_contract.py`

