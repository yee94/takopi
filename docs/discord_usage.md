# yee88 Discord 用法速查

## 启动
```bash
yee88 --onboard  # 首次配置
yee88            # 启动 Bot
```

## 基本对话
```
帮我写一个 Python 函数计算斐波那契数列
```

## 切换引擎
```
/claude 解释这段代码
/codex 修复这个 bug  
/opencode 优化算法
/pi 分析这个问题
```

## 项目操作
```
/myproject 实现登录功能        # 使用项目别名
@feature-branch 开发新功能     # 切换到分支
```

## 线程对话
- Bot 自动创建线程
- 在线程里回复继续对话
- 使用 resume token 恢复会话

## 配置
```toml
# ~/.config/yee88/yee88.toml
transport = "discord"

[transports.discord]
bot_token = "YOUR_BOT_TOKEN"
guild_id = 123456789      # 可选：限制服务器
channel_id = 987654321    # 可选：默认频道
```
