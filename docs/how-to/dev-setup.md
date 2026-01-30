# Dev setup

Set up Takopi for local development and run the checks.

## Clone and run

```bash
git clone https://github.com/banteg/yee88
cd yee88

# Run directly with uv (installs deps automatically)
uv run yee88 --help
```

## Install locally (optional)

```bash
uv tool install .
yee88 --help
```

## Run checks

```bash
uv run pytest
uv run ruff check src tests
uv run ty check .

# Or all at once
just check
```

