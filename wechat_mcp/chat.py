"""一键启动微信 × Claude Code 实时聊天。"""

import json
import os
import shutil
import sys
from pathlib import Path


MCP_JSON_CONTENT = {
    "mcpServers": {
        "wechat": {
            "command": "npx",
            "args": ["claude-wechat-channel"],
        }
    }
}


def ensure_mcp_json():
    """确保当前目录有 .mcp.json，没有则创建。"""
    mcp_json_path = Path.cwd() / ".mcp.json"

    if mcp_json_path.exists():
        try:
            existing = json.loads(mcp_json_path.read_text(encoding="utf-8"))
            if "wechat" in existing.get("mcpServers", {}):
                return  # 已配置
        except Exception:
            pass

    # 需要创建或补充
    if mcp_json_path.exists():
        try:
            existing = json.loads(mcp_json_path.read_text(encoding="utf-8"))
            servers = existing.setdefault("mcpServers", {})
            servers["wechat"] = MCP_JSON_CONTENT["mcpServers"]["wechat"]
            content = existing
        except Exception:
            content = MCP_JSON_CONTENT
    else:
        content = MCP_JSON_CONTENT

    mcp_json_path.write_text(
        json.dumps(content, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("📝 已自动创建 .mcp.json")


def main():
    # 检查 claude 是否存在
    if not shutil.which("claude"):
        print("❌ 未找到 claude 命令")
        print("   安装：npm install -g @anthropic-ai/claude-code")
        sys.exit(1)

    # 确保配置存在
    ensure_mcp_json()

    # 替换当前进程为 claude
    print("🚀 启动微信聊天...\n")
    os.execvp(
        "claude",
        ["claude", "--dangerously-load-development-channels", "server:wechat"],
    )


if __name__ == "__main__":
    main()
