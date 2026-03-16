# WeChat × Claude Code MCP

让 Claude Code 直接读取你的微信聊天记录。支持 macOS 和 Windows。

提取微信 (WeChat) 数据库密钥，解密 SQLCipher 加密的本地数据库，导出聊天记录。内置 MCP Server，让 AI 直接查询微信数据——不需要截图，不需要复制粘贴，你的 Claude 可以直接搜索、浏览、分析你的所有微信对话。

## 功能

- 🔑 **密钥提取**：macOS 通过 LLDB 内存扫描，Windows 通过 pymem 进程内存搜索
- 🔓 **数据库解密**：使用 SQLCipher 解密所有本地数据库（消息、联系人、会话等）
- 💬 **消息导出**：按联系人/群聊导出，支持模糊匹配、关键词搜索、日期筛选
- 🤖 **MCP Server**：注册到 Claude Code 后，AI 可直接查询微信数据
- 📡 **消息轮询**：实时监听指定对话的新消息，适配 Claude Code 的微信聊天模式

## 安装

### 通过 pip 安装（推荐）

```bash
pip install wechat-claudecode-mcp
```

安装后可用以下命令：

| 命令 | 功能 |
|------|------|
| `wechat-mcp` | 启动 MCP Server |
| `wechat-mcp-keygen` | 提取密钥（macOS） |
| `wechat-mcp-keygen-win` | 提取密钥（Windows） |
| `wechat-mcp-decrypt` | 解密数据库 |
| `wechat-mcp-export` | 导出聊天记录 |
| `wechat-mcp-verify` | 验证密钥 |
| `wechat-mcp-poll` | 轮询新消息 |

### 从源码安装

```bash
git clone https://github.com/SsssssSynqa/WeChat-ClaudeCode-MCP.git
cd WeChat-ClaudeCode-MCP
pip install -e .
```

### 系统依赖

macOS 还需要：

```bash
brew install llvm sqlcipher
```

## 快速开始（macOS）

### 1. 前置条件

- macOS arm64，微信 4.x
- 禁用 SIP：`csrutil disable`（提取密钥时需要，解密和查询不需要）
- 安装系统依赖：`brew install llvm sqlcipher`

### 2. 提取密钥

确保微信已登录并正在运行：

```bash
PYTHONPATH=$(lldb -P) wechat-mcp-keygen
```

密钥保存到 `~/.wechat-mcp/wechat_keys.json`。提取一次即可，微信大版本更新后需重新提取。

### 3. 注册 MCP Server 到 Claude Code

```bash
claude mcp add wechat -- wechat-mcp
```

就这么简单！注册后 AI 可以直接调用以下能力：

| Tool | 功能 |
|------|------|
| `get_recent_sessions` | 获取最近会话列表 |
| `get_chat_history` | 查看聊天记录（支持模糊匹配、日期筛选） |
| `search_messages` | 跨会话搜索关键词 |
| `get_contacts` | 搜索联系人 |

MCP Server 直接查询加密数据库（通过 sqlcipher3），无需预先解密，始终读取最新消息。

### 4. 其他工具（可选）

```bash
# 解密数据库（离线分析用）
wechat-mcp-decrypt

# 导出聊天记录
wechat-mcp-export                     # 列出所有会话
wechat-mcp-export -c "联系人名字"      # 导出指定会话
wechat-mcp-export -s "关键词"          # 搜索关键词
wechat-mcp-export --all               # 导出所有会话

# 轮询新消息（实时监听）
wechat-mcp-poll wxid_xxx              # 每8秒检查一次
wechat-mcp-poll wxid_xxx 5            # 自定义间隔
wechat-mcp-poll 12345@chatroom 10     # 轮询群聊
```

## 快速开始（Windows）

### 1. 前置条件

- Windows 10/11，微信 4.x（进程名 `Weixin.exe`）
- Python 3.10+

```bash
pip install wechat-claudecode-mcp[windows]
```

### 2. 提取密钥

以管理员身份运行 PowerShell，确保微信已登录：

```bash
wechat-mcp-keygen-win
```

密钥保存到 `~/.wechat-mcp/wechat_keys.json`。

### 3. 使用 MCP Server

Windows 暂不支持直接运行 MCP Server（需要 sqlcipher3 编译）。推荐方案：

- 如果在 Parallels 虚拟机中运行 Windows 微信，数据库文件可通过共享文件夹从 macOS 端访问
- 在 macOS 端安装 `wechat-mcp`，通过环境变量指向 Windows 数据路径：

```bash
claude mcp add wechat -- env WECHAT_MCP_KEYS=/path/to/keys.json WECHAT_MCP_DB_BASE=~/Documents/xwechat_files wechat-mcp
```

## 配置

MCP Server 通过以下方式自动查找密钥和数据库：

**密钥文件** (`wechat_keys.json`) 搜索顺序：
1. `WECHAT_MCP_KEYS` 环境变量
2. 当前目录
3. `~/.wechat-mcp/wechat_keys.json`

**数据库目录** 自动检测：
- macOS: `~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files`
- Windows: `%USERPROFILE%\Documents\xwechat_files`
- 可通过 `WECHAT_MCP_DB_BASE` 环境变量覆盖

## 工作原理

微信桌面版使用 SQLCipher (WCDB) 加密本地数据库。加密密钥存储在进程内存中，格式为 `x'<64字符密钥><32字符盐值>'`。

**macOS 密钥提取**：通过 LLDB 扫描 WeChat 进程内存，搜索符合密钥格式的字符串，然后通过 HMAC-SHA512 验证密钥正确性。需要禁用 SIP。

**Windows 密钥提取**：通过 pymem 扫描 `Weixin.exe` 进程内存，搜索数据库文件头中的盐值（salt），然后从盐值位置向前读取 64 字符得到密钥。需要管理员权限。

MCP Server 和消息轮询使用 [sqlcipher3](https://pypi.org/project/sqlcipher3/)（Python 绑定）直接查询加密数据库，每次只解密查询涉及的数据页，无需预先解密整个数据库文件。`wechat-mcp-decrypt` 和 `wechat-mcp-export` 则通过 sqlcipher CLI 将数据库完整解密为明文 SQLite 文件，适合离线分析和导出。

## 致谢

- [Thearas/wechat-db-decrypt-macos](https://github.com/Thearas/wechat-db-decrypt-macos) — 核心解密方案
- [ylytdeng/wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt) — 内存搜索方案参考

## License

WTFPL
