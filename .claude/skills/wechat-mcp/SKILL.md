---
name: wechat-mcp
description: 微信 MCP 使用指南。查询聊天记录、搜索消息、联系人查找、消息轮询。当用户提到微信、聊天记录、消息搜索时自动激活。
argument-hint: [操作描述，如"最近谁找我了" "搜一下关于xx的聊天" "看看xx的消息"]
---

# 微信 MCP 使用指南

本项目提供 4 个 MCP 工具，Claude Code 注册后可直接调用。

## 可用工具

| Tool | 功能 | 关键参数 |
|------|------|----------|
| `get_recent_sessions` | 最近会话列表 | `limit`（默认20） |
| `get_chat_history` | 查看聊天记录 | `chat_name`（支持模糊匹配）、`limit`、`start_date`、`end_date` |
| `search_messages` | 跨会话搜索关键词 | `keyword`、`limit` |
| `get_contacts` | 搜索联系人 | `query`（名字/备注/微信号）、`limit` |

## 常用场景

### 查看最近会话

直接调用 `get_recent_sessions`，返回最近的会话列表，包含最新消息摘要、未读数、时间。

### 查看某人的聊天记录

调用 `get_chat_history`，`chat_name` 支持模糊匹配（备注名、昵称、微信号都行）：

```
get_chat_history(chat_name="张三", limit=30)
```

按日期筛选（ISO 格式）：

```
get_chat_history(chat_name="张三", start_date="2026-03-01", end_date="2026-03-15")
```

### 搜索关键词

调用 `search_messages`，跨所有会话搜索：

```
search_messages(keyword="会议", limit=20)
```

### 查找联系人

调用 `get_contacts`，支持模糊搜索：

```
get_contacts(query="张", limit=10)
```

## 重要注意事项

1. **sender 为空 = 用户自己发的消息**。微信数据库中，自己发送的消息不带 sender 字段。显示时应标注为用户本人，而非"系统"或"未知"
2. **数据是实时的**。MCP Server 通过 sqlcipher3 直接查询加密数据库，每次调用都读取最新数据
3. **只读操作**。所有工具都是查询，不会修改微信数据
4. **群聊消息**。群聊的 username 格式为 `xxx@chatroom`，消息包含发送者信息
5. **消息类型**。纯文本直接返回内容；图片、语音、视频等显示为 `[图片]`、`[语音]`、`[视频]` 等标记，无法读取实际内容

## 消息轮询（进阶）

如果需要实时监听某个对话的新消息，可用命令行工具：

```bash
wechat-mcp-poll <username> [interval_seconds]
```

- `username`：联系人的 wxid 或群聊 ID（从 `get_contacts` 或 `get_recent_sessions` 获取）
- `interval_seconds`：轮询间隔，默认 8 秒
- 检测到新消息时输出到 stdout 并退出，适合配合 Claude Code 的 `TaskOutput` 使用

## 发送消息

MCP 是只读的，不支持发送消息。如需发送消息，需通过 macOS osascript UI 自动化操控微信桌面客户端。

### 切换聊天对象

有两种方案，根据场景选择：

#### 方案A：交互式（用户在场）

分步操作，搜索后截图确认再按回车选择联系人。

```bash
# 步骤1: 搜索联系人（不按回车）
osascript <<'ASCRIPT'
set the clipboard to "搜索词"
tell application "System Events"
    tell process "WeChat"
        set frontmost to true
        delay 0.2
        keystroke "f" using command down
        delay 0.5
        keystroke "v" using command down
        delay 2.0
    end tell
end tell
ASCRIPT

# 步骤2: 截图确认搜索结果正确

# 步骤3: 确认无误后按回车选择联系人
osascript -e 'tell application "System Events" to key code 36'
```

⚠️ 步骤2和3之间如果间隔太久或切换了窗口，搜索框可能消失，需要从步骤1重新来过。

#### 方案B：一键完成（无人值守 / scheduled-task）

搜索→回车→粘贴消息→发送全部在一个 osascript 里完成，不中断焦点。发送后用数据库验证。

```bash
# ⚠️ 不要加 Escape、不要加 Cmd+A，会破坏焦点状态！
osascript <<'ASCRIPT'
tell application "WeChat" to activate
delay 1
set the clipboard to "搜索词"
tell application "System Events"
    tell process "WeChat"
        set frontmost to true
        delay 0.3
        keystroke "f" using command down
        delay 0.5
        keystroke "v" using command down
        delay 2.0
        key code 36
        delay 1.5
    end tell
end tell
set the clipboard to "消息内容"
tell application "System Events"
    tell process "WeChat"
        keystroke "v" using command down
        delay 0.3
        key code 36
    end tell
end tell
ASCRIPT

# 发送后用数据库验证消息是否到了正确的人
```

### 发送消息的安全规则

- **中文和特殊字符必须用剪贴板**。`keystroke` 无法正确输入非 ASCII 字符，会产生乱码
- **搜索词尽量简短**。避免使用特殊字符（颜文字、泰文等），osascript 可能将其损坏为乱码
- **用户在场时**：搜索后截图确认再按回车（方案A）
- **无人值守时**：一个 osascript 一气呵成，发送后用数据库验证（方案B）
- **如果不确定搜索结果是否正确，放弃操作**。宁可不发，不能发错

### 反模式（踩过的坑）

1. **不要用 `keystroke` 输入中文或特殊字符**。会被输入法拦截或产生乱码，必须用剪贴板
2. **搜索框里不要按 Cmd+A**。`Cmd+F` 打开搜索后直接 `Cmd+V` 粘贴即可。`Cmd+A` 会破坏微信的焦点状态，导致回车选择联系人后光标无法进入消息输入框
3. **不要把搜索和回车拆成两个 osascript**（无人值守时）。焦点离开微信后搜索框会消失，必须在一个脚本里一气呵成
4. **不要在 scheduled-task 里依赖截图确认**。截图需要手动授权，无法自动化。改用发后数据库验证

## 故障排查

- **"无法打开 xxx.db"**：检查密钥文件是否存在（`~/.wechat-mcp/wechat_keys.json`），微信是否正在运行
- **密钥验证失败**：微信可能已更新，需要重新提取密钥（`wechat-mcp-keygen`，需禁用 SIP）
- **联系人名字显示为 wxid**：联系人数据库可能未解密或该联系人没有设置备注/昵称
