# yee88

Telegram 桥接工具，连接 Codex、Claude Code、OpenCode、Pi 等 AI 编程引擎。

## 快速开始

```sh
# 安装
uv tool install -U yee88

# 首次运行 - 跟随设置向导完成配置
yee88

# 安装 yee88 skill（为 AI 引擎提供 yee88 CLI 能力）
npx skills add yee94/yee88

# 在任意 git 仓库中 - 创建话题并启动
cd ~/your-project
yee88 topic init
yee88
```

## 功能特性

- **项目与工作树**：同时在多个仓库/分支上工作，分支基于 git worktree
- **无状态恢复**：在聊天中继续对话，或复制恢复命令在终端中接续
- **进度流式输出**：实时显示命令、工具调用、文件变更、耗时
- **并行运行**：跨 agent 会话并行执行，每个会话独立队列
- **Telegram 特性**：支持语音消息、定时消息等 Telegram 原生功能
- **文件传输**：向仓库发送文件，或从仓库获取文件/目录
- **发送文件/图片**：通过 `yee88 send-file` 命令发送文件到 Telegram（自动识别图片类型）
- **群组与话题**：将群组话题映射到仓库/分支上下文
- **定时任务**：通过 `yee88 cron` 管理定时提醒和自动化任务
- **兼容现有订阅**：支持 Anthropic 和 OpenAI 现有订阅

## 环境要求

- `uv` 包管理器（`curl -LsSf https://astral.sh/uv/install.sh | sh`）
- Python 3.14+（`uv python install 3.14`）
- 至少一个引擎在 PATH 中：`codex`、`claude`、`opencode` 或 `pi`
- Node.js（用于安装 skill：`npx skills add yee94/yee88`）

## 使用方法

```sh
cd ~/dev/happy-gadgets
yee88
```

向你的 bot 发送消息。使用 `/codex`、`/claude`、`/opencode` 或 `/pi` 前缀选择引擎。回复消息可继续对话。

### 项目管理

```sh
# 注册项目
yee88 init happy-gadgets

# 从任意位置向项目发送指令
/happy-gadgets 重构用户认证模块

# 指定分支，在独立工作树中运行
/happy-gadgets @feat/memory-box 冻结所有构件
```

### 配置管理

```sh
yee88 config list          # 列出所有配置
yee88 config get <key>     # 获取配置项
yee88 config set <key> <value>  # 设置配置项
```

### 定时任务

```sh
yee88 cron add reminder "+30m" "该休息了" -o    # 30分钟后一次性提醒
yee88 cron add standup "0 9 * * 1-5" "站会时间"  # 工作日每天9点
yee88 cron list                                   # 查看所有任务
yee88 cron remove <id> --force                    # 删除任务
```

### 发送文件

```sh
yee88 send-file /path/to/image.png                # 发送图片（聊天中直接显示）
yee88 send-file /path/to/report.pdf --caption "日报"  # 发送文件附件
```

### Skill 安装

yee88 提供 AI 引擎 skill，让 OpenCode、Claude Code 等引擎能够直接调用 yee88 CLI 命令（如定时提醒、发送文件等）。

```sh
# 通过 npx 安装（推荐）
npx skills add yee94/yee88

# 或在首次运行时通过 --onboard 向导安装
yee88 --onboard
```

## 插件

yee88 支持基于 entrypoint 的插件系统，可扩展引擎、传输层和命令。

详见 [`docs/how-to/write-a-plugin.md`](docs/how-to/write-a-plugin.md) 和 [`docs/reference/plugin-api.md`](docs/reference/plugin-api.md)。

## 开发

详见 [`docs/reference/specification.md`](docs/reference/specification.md) 和 [`docs/developing.md`](docs/developing.md)。