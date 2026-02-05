# AGENTS.md - yee88 开发指南

## 项目概述

yee88 是一个 Telegram/Discord 桥接工具，用于连接多个 AI 编程助手（Codex、Claude Code、OpenCode、Pi）。它实现了标准化的 Runner 协议，支持状态恢复、多线程并行、定时任务和话题管理。

---

## 开发规范

### 提交前必须执行

```bash
just check
```

这会运行：
- `ruff format --check` - 代码格式化检查
- `ruff check` - Lint 检查
- `ty check` - 类型检查
- `pytest` - 测试套件（覆盖率要求 ≥81%）

**如果修复了任何问题，必须重新运行 `just check` 确认通过后再提交。**

### 提交规范

- 使用 [Conventional Commits](https://www.conventionalcommits.org/)
- 只提交你编辑的文件
- PR 必须包含 "Manual testing" 清单部分

---

## 架构概览

### 核心层级

```
CLI Layer          → cli.py (入口、配置、锁文件)
Plugin Layer       → plugins.py, engines.py, transports.py, api.py
Orchestration Layer → router.py, scheduler.py, config.py
Bridge Layer       → telegram/bridge.py, runner_bridge.py
Runner Layer       → runners/*.py, schemas/*.py
Transport Layer    → telegram/client.py, presenter.py
```

### 关键概念

- **Runner**: AI 引擎适配器，执行代理 CLI 并生成 TakopiEvent
- **ResumeToken**: 线程标识符 `{engine: str, value: str}`
- **ResumeLine**: 引擎原生的恢复命令（如 `claude --resume <id>`）
- **TakopiEvent**: 标准化事件（started, action, completed）
- **ThreadKey**: 线程唯一键 `f"{engine}:{value}"`

---

## 代码规范

### Python 版本

- **必须**使用 Python 3.14+
- 使用 `from __future__ import annotations`

### 导入顺序

```python
from __future__ import annotations

# 标准库
import sys
from pathlib import Path
from collections.abc import Callable

# 第三方库
import typer
from pydantic import BaseModel

# 项目内部
from ..model import ResumeToken
from ..runner import Runner
```

### 类型注解

- 所有函数参数和返回值必须标注类型
- 使用 `|` 替代 `Optional` 和 `Union`（Python 3.10+ 风格）
- 使用 `... | None` 表示可选

```python
# ✅ 正确
def run(prompt: str, resume: ResumeToken | None) -> AsyncIterator[TakopiEvent]: ...

# ❌ 错误
def run(prompt: str, resume: Optional[ResumeToken]) -> AsyncIterator[TakopiEvent]: ...
```

### 异步代码

- 使用 `anyio` 进行异步操作
- 异步函数使用 `async def`
- 异步迭代器使用 `AsyncIterator[T]`

```python
from collections.abc import AsyncIterator
import anyio

async def run(self, prompt: str, resume: ResumeToken | None) -> AsyncIterator[TakopiEvent]:
    async with await anyio.open_process(...) as process:
        ...
```

### 数据类

- 使用 `@dataclass(frozen=True, slots=True)` 定义不可变数据类
- 使用 `msgspec` 进行高性能序列化

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ResumeToken:
    engine: str
    value: str
```

### 错误处理

- 使用自定义异常类
- 避免裸 `except:`，使用 `except SpecificError:`

```python
class ConfigError(Exception):
    """配置错误"""
    pass

class LockError(Exception):
    """锁文件错误"""
    pass
```

### 日志记录

- 使用 `structlog` 进行结构化日志
- 在模块级别获取 logger

```python
import structlog

logger = structlog.get_logger(__name__)

# 使用
logger.info("message", key="value", count=42)
```

---

## 模块职责

### 核心模块

| 模块 | 职责 |
|------|------|
| `model.py` | 领域类型：ResumeToken, Action, TakopiEvent |
| `runner.py` | Runner 协议定义 |
| `router.py` | 引擎选择、Resume 解析 |
| `scheduler.py` | 每线程队列调度 |
| `progress.py` | 进度消息渲染 |
| `events.py` | 事件处理 |

### Runner 实现

每个 Runner 必须实现：

```python
class Runner(Protocol):
    engine: str
    
    async def run(
        self,
        prompt: str,
        resume: ResumeToken | None,
    ) -> AsyncIterator[TakopiEvent]: ...
    
    def format_resume(self, token: ResumeToken) -> str: ...
    def extract_resume(self, text: str) -> ResumeToken | None: ...
    def is_resume_line(self, line: str) -> bool: ...
```

### Schema 定义

- 使用 `msgspec.Struct` 定义 JSONL 解码结构
- 放在 `src/yee88/schemas/{engine}.py`

```python
import msgspec

class ClaudeEvent(msgspec.Struct):
    type: str
    content: str | None = None
```

---

## 测试规范

### 测试文件命名

- `test_{module}.py` - 对应模块的测试
- `test_{feature}.py` - 功能测试

### 测试覆盖率

- **最低覆盖率**: 81%
- 使用 `pytest-cov` 生成报告
- 变异测试使用 `mutmut`

### 运行测试

```bash
# 全部测试
pytest

# 带覆盖率
pytest --cov=yee88 --cov-branch --cov-report=term-missing

# 变异测试
just mutate
```

### 测试夹具

- 共享夹具放在 `tests/conftest.py`
- 使用 `pytest-anyio` 进行异步测试

---

## 文档规范

### 文档结构

文档使用 Diátaxis 框架组织：

```
docs/
├── tutorials/      # 教程（学习导向）
├── how-to/         # 操作指南（任务导向）
├── reference/      # 参考文档（信息导向）
└── explanation/    # 解释说明（理解导向）
```

### 构建文档

```bash
# 本地预览
just docs-serve

# 构建
just docs-build
```

---

## 配置规范

### 配置文件

- 主配置: `~/.yee88/yee88.toml`
- 定时任务: `~/.yee88/cron.toml`
- 锁文件: `~/.yee88/yee88.lock`

### 配置模型

- 使用 `pydantic-settings` 定义配置模型
- 支持 TOML 文件和环境变量

```python
from pydantic_settings import BaseSettings

class TakopiSettings(BaseSettings):
    default_engine: str = "codex"
    transport: str = "telegram"
```

---

## 插件开发

### 入口点

```toml
[project.entry-points."yee88.engine_backends"]
myengine = "my_package.runner:BACKEND"

[project.entry-points."yee88.transport_backends"]
mytransport = "my_package.backend:BACKEND"
```

### 公共 API

- 插件使用 `yee88.api` 模块
- 不要直接导入内部模块

---

## 常见任务

### 添加新 Runner

1. 在 `src/yee88/runners/` 创建 `{name}.py`
2. 实现 Runner 协议
3. 在 `src/yee88/schemas/` 创建 JSONL 解码器
4. 在 `pyproject.toml` 添加入口点
5. 添加测试到 `tests/`
6. 更新文档

### 添加 CLI 命令

1. 在 `src/yee88/cli/` 创建命令模块
2. 在 `src/yee88/cli/__init__.py` 注册命令
3. 添加测试

### 修改配置模型

1. 更新 `src/yee88/settings.py`
2. 在 `src/yee88/config_migrations.py` 添加迁移（如需要）
3. 更新文档

---

## 调试技巧

### 启用调试日志

```bash
yee88 --debug
```

### 检查配置

```bash
yee88 doctor
yee88 config list
```

### 查看日志

```bash
tail -f /tmp/yee88.log
```

---

## 不变式（Invariants）

**不要破坏这些规则：**

1. **Runner 契约**
   - 恰好一个 `StartedEvent`
   - 恰好一个 `CompletedEvent`
   - `CompletedEvent` 必须是最后一个事件
   - `CompletedEvent.resume == StartedEvent.resume`

2. **每线程串行化**
   - 同一 ResumeToken 最多一个活跃运行
   - 通过调度和 Runner 锁双重保证

3. **Resume Line**
   - 使用引擎原生恢复命令格式
   - Runner 是格式化和解析的权威

---

## 参考链接

- [Specification](docs/reference/specification.md) - 规范文档
- [Plugin API](docs/reference/plugin-api.md) - 插件 API
- [Architecture](docs/explanation/architecture.md) - 架构说明
- [Module Map](docs/explanation/module-map.md) - 模块地图
- [Repo Map](docs/reference/agents/repo-map.md) - 代码导航

---

## 快速命令

```bash
# 开发检查
just check

# 运行测试
pytest

# 文档预览
just docs-serve

# 变异测试
just mutate

# 配置检查
yee88 doctor
```
