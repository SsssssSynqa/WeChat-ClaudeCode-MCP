# WeChat × Claude Code MCP

让 Claude Code 直接读取你的微信聊天记录。支持 macOS 和 Windows。

提取微信 (WeChat) 数据库密钥，解密 SQLCipher 加密的本地数据库，导出聊天记录。内置 MCP Server，让 AI 直接查询微信数据——不需要截图，不需要复制粘贴，你的 Claude 可以直接搜索、浏览、分析你的所有微信对话。

## 功能

- 🔑 **密钥提取**：macOS 通过 LLDB 内存扫描，Windows 通过 pymem 进程内存搜索
- 🔓 **数据库解密**：使用 SQLCipher 解密所有本地数据库（消息、联系人、会话等）
- 💬 **消息导出**：按联系人/群聊导出，支持模糊匹配、关键词搜索、日期筛选
- 🤖 **MCP Server**：注册到 Claude Code 后，AI 可直接查询微信数据
- 📡 **消息轮询**：实时监听指定对话的新消息，适配 Claude Code 的微信聊天模式

## 快速开始（macOS）

### 1. 前置条件

- macOS arm64，微信 4.x
- 禁用 SIP：`csrutil disable`（提取密钥时需要，解密和查询不需要）
- 安装依赖：`brew install llvm sqlcipher`
- Python 依赖：`pip3 install fastmcp sqlcipher3`（MCP Server 和实时轮询需要）

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
pip3 install fastmcp sqlcipher3
claude mcp add wechat -- python3 $(pwd)/mcp_server.py
```

MCP Server 直接查询加密数据库（通过 sqlcipher3），无需预先解密，始终读取最新消息。

注册后 AI 可以直接调用以下能力：

| Tool | 功能 |
|------|------|
| `get_recent_sessions` | 获取最近会话列表 |
| `get_chat_history` | 查看聊天记录（支持模糊匹配、日期筛选） |
| `search_messages` | 跨会话搜索关键词 |
| `get_contacts` | 搜索联系人 |

### 6. 消息轮询（实时监听新消息）

```bash
# 轮询指定对话，每8秒检查一次（默认）
python3 poll_messages.py wxid_xxx

# 自定义轮询间隔
python3 poll_messages.py wxid_xxx 5

# 轮询群聊
python3 poll_messages.py 12345@chatroom 10
```

检测到新消息时打印并退出，适合在 Claude Code 中配合后台任务使用。

## 快速开始（Windows）

### 1. 前置条件

- Windows 10/11，微信 4.x（进程名 `Weixin.exe`）
- Python 3.10+
- `pip install pymem psutil`

### 2. 提取密钥

以管理员身份运行 PowerShell，确保微信已登录：

```bash
python find_key_windows.py
```

密钥保存到 `wechat_keys_win.json`。

### 3. 使用 MCP Server

Windows 暂不支持直接运行 MCP Server（需要 sqlcipher3 编译）。推荐方案：

- 如果在 Parallels 虚拟机中运行 Windows 微信，数据库文件可通过共享文件夹从 macOS 端访问
- 将 `wechat_keys_win.json` 复制到 macOS 端的项目目录
- 修改 MCP Server 的 `DB_BASE` 和 `KEYS_FILE` 指向 Windows 微信的数据路径

## 工作原理

微信桌面版使用 SQLCipher (WCDB) 加密本地数据库。加密密钥存储在进程内存中，格式为 `x'<64字符密钥><32字符盐值>'`。

**macOS 密钥提取**：通过 LLDB 调试器在 `setCipherKey` 函数设断点，从寄存器读取密钥字符串。需要禁用 SIP。

**Windows 密钥提取**：通过 pymem 扫描 `Weixin.exe` 进程内存，搜索数据库文件头中的盐值（salt），然后从盐值位置向前读取 64 字符得到密钥。需要管理员权限。

MCP Server 和消息轮询使用 [sqlcipher3](https://pypi.org/project/sqlcipher3/)（Python 绑定）直接查询加密数据库，每次只解密查询涉及的数据页，无需预先解密整个数据库文件。`decrypt_db.py` 和 `export_messages.py` 则通过 sqlcipher CLI 将数据库完整解密为明文 SQLite 文件，适合离线分析和导出。

## 致谢

- [Thearas/wechat-db-decrypt-macos](https://github.com/Thearas/wechat-db-decrypt-macos) — 核心解密方案
- [ylytdeng/wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt) — 内存搜索方案参考

## License

WTFPL
