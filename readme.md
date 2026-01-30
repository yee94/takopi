# yee88

telegram bridge for codex, claude code, opencode, pi.

## quickstart

```sh
# install
uv tool install -U yee88

# first run - follow the setup wizard
yee88

# in any git repo - create a topic and start
cd ~/your-project
yee88 topic init
yee88
```

## features

- projects and worktrees: work on multiple repos/branches simultaneously, branches are git worktrees
- stateless resume: continue in chat or copy the resume line to pick up in terminal
- progress streaming: commands, tools, file changes, elapsed time
- parallel runs across agent sessions, per-agent-session queue
- works with telegram features like voice notes and scheduled messages
- file transfer: send files to the repo or fetch files/dirs back
- group chats and topics: map group topics to repo/branch contexts
- works with existing anthropic and openai subscriptions

## requirements

`uv` for installation (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

python 3.14+ (`uv python install 3.14`)

at least one engine on PATH: `codex`, `claude`, `opencode`, or `pi`

## usage

```sh
cd ~/dev/happy-gadgets
yee88
```

send a message to your bot. prefix with `/codex`, `/claude`, `/opencode`, or `/pi` to pick an engine. reply to continue a thread.

register a project with `yee88 init happy-gadgets`, then target it from anywhere with `/happy-gadgets hard reset the timeline`.

mention a branch to run an agent in a dedicated worktree `/happy-gadgets @feat/memory-box freeze artifacts forever`.

inspect or update settings with `yee88 config list`, `yee88 config get`, and `yee88 config set`.

## plugins

takopi supports entrypoint-based plugins for engines, transports, and commands.

see [`docs/how-to/write-a-plugin.md`](docs/how-to/write-a-plugin.md) and [`docs/reference/plugin-api.md`](docs/reference/plugin-api.md).

## development

see [`docs/reference/specification.md`](docs/reference/specification.md) and [`docs/developing.md`](docs/developing.md).

