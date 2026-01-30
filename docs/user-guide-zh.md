# 🐙 yee88 完整使用指南

yee88 是一个 Telegram 桥接工具，让你可以通过 Telegram 聊天界面来运行 AI 编程助手（Codex、Claude Code、OpenCode、Pi）。

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## 📦 一、安装与初始化（💻 电脑侧）

### 1. 安装依赖

```bash
# 安装 uv（Python 包管理器）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 Python 3.14
uv python install 3.14

# 安装 yee88
uv tool install -U yee88
```

### 2. 安装 AI 引擎（至少一个）

```bash
# Codex (OpenAI)
npm install -g @openai/codex

# Claude Code (Anthropic)
npm install -g @anthropic-ai/claude-code

# OpenCode
npm install -g opencode-ai@latest

# Pi
npm install -g @mariozechner/pi-coding-agent
```

### 3. 首次运行配置（📱 手机侧配合）

```bash
yee88
```

这会启动交互式向导：

1. **创建 Telegram Bot** → 去 @BotFather 创建机器人，获取 token
2. **选择工作流**：
   - `assistant` - 持续对话模式（推荐个人使用）
   - `workspace` - 话题模式（团队多项目）
   - `handoff` - 回复继续模式
3. **连接聊天** → 在 Telegram 向机器人发送 `/start`
4. **选择默认引擎** → codex / claude / opencode / pi

配置保存在 `~/.yee88/yee88.toml`

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## 🚀 二、日常使用

### 启动 yee88（💻 电脑侧）

```bash
# 在项目目录启动
cd ~/your-project
yee88

# 指定引擎启动
yee88 claude
yee88 codex
```

### 基本对话（📱 手机侧 Telegram）

直接发送消息给机器人：

```
解释这个项目是做什么的
```

### 切换引擎（📱 手机侧）

在消息前加引擎前缀：

```
/codex 修复这个 bug
/claude 重构这个函数
/opencode 优化性能
/pi 添加测试
```

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## 📁 三、项目管理

### 注册项目（💻 电脑侧）

```bash
cd ~/dev/my-project
yee88 init myproject
```

### 从任意位置定位项目（📱 手机侧）

```
/myproject 添加新功能
/myproject @feat/new-ui 创建登录页面
```

### 设置默认项目（💻 电脑侧）

```bash
yee88 config set default_project myproject
```

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## 🌳 四、工作树（Worktrees）

### 在特定分支上运行（📱 手机侧）

```
/myproject @feat/auth 实现 JWT 认证
```

yee88 会自动：

- 创建 `.worktrees/feat/auth` 工作树
- 在该分支上下文中运行 AI

### 配置工作树（💻 电脑侧）

```bash
yee88 config set projects.myproject.worktrees_dir ".worktrees"
yee88 config set projects.myproject.worktree_base "main"
```

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## 💬 五、Telegram 命令（📱 手机侧）

| 命令 | 说明 |
|------|------|
| `/cancel` | 回复进度消息以取消当前运行 |
| `/agent` | 查看/设置当前聊天的默认引擎 |
| `/agent set claude` | 设置默认引擎为 Claude |
| `/model` | 查看/设置模型覆盖 |
| `/reasoning` | 查看/设置推理模式 |
| `/trigger` | 设置触发模式（mentions-only / all） |
| `/file put <path>` | 上传文件到仓库 |
| `/file get <path>` | 获取文件/目录（自动压缩） |
| `/topic <project> @branch` | 创建/绑定话题（需开启 topics） |
| `/ctx` | 显示当前上下文绑定 |
| `/ctx set <project> @branch` | 更新上下文 |
| `/ctx clear` | 清除上下文绑定 |
| `/new` | 清除当前会话，开始新对话 |

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## 📎 六、文件传输

### 启用文件传输（💻 电脑侧）

```bash
yee88 config set transports.telegram.files.enabled true
yee88 config set transports.telegram.files.auto_put true
```

### 上传文件（📱 手机侧）

发送文档并附带说明：

```
/file put docs/spec.pdf
```

或直接发送文件（自动保存到 `incoming/`）

### 下载文件（📱 手机侧）

```
/file get src/main.py
/file get src/          # 目录会自动打包为 zip
```

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## 🎙 七、语音消息

### 启用语音转录（💻 电脑侧）

```bash
yee88 config set transports.telegram.voice_transcription true
```

设置环境变量 `OPENAI_API_KEY`

### 使用（📱 手机侧）

直接发送语音消息，yee88 会自动转录并执行

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## ⚙️ 八、配置管理（💻 电脑侧）

### 查看配置

```bash
yee88 config list
yee88 config get default_engine
```

### 修改配置

```bash
# 设置默认值
yee88 config set default_engine "claude"
yee88 config set default_project "myproject"

# Telegram 设置
yee88 config set transports.telegram.session_mode "chat"
yee88 config set transports.telegram.show_resume_line false

# 引擎特定配置
yee88 config set claude.model "claude-sonnet-4-5-20250929"
yee88 config set codex.profile "work"

# 启用配置热重载
yee88 config set watch_config true
```

### 诊断检查

```bash
yee88 doctor
```

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## 🗂 九、话题模式（Topics）

适合团队协作，每个话题绑定一个项目/分支：

### 启用（💻 电脑侧）

```bash
yee88 config set transports.telegram.topics.enabled true
```

### 创建话题（📱 手机侧）

在论坛群组中：

```
/topic myproject @main 设置主分支
/topic myproject @feat/ui 前端开发
```

每个话题会自动记住绑定的项目和分支，无需重复输入。

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## 🔧 十、完整配置参考

### 配置文件位置

- **默认**: `~/.yee88/yee88.toml`
- **锁文件**: `~/.yee88/yee88.lock`

### 顶层配置

| 配置项 | 类型 | 默认值 | 中文说明 |
|--------|------|--------|----------|
| `watch_config` | bool | `false` | 热重载配置更改（传输层除外） |
| `default_engine` | string | `"codex"` | 新线程的默认引擎 ID |
| `default_project` | string\|null | `null` | 默认项目别名 |
| `transport` | string | `"telegram"` | 传输后端 ID |
| `system_prompt` | string | (内置) | 系统提示词 |

### Telegram 传输配置 (`transports.telegram`)

#### 基础配置

| 配置项 | 类型 | 默认值 | 中文说明 |
|--------|------|--------|----------|
| `bot_token` | string | (必需) | Telegram Bot Token（从 @BotFather 获取） |
| `chat_id` | int | (必需) | 默认聊天 ID |
| `allowed_user_ids` | int[] | `[]` | 允许的用户 ID 列表（空列表表示不限制） |
| `message_overflow` | string | `"trim"` | 长消息处理方式：`"trim"`(截断) 或 `"split"`(分割) |
| `session_mode` | string | `"stateless"` | 会话模式：`"stateless"`(回复继续) 或 `"chat"`(自动恢复) |
| `show_resume_line` | bool | `true` | 在消息页脚显示恢复行 |
| `forward_coalesce_s` | float | `1.0` | 转发消息合并的静默窗口（秒），设为 `0` 禁用 |

#### 语音转录配置

| 配置项 | 类型 | 默认值 | 中文说明 |
|--------|------|--------|----------|
| `voice_transcription` | bool | `false` | 启用语音笔记转录 |
| `voice_max_bytes` | int | `10485760` | 最大语音文件大小（字节，默认 10MB） |
| `voice_transcription_model` | string | `"gpt-4o-mini-transcribe"` | 转录模型名称 |
| `voice_transcription_base_url` | string\|null | `null` | 转录 API 基础 URL（可选） |
| `voice_transcription_api_key` | string\|null | `null` | 转录 API 密钥（可选） |

#### 话题配置 (`transports.telegram.topics`)

| 配置项 | 类型 | 默认值 | 中文说明 |
|--------|------|--------|----------|
| `enabled` | bool | `false` | 启用论坛话题功能 |
| `scope` | string | `"auto"` | 话题管理范围：`"auto"`、`"main"`、`"projects"`、`"all"` |

#### 文件传输配置 (`transports.telegram.files`)

| 配置项 | 类型 | 默认值 | 中文说明 |
|--------|------|--------|----------|
| `enabled` | bool | `false` | 启用 `/file put` 和 `/file get` 命令 |
| `auto_put` | bool | `true` | 自动保存上传的文件 |
| `auto_put_mode` | string | `"upload"` | 上传后行为：`"upload"`(仅保存) 或 `"prompt"`(保存并启动运行) |
| `uploads_dir` | string | `"incoming"` | 上传目录（相对于仓库/worktree） |
| `allowed_user_ids` | int[] | `[]` | 允许文件传输的用户 ID（空列表允许私聊，群组需要管理员） |
| `deny_globs` | string[] | (见下) | 拒绝的文件模式列表 |

默认 `deny_globs`:
```toml
deny_globs = [
    ".git/**",
    ".env",
    ".envrc",
    "**/*.pem",
    "**/.ssh/**"
]
```

**文件大小限制**（不可配置）：
- 上传：20 MiB
- 下载：50 MiB

### 项目配置 (`projects.<alias>`)

| 配置项 | 类型 | 默认值 | 中文说明 |
|--------|------|--------|----------|
| `path` | string | (必需) | 仓库根目录路径（支持 `~` 展开） |
| `worktrees_dir` | string | `".worktrees"` | Worktree 根目录（相对于 `path`） |
| `default_engine` | string\|null | `null` | 项目默认引擎 |
| `worktree_base` | string\|null | `null` | 新 worktree 的基础分支 |
| `chat_id` | int\|null | `null` | 绑定到此项目的 Telegram 聊天 ID |
| `system_prompt` | string\|null | `null` | 项目特定的系统提示词 |

### 插件配置 (`plugins`)

| 配置项 | 类型 | 默认值 | 中文说明 |
|--------|------|--------|----------|
| `enabled` | string[] | `[]` | 启用的插件列表（空列表表示加载所有已安装插件） |

### 引擎特定配置

#### Codex 配置 (`[codex]`)

| 配置项 | 类型 | 默认值 | 中文说明 |
|--------|------|--------|----------|
| `extra_args` | string[] | `["-c", "notify=[]"]` | 额外的 CLI 参数（不支持 exec-only 标志） |
| `profile` | string | (未设置) | 配置文件名称，作为 `--profile` 传递并用于会话标题 |

#### Claude 配置 (`[claude]`)

| 配置项 | 类型 | 默认值 | 中文说明 |
|--------|------|--------|----------|
| `model` | string | (未设置) | 可选的模型覆盖 |
| `allowed_tools` | string[] | `["Bash", "Read", "Edit", "Write"]` | 自动批准的工具列表 |
| `dangerously_skip_permissions` | bool | `false` | 跳过 Claude 权限提示（**高风险**） |
| `use_api_billing` | bool | `false` | 使用 API 计费（默认使用订阅） |

#### Pi 配置 (`[pi]`)

| 配置项 | 类型 | 默认值 | 中文说明 |
|--------|------|--------|----------|
| `model` | string | (未设置) | 传递给 `--model` |
| `provider` | string | (未设置) | 传递给 `--provider` |
| `extra_args` | string[] | `[]` | 额外的 CLI 参数 |

#### OpenCode 配置 (`[opencode]`)

| 配置项 | 类型 | 默认值 | 中文说明 |
|--------|------|--------|----------|
| `model` | string | (未设置) | 可选的模型覆盖 |


⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## 📋 十一、三种工作流的完整配置示例

### Assistant 工作流（持续聊天）

```toml
default_engine = "codex"
transport = "telegram"

[transports.telegram]
bot_token = "YOUR_BOT_TOKEN"
chat_id = 123456789
session_mode = "chat"           # 自动恢复
show_resume_line = false        # 隐藏恢复行

[transports.telegram.topics]
enabled = false
scope = "auto"
```

### Workspace 工作流（话题分支）

```toml
default_engine = "codex"
transport = "telegram"

[transports.telegram]
bot_token = "YOUR_BOT_TOKEN"
chat_id = -1001234567890        # 论坛群组
session_mode = "chat"
show_resume_line = false

[transports.telegram.topics]
enabled = true                  # 启用话题
scope = "auto"

[projects.my-project]
path = "~/dev/my-project"
chat_id = -1001234567890
```

### Handoff 工作流（回复继续）

```toml
default_engine = "codex"
transport = "telegram"

[transports.telegram]
bot_token = "YOUR_BOT_TOKEN"
chat_id = 123456789
session_mode = "stateless"      # 回复继续
show_resume_line = true         # 始终显示恢复行
```

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

## 📝 十二、使用技巧

### 1. 快速切换上下文

```
/ctx set myproject @feat/new-feature
```

之后的所有消息都会在这个项目和分支上下文中执行。

### 2. 使用定时消息

在 Telegram 中安排消息，yee88 会在指定时间执行。

### 3. 查看进度

运行过程中会显示实时进度消息，包含：
- 正在执行的命令
- 工具调用
- 文件变更
- 已用时间

### 4. 恢复会话

每个完成的运行都会在消息底部显示恢复命令：

```
codex resume <token>
```

复制到终端即可继续会话。

### 5. 多引擎协作

```
/codex 实现基础功能
/claude 优化代码结构
/opencode 添加测试
```
