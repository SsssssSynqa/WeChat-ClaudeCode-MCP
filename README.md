# WeChat × Claude Code

让 Claude Code 连接微信——查历史记录、监听新消息、实时聊天，三种能力可独立使用也可搭配组合。

## 🚀 只想在微信里跟 Claude 聊天？三步搞定

不需要提取密钥、不需要禁用 SIP、不需要任何技术背景：

```bash
pip install wechat-claudecode-mcp    # 1. 安装
wechat-mcp-setup                      # 2. 一键配置（只需运行一次）
wechat-mcp-chat                       # 3. 启动！扫码登录，开始聊天
```

首次启动会弹出微信二维码，用手机扫码登录。之后每次只需 `wechat-mcp-chat` 即可自动连接。

> 💡 这使用的是微信官方的 **微信ClawBot**（@WeixinTeam 出品，基于 iLink Bot API）。扫码后微信里会出现一个名叫"微信ClawBot"的 AI 联系人，你可以在它的设置里自定义名字和头像（比如改成"Claude code" + Claude logo）。直接给它发消息就是在跟 Claude 聊天。

---

## 三种能力一览

本项目提供三种能力，定位不同，解决不同场景的需求：

| | 📚 MCP Server（本项目） | 📡 消息轮询 + 发送（本项目） | 💬 微信 ClawBot 实时聊天 |
|---|---|---|---|
| **一句话** | Claude 读取你的微信聊天记录 | Claude 用你的微信号收发消息 | 在微信里跟 Claude bot 实时对话 |
| **数据来源** | 本地微信数据库 | 本地数据库 + osascript UI 自动化 | 微信官方 iLink Bot API |
| **方向** | 只读（查询历史） | 双向（监听 + 发送） | 双向（收 + 发） |
| **用谁的微信号** | 你自己的 | 你自己的 | 微信官方分配的 bot 账号 |
| **能给任何人发消息** | ❌ | ✅ 能（以你的身份） | ❌ 只能回复给 bot 发消息的人 |
| **跟 Claude 对话需要** | — | 另一个微信号 | 同一个微信号直接发 |
| **需要提取密钥** | ✅ 是 | ✅ 是 | ❌ 否 |
| **需要禁用 SIP** | 仅提取密钥时 | 仅提取密钥时 | ❌ 否 |
| **需要额外安装** | pip install | pip install | npx（自动） |
| **实现方式** | sqlcipher3 查询加密数据库 | 轮询本地数据库 + osascript 发送 | Claude Code development channel |

**怎么选？**
- 只想让 Claude 查你的聊天记录 → MCP Server
- 想让 Claude 用你的微信号跟别人聊天（需要第二个微信号跟 Claude 对话） → 消息轮询 + 发送
- 想在微信里直接跟 Claude 一对一聊天（最简单，不需要第二个号） → 微信 ClawBot 实时聊天
- 推荐组合：**MCP Server + ClawBot 实时聊天**——Claude 既能翻你的聊天历史，又能在微信里跟你实时对话

---

## 📚 MCP Server：读取微信聊天记录

让 Claude Code 直接查询你的微信本地数据库——搜索消息、浏览会话、查看联系人，不需要截图不需要复制粘贴。

### 安装

```bash
# 安装 Python 包
pip install wechat-claudecode-mcp

# macOS 系统依赖
brew install llvm sqlcipher
```

从源码安装：

```bash
git clone https://github.com/SsssssSynqa/WeChat-ClaudeCode-MCP.git
cd WeChat-ClaudeCode-MCP
pip install -e .
```

### 快速开始（macOS）

**前置条件**：macOS arm64，微信 4.x，禁用 SIP（`csrutil disable`，仅提取密钥时需要）

**第一步：提取密钥**（确保微信已登录并正在运行）

```bash
PYTHONPATH=$(lldb -P) wechat-mcp-keygen
```

密钥保存到 `~/.wechat-mcp/wechat_keys.json`。只需提取一次，微信大版本更新后重新提取。

**第二步：注册 MCP Server**

```bash
claude mcp add wechat -- wechat-mcp
```

就这么简单！注册后 Claude 可以直接调用：

| Tool | 功能 |
|------|------|
| `get_recent_sessions` | 获取最近会话列表（包含最新消息摘要、未读数） |
| `get_chat_history` | 查看聊天记录（支持模糊匹配联系人名、日期范围筛选） |
| `search_messages` | 跨所有会话搜索关键词 |
| `get_contacts` | 搜索联系人（匹配昵称、备注名、wxid） |

MCP Server 通过 sqlcipher3 直接查询加密数据库，无需预先解密，始终读取最新消息。

### 快速开始（Windows）

**前置条件**：Windows 10/11，微信 4.x（进程名 `Weixin.exe`），Python 3.10+

```bash
pip install wechat-claudecode-mcp[windows]
```

以管理员身份运行 PowerShell 提取密钥：

```bash
wechat-mcp-keygen-win
```

Windows 暂不支持直接运行 MCP Server（需要 sqlcipher3 编译）。如果在 Parallels 虚拟机中运行 Windows 微信，可在 macOS 端通过环境变量指向 Windows 数据路径：

```bash
claude mcp add wechat -- env WECHAT_MCP_KEYS=/path/to/keys.json WECHAT_MCP_DB_BASE=~/Documents/xwechat_files wechat-mcp
```

### 其他工具

安装后还可使用以下命令行工具：

```bash
# 解密数据库（导出为明文 SQLite，适合离线分析）
wechat-mcp-decrypt

# 导出聊天记录为文本文件
wechat-mcp-export                     # 列出所有会话
wechat-mcp-export -c "联系人名字"      # 导出指定会话
wechat-mcp-export -s "关键词"          # 搜索关键词
wechat-mcp-export --all               # 导出所有会话

# 验证密钥是否正确
wechat-mcp-verify
```

### 配置

**密钥文件** (`wechat_keys.json`) 搜索顺序：
1. `WECHAT_MCP_KEYS` 环境变量
2. 当前目录
3. `~/.wechat-mcp/wechat_keys.json`

**数据库目录** 自动检测：
- macOS: `~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files`
- Windows: `%USERPROFILE%\Documents\xwechat_files`
- 可通过 `WECHAT_MCP_DB_BASE` 环境变量覆盖

---

## 📡 消息轮询 + 发送：用你的微信号收发消息

`wechat-mcp-poll` 在后台定时查询本地数据库，发现新消息时通知 Claude。配合 macOS 的 osascript UI 自动化，Claude 可以通过你的微信桌面客户端**以你的身份**发送消息给任何联系人。

这是一个完整的双向对话方案：轮询负责"听"，osascript 负责"说"。

### 使用方法

```bash
# 监听指定联系人（默认每 8 秒检查一次）
wechat-mcp-poll wxid_xxx

# 自定义轮询间隔（秒）
wechat-mcp-poll wxid_xxx 5

# 监听群聊
wechat-mcp-poll 12345@chatroom 10
```

发送消息由 Claude 通过 osascript 操作微信桌面客户端实现（搜索联系人 → 选择 → 输入 → 发送）。

### 跟 Claude 对话需要两个微信号

因为 Claude 是以**你的微信号**的身份发消息的，所以你不能用同一个号跟它对话（那等于自己跟自己聊天）。你需要用**另一个微信号**给你的微信发消息，Claude 在你的电脑上看到新消息后通过 osascript 回复。

### 轮询方案 vs ClawBot 实时聊天的区别

| | 轮询 + osascript | ClawBot 实时聊天 |
|---|---|---|
| **跟 Claude 对话** | 需要两个微信号 | 一个微信号直接发 |
| **能给别人发消息** | ✅ 能给任何联系人发 | ❌ 只能回复发给 bot 的人 |
| **消息延迟** | 取决于轮询间隔（默认 8 秒） | 实时推送，几乎无延迟 |
| **发送方式** | osascript 模拟键盘操作（有翻车风险） | 微信官方 API 直接发送（稳定） |
| **平台限制** | 仅 macOS（依赖 osascript） | 跨平台（Node.js） |

---

## 💬 微信 ClawBot 实时聊天：在微信里跟 Claude 对话

基于微信官方 iLink Bot API 和 [claude-wechat-channel](https://github.com/fengliu222/claude-wechat-channel)，让你直接在微信里跟 Claude Code 实时对话——你发一条微信消息，Claude 在同一个聊天窗口里回复你。回复的是当前 Claude Code session 里的 Claude（读了你的 CLAUDE.md 和 memory 的那个），不是一个裸的模型。

### 前置条件

- Claude Code **v2.1.80+**（`claude --version` 检查，`claude update` 更新）
- Node.js 18+
- 不需要提取密钥，不需要禁用 SIP

### 一键安装

```bash
pip install wechat-claudecode-mcp    # 安装（如果还没装）
wechat-mcp-setup                      # 一键配置
wechat-mcp-chat                       # 启动聊天
```

`wechat-mcp-setup` 会自动检查环境、注册 MCP Server、创建配置文件。只需运行一次。

之后每次想聊天，运行 `wechat-mcp-chat` 即可。

### 手动安装（如果一键安装有问题）

在项目目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "wechat": {
      "command": "npx",
      "args": ["claude-wechat-channel"]
    }
  }
}
```

启动：

```bash
claude --dangerously-load-development-channels server:wechat
```

首次启动会弹出微信二维码，用手机扫码登录。之后凭证保存在 `~/.wechat-claude/`，下次自动连接。

### 工作原理

微信官方提供了 iLink Bot API，允许开发者创建 bot 账号接收和回复微信消息。claude-wechat-channel 将这个能力接入了 Claude Code 的 development channel 机制。消息流程：

```
你在微信发消息 → iLink Bot API → claude-wechat-channel → Claude Code session 处理 → 回复推回微信
```

这不是登录你的微信号，而是通过微信官方的 **微信ClawBot**（@WeixinTeam 出品）创建一个 bot 账号。扫码后你的微信里会出现一个名叫"微信ClawBot"的 AI 联系人，可以在它的设置页自定义名字和头像。给它发消息就是在跟 Claude 聊天。

### 注意事项

- `--dangerously-load-development-channels` 是 Claude Code 的实验性功能，只在 CLI 终端可用，**PC/Mac 客户端不支持**
- 这是 **bot 模式**：只能回复给 bot 发消息的人，不能主动给你通讯录里的其他人发消息
- **24 小时回复限制**：你发消息后，bot 仅接收 24 小时内的回复。超过 24 小时未回复则该消息作废
- 微信有 4000 字符消息长度限制，claude-wechat-channel 会自动分段发送长回复
- Claude 的回复会自动从 Markdown 转为纯文本（微信不渲染 Markdown）
- bot 的名字和头像可以自定义：在微信里点击 bot 头像 → 设置 → 修改名字/头像

---

## 搭配使用

三种能力可以自由组合：

**MCP Server + ClawBot 实时聊天**（推荐）：Claude 既能翻你的聊天历史（"帮我找找上周小明说的那个链接"），又能在微信里跟你一对一实时对话。最简单的组合，不需要第二个微信号。

**MCP Server + 轮询 + 发送**：Claude 能查历史记录，还能以你的身份给任何人发消息。适合需要 Claude 帮你回复别人、在群里发言等场景。需要第二个微信号跟 Claude 对话。

**全部搭配**：Claude 能查历史、以你的身份发消息、还能在 ClawBot 里跟你一对一聊天。

注意：MCP Server / 轮询（本项目）和 ClawBot 实时聊天（claude-wechat-channel）是两个独立的项目，安装方式不同，数据来源也不同。MCP Server 和轮询读本地数据库（你的微信账号的所有消息），ClawBot 走微信官方 iLink Bot API（独立的 bot 账号）。

---

## 工作原理

微信桌面版使用 SQLCipher (WCDB) 加密本地数据库。加密密钥存储在进程内存中，格式为 `x'<64字符密钥><32字符盐值>'`。

**macOS 密钥提取**：通过 LLDB 扫描 WeChat 进程内存，搜索符合密钥格式的字符串，然后通过 HMAC-SHA512 验证密钥正确性。需要禁用 SIP。

**Windows 密钥提取**：通过 pymem 扫描 `Weixin.exe` 进程内存，搜索数据库文件头中的盐值（salt），然后从盐值位置向前读取 64 字符得到密钥。需要管理员权限。

MCP Server 和消息轮询使用 [sqlcipher3](https://pypi.org/project/sqlcipher3/)（Python 绑定）直接查询加密数据库，每次只解密查询涉及的数据页，无需预先解密整个数据库文件。`wechat-mcp-decrypt` 和 `wechat-mcp-export` 则通过 sqlcipher CLI 将数据库完整解密为明文 SQLite 文件，适合离线分析和导出。

## 致谢

- [Thearas/wechat-db-decrypt-macos](https://github.com/Thearas/wechat-db-decrypt-macos) — 核心解密方案
- [ylytdeng/wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt) — 内存搜索方案参考
- [fengliu222/claude-wechat-channel](https://github.com/fengliu222/claude-wechat-channel) — 微信 ClawBot 实时聊天 channel（基于微信官方 iLink Bot API）

## License

WTFPL
