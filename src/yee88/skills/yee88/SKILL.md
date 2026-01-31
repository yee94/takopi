---
name: yee88
description: 当用户说"提醒我"、"X分钟/小时后"、"定时"、"每天/每周"、"设置闹钟"、"注册项目"、"切换引擎"、"创建话题"时使用。yee88 Telegram 桥接工具，支持一次性提醒(+30m, +2h)、定时任务(cron)、项目管理、话题管理、多引擎切换。通过 yee88 CLI 命令直接操作。
---

# yee88 CLI 工具

## ⚠️ 重要：必须执行真实命令

当用户请求以下功能时，**必须使用 Bash 执行对应的 yee88 命令**，不能只是口头回复！

## 💬 回复用户时保持简洁

**不要透露内部实现细节！** 用户不需要知道：
- "一次性任务"、"执行后自动清理"等技术细节
- 命令参数含义（如 `-o`、`--project`）
- 内部调度机制

| 用户说 | 正确回复 ✅ | 错误回复 ❌ |
|--------|-------------|-------------|
| "1分钟后提醒我喝水" | "好的，1分钟后提醒你喝水" | "已创建一次性定时任务，将在1分钟后触发，执行后自动清理..." |
| "每天9点提醒我站会" | "好的，每天早上9点提醒你站会" | "已添加 cron 任务，schedule 为 0 9 * * *，project 为..." |
| "取消那个提醒" | "已取消" | "已执行 yee88 cron remove xxx --force，任务已从列表中删除..." |

## 🚨 关键区分：设置提醒 vs 执行任务

**设置提醒时，你只需要创建定时任务，不要执行任务本身！**

| 场景 | 正确做法 | 错误做法 |
|------|----------|----------|
| "1分钟后提醒我查天气" | 只执行 `yee88 cron add ...` 创建提醒 | ❌ 立即查天气，把结果写进 message |
| "30分钟后提醒我开会" | 只执行 `yee88 cron add ...` 创建提醒 | ❌ 立即做任何与"开会"相关的操作 |
| "2小时后帮我发邮件" | 只执行 `yee88 cron add ...` 创建提醒 | ❌ 立即发邮件 |

**message 参数应该是用户的原话或简短描述，不是执行结果！**

## ⛔ 默认不传 --project！除非用户明确要求

**简单规则：不知道项目别名就不传 `--project`，让 yee88 使用默认上下文。**

| 场景 | 做法 |
|------|------|
| 用户只说"1分钟后提醒我..." | `yee88 cron add reminder "+1m" "..." -o` （不传 --project） |
| 用户说"在 takopi 项目提醒我..." | `yee88 cron add reminder "+1m" "..." --project takopi -o` |
| 不确定项目别名 | **不传 --project** |

**⚠️ --project 只接受项目别名，不是路径！**

| 正确 ✅ | 错误 ❌ |
|---------|---------|
| 不传（默认） | `--project /Users/yee.wang/Code/github/takopi` |
| `--project takopi` | `--project ~/dev/work-project` |
| `--project work` | `--project /Users/yee.wang/.yee88` |
|  | `--project .` |

**如何获取项目别名（仅当用户要求时）：**
```bash
yee88 config list | grep projects
```

## 🎯 快速触发表（立即执行）

| 用户说 | 必须执行的命令 |
|--------|----------------|
| "5分钟后提醒我..." | `yee88 cron add reminder "+5m" "提醒内容" -o` |
| "30分钟后提醒我..." | `yee88 cron add reminder "+30m" "提醒内容" -o` |
| "2小时后提醒我..." | `yee88 cron add reminder "+2h" "提醒内容" -o` |
| "明天提醒我..." | `yee88 cron add reminder "+1d" "提醒内容" -o` |
| "每天早上9点提醒我..." | `yee88 cron add daily "0 9 * * *" "提醒内容"` |
| "每周一提醒我..." | `yee88 cron add weekly "0 9 * * 1" "提醒内容"` |
| "查看所有提醒" | `yee88 cron list` |
| "删除提醒 X" | `yee88 cron remove X --force` |

### 一次性提醒命令格式

```bash
yee88 cron add <id> "<时间>" "<消息>" -o
```

**参数说明：**
- `<id>`: 任务ID（如 reminder, meeting, break）
- `<时间>`: 相对时间格式 `+5m`, `+30m`, `+1h`, `+2h`, `+1d`
- `<消息>`: **用户的原话或简短描述**（不是执行结果！）
- `--project <alias>`: 可选，项目别名（如 takopi, myproject），不指定则在默认上下文执行
- `-o`: 一次性任务（执行后自动删除）

**正确示例：**
```bash
# 用户说："5分钟后提醒我该健身了"
yee88 cron add reminder "+5m" "该健身了" -o

# 用户说："30分钟后提醒我开会"
yee88 cron add meeting "+30m" "开会时间到" -o

# 用户说："1分钟后提醒我查天气"
# ✅ 正确：只设置提醒，不查天气
yee88 cron add weather "+1m" "查天气" -o

# ❌ 错误：立即查天气并把结果写进 message
# yee88 cron add weather "+1m" "杭州今天晴，15度..." -o
```

---

## 完整能力参考

### 1. 定时任务 (Cron)

#### 注册项目
```bash
yee88 init <alias>
```

在指定目录注册项目：
```bash
cd ~/dev/my-project
yee88 init myproject
```

#### 查看项目配置
```bash
yee88 config list | grep projects
```

### 2. 配置管理

#### 查看配置路径
```bash
yee88 config path
```

#### 列出所有配置
```bash
yee88 config list
```

#### 获取配置项
```bash
yee88 config get <key>
```

示例：
```bash
yee88 config get default_engine
yee88 config get projects.myproject.path
```

#### 设置配置项
```bash
yee88 config set <key> <value>
```

示例：
```bash
# 设置默认引擎
yee88 config set default_engine "claude"

# 设置默认项目
yee88 config set default_project "myproject"

# 设置项目路径
yee88 config set projects.myproject.path "~/dev/my-project"

# 设置项目默认引擎
yee88 config set projects.myproject.default_engine "claude"

# Telegram 设置
yee88 config set transports.telegram.session_mode "chat"
yee88 config set transports.telegram.show_resume_line false

# 引擎特定配置
yee88 config set claude.model "claude-sonnet-4-5-20250929"
yee88 config set codex.profile "work"
```

#### 删除配置项
```bash
yee88 config unset <key>
```

### 3. 定时任务 (Cron)

#### 添加定时任务
```bash
yee88 cron add <id> <schedule> <message> [--project <alias>]
```

参数：
- `id`: 任务唯一标识
- `schedule`: Cron 表达式（如 "0 9 * * 1-5"）
- `message`: 推送消息内容
- `--project`: 可选，项目别名（如 takopi），不指定则在默认上下文执行

示例：
```bash
# 每日站会（工作日早上9点）
yee88 cron add standup "0 9 * * 1-5" "准备每日站会" --project work

# 周报（周五下午6点）
yee88 cron add weekly "0 18 * * 5" "生成本周工作报告" --project work

# 提醒（每30分钟）
yee88 cron add reminder "*/30 * * * *" "该休息眼睛了" --project personal
```

#### 列出所有定时任务
```bash
yee88 cron list
```

显示所有（包括禁用的）：
```bash
yee88 cron list --all
```

#### 启用/禁用任务
```bash
yee88 cron enable <id>
yee88 cron disable <id>
```

#### 删除任务
```bash
yee88 cron remove <id>
```

强制删除（不确认）：
```bash
yee88 cron remove <id> --force
```

#### 立即执行一次（测试）
```bash
yee88 cron run <id>
```

#### 添加一次性定时任务

使用 `--one-time` 或 `-o` 参数创建只执行一次的任务，执行后自动删除。

支持两种时间格式：
- **相对时间**: `+30m` (30分钟后), `+2h` (2小时后), `+1d` (1天后)
- **ISO 8601**: `2026-02-01T14:00:00` (具体日期时间)

```bash
# 30分钟后提醒
yee88 cron add reminder "+30m" "该开会了" --project work -o

# 2小时后部署
yee88 cron add deploy "+2h" "部署到生产环境" --project myapp -o

# 指定具体时间
yee88 cron add meeting "2026-02-01T14:00:00" "项目评审会议" --project work -o
```

查看任务列表时，一次性任务会标记为 `once` 类型：
```bash
yee88 cron list
# 输出: ID                   TYPE       SCHEDULE             STATUS     PROJECT
```

### 4. 话题管理

#### 初始化话题
```bash
yee88 topic init
```

在当前目录创建话题并绑定到项目。

#### 创建话题
```bash
yee88 topic create <project> [@branch]
```

示例：
```bash
yee88 topic create myproject
yee88 topic create myproject @feat/new-feature
```

#### 查看话题状态
```bash
yee88 topic status
```

#### 切换话题
```bash
yee88 topic switch <topic_id>
```

### 5. 引擎运行

#### 启动 yee88
```bash
yee88
```

#### 指定引擎启动
```bash
yee88 claude
yee88 codex
yee88 opencode
yee88 pi
```

#### 带选项启动
```bash
yee88 --debug
yee88 --onboard
yee88 --transport telegram
```

### 6. 诊断检查

#### 运行配置检查
```bash
yee88 doctor
```

检查配置是否正确，包括：
- Telegram bot token
- Chat ID
- 引擎可用性
- 项目配置

### 7. 插件管理

#### 列出插件
```bash
yee88 plugins
```

#### 验证插件
```bash
yee88 plugins --validate
```

### 8. 获取 Chat ID

```bash
yee88 chat-id
```

启动临时 bot 捕获 Telegram chat ID。

### 9. 查看引导路径

```bash
yee88 onboarding-paths
```

显示所有可能的配置路径。

## 配置参考

### 配置文件位置
- 主配置：`~/.yee88/yee88.toml`
- 定时任务：`~/.yee88/cron.toml`
- 话题状态：`~/.yee88/topics.json`

### 常用配置示例

```toml
# ~/.yee88/yee88.toml

watch_config = true
default_engine = "claude"
default_project = "myproject"
transport = "telegram"

[transports.telegram]
bot_token = "YOUR_BOT_TOKEN"
chat_id = 123456789
session_mode = "chat"
show_resume_line = false

[projects.myproject]
path = "~/dev/my-project"
default_engine = "claude"
```

## 使用场景

### 场景 1：每日工作流自动化

```bash
# 1. 注册项目
cd ~/dev/work-project
yee88 init work

# 2. 设置默认项目
yee88 config set default_project work

# 3. 添加定时任务（使用项目别名）
yee88 cron add morning "0 9 * * 1-5" "准备每日站会" --project work
yee88 cron add evening "0 18 * * 1-5" "总结今日工作" --project work
yee88 cron add weekly "0 17 * * 5" "生成本周报告" --project work

# 4. 启动 yee88
yee88
```

### 场景 2：多项目管理

```bash
# 注册多个项目
cd ~/dev/project-a && yee88 init project-a
cd ~/dev/project-b && yee88 init project-b

# 设置不同默认引擎
yee88 config set projects.project-a.default_engine "claude"
yee88 config set projects.project-b.default_engine "codex"

# 为每个项目创建话题
cd ~/dev/project-a
yee88 topic init

cd ~/dev/project-b
yee88 topic init
```

### 场景 3：团队协作

```bash
# 1. 配置群组 chat_id
yee88 config set transports.telegram.chat_id -1001234567890

# 2. 启用话题模式
yee88 config set transports.telegram.topics.enabled true

# 3. 创建团队话题
yee88 topic create team-project @main

# 4. 设置定时提醒（使用项目别名）
yee88 cron add daily-sync "0 10 * * 1-5" "团队同步时间" --project team-project
```

### 场景 4：临时提醒和一次性任务

```bash
# 30分钟后提醒自己休息
yee88 cron add break "+30m" "该休息眼睛了，起来活动一下" --project personal -o

# 今天下午3点的会议提醒
yee88 cron add meeting "2026-02-01T15:00:00" "参加产品评审会议" --project work -o

# 明天早上执行代码审查
yee88 cron add review "+1d" "审查昨天的 PR" --project work -o
```

## 故障排查

### 检查配置
```bash
yee88 doctor
```

### 查看日志
```bash
# yee88 日志
tail -f /tmp/yee88.log

# 定时任务日志
tail -f /tmp/yee88-cron.log
```

### 验证 cron 表达式
```bash
python -c "from croniter import croniter; print(croniter('0 9 * * *').get_next(str))"
```

### 测试任务
```bash
yee88 cron run <task-id>
```

## 注意事项

1. **项目别名要求**：
   - 定时任务的 `--project` 使用项目别名（如 `takopi`, `work`）
   - 通过 `yee88 config list | grep projects` 查看已注册项目
   - 使用 `yee88 init <alias>` 注册新项目

2. **配置热重载**：
   - 设置 `watch_config = true` 可热重载配置
   - 定时任务配置修改后需重启 yee88

3. **调度精度**：
   - 定时任务每分钟检查一次
   - 实际执行可能有 1 分钟内延迟

4. **权限问题**：
   - 确保 yee88 命令在 PATH 中
   - 定时任务执行时保持 yee88 运行

5. **一次性任务**：
   - 使用 `-o` 或 `--one-time` 参数创建
   - 支持相对时间 (`+30m`, `+2h`, `+1d`) 和 ISO 8601 格式
   - 执行后自动从列表中删除
   - 无法对一次性任务使用 enable/disable（执行前自动删除）

## 完整命令速查表

| 命令 | 说明 |
|------|------|
| `yee88` | 启动 yee88 |
| `yee88 init <alias>` | 注册项目 |
| `yee88 config path` | 查看配置路径 |
| `yee88 config list` | 列出配置 |
| `yee88 config get <key>` | 获取配置项 |
| `yee88 config set <key> <value>` | 设置配置项 |
| `yee88 config unset <key>` | 删除配置项 |
| `yee88 cron add <id> <schedule> <msg> [--project <alias>]` | 添加定时任务 |
| `yee88 cron add <id> <time> <msg> [-p <alias>] -o` | 添加一次性任务 (-o = --one-time) |
| `yee88 cron list` | 列出定时任务 |
| `yee88 cron enable <id>` | 启用任务 |
| `yee88 cron disable <id>` | 禁用任务 |
| `yee88 cron remove <id>` | 删除任务 |
| `yee88 cron run <id>` | 立即执行任务 |
| `yee88 topic init` | 初始化话题 |
| `yee88 topic create <project> [@branch]` | 创建话题 |
| `yee88 topic status` | 查看话题状态 |
| `yee88 doctor` | 运行诊断检查 |
| `yee88 plugins` | 列出插件 |
| `yee88 chat-id` | 获取 Chat ID |
| `yee88 claude` | 使用 Claude 引擎 |
| `yee88 codex` | 使用 Codex 引擎 |
| `yee88 opencode` | 使用 OpenCode 引擎 |
| `yee88 pi` | 使用 Pi 引擎 |
