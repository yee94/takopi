from typing import cast

import click
import typer

from takopi import cli, engines


def test_engine_discovery_skips_non_backend() -> None:
    ids = engines.list_backend_ids()
    assert "codex" in ids
    assert "claude" in ids
    assert "mock" not in ids


def test_cli_registers_engine_commands_sorted() -> None:
    command_names = [cmd.name for cmd in cli.app.registered_commands]
    engine_ids = engines.list_backend_ids()
    assert set(engine_ids) <= set(command_names)
    engine_commands = [name for name in command_names if name in engine_ids]
    assert engine_commands == engine_ids


def test_engine_commands_do_not_expose_engine_id_option() -> None:
    group = cast(click.Group, typer.main.get_command(cli.app))
    engine_ids = engines.list_backend_ids()

    ctx = group.make_context("takopi", [])

    for engine_id in engine_ids:
        command = group.get_command(ctx, engine_id)
        assert command is not None
        options: set[str] = set()
        for param in command.params:
            options.update(getattr(param, "opts", []))
            options.update(getattr(param, "secondary_opts", []))
        assert "--final-notify" in options
        assert "--debug" in options
        assert not any(opt.lstrip("-") == "engine-id" for opt in options)
