# WeChat × Claude Code MCP

让 Claude Code 直接读取你的微信聊天记录。

提取微信 (WeChat) 数据库密钥，解密 SQLCipher 加密的本地数据库，导出聊天记录。内置 MCP Server，让 AI 直接查询微信数据——不需要截图，不需要复制粘贴，你的 Claude 可以直接搜索、浏览、分析你的所有微信对话。

## 功能

- 🔑 **密钥提取**：通过 LLDB 内存扫描自动提取微信数据库加密密钥
- 🔓 **数据库解密**：使用 SQLCipher 解密所有本地数据库（消息、联系人、会话等）
- 💬 **消息导出**：按联系人/群聊导出，支持模糊匹配、关键词搜索、日期筛选
- 🤖 **MCP Server**：注册到 Claude Code 后，AI 可直接查询微信数据

## 快速开始

### 1. 前置条件

- macOS arm64，微信 4.x
- 禁用 SIP：`csrutil disable`（提取密钥时需要，解密和查询不需要）
- 安装依赖：`brew install llvm sqlcipher`

### 2. 提取密钥

确保微信已登录并正在运行：

```bash
PYTHONPATH=$(lldb -P) python3 find_key_memscan.py
```

密钥保存到 `wechat_keys.json`。提取一次即可，微信大版本更新后需重新提取。

### 3. 解密数据库

```bash
python3 decrypt_db.py
```

### 4. 导出聊天记录

```bash
# 列出所有会话
python3 export_messages.py

# 导出指定会话（支持模糊匹配联系人名）
python3 export_messages.py -c "联系人名字"
python3 export_messages.py -c wxid_xxx
python3 export_messages.py -c 12345@chatroom

# 导出最近 N 条
python3 export_messages.py -c "联系人名字" -n 50

# 搜索关键词
python3 export_messages.py -s "关键词"

# 导出所有会话
python3 export_messages.py --all
```

### 5. MCP Server（让 AI 直接查询）

安装依赖并注册到 Claude Code：

```bash
pip3 install fastmcp
claude mcp add wechat -- python3 $(pwd)/mcp_server.py
```

注册后 AI 可以直接调用以下能力：

| Tool | 功能 |
|------|------|
| `get_recent_sessions` | 获取最近会话列表 |
| `get_chat_history` | 查看聊天记录（支持模糊匹配、日期筛选） |
| `search_messages` | 跨会话搜索关键词 |
| `get_contacts` | 搜索联系人 |
| `sync` | 手动同步数据库（通常自动同步，每60秒） |

## 工作原理

微信桌面版使用 SQLCipher 加密本地数据库。加密密钥在微信启动时通过 PBKDF2-HMAC-SHA512 派生，存储在进程内存中。本工具通过 LLDB 调试器扫描微信进程内存，定位并提取这些密钥，然后使用 sqlcipher 解密数据库文件为普通 SQLite 格式。

## 致谢

- [Thearas/wechat-db-decrypt-macos](https://github.com/Thearas/wechat-db-decrypt-macos) — 核心解密方案
- [ylytdeng/wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt) — 内存搜索方案参考

## License

WTFPL
