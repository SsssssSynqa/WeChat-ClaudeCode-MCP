"""一键配置微信 × Claude Code 环境。"""

import json
import os
import shutil
import subprocess
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


def check_node():
    """检查 Node.js 是否安装。"""
    if shutil.which("npx"):
        return True
    print("❌ 未检测到 Node.js / npx")
    print("   微信实时聊天需要 Node.js 18+")
    print("   安装：https://nodejs.org/ 或 brew install node")
    return False


def check_claude():
    """检查 Claude Code 版本。"""
    claude = shutil.which("claude")
    if not claude:
        print("❌ 未检测到 Claude Code")
        print("   安装：npm install -g @anthropic-ai/claude-code")
        return False

    try:
        result = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=10
        )
        version_str = result.stdout.strip().split()[0]  # e.g. "2.1.80 (Claude Code)"
        parts = version_str.split(".")
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

        if (major, minor, patch) < (2, 1, 80):
            print(f"⚠️  Claude Code 版本 {version_str}，需要 2.1.80+")
            print("   更新：claude update")
            return False

        print(f"✅ Claude Code {version_str}")
        return True
    except Exception as e:
        print(f"⚠️  无法检测 Claude Code 版本: {e}")
        return True  # 不阻塞


def register_mcp_server():
    """注册 MCP Server 到 Claude Code。"""
    try:
        result = subprocess.run(
            ["claude", "mcp", "add", "wechat", "--", "wechat-mcp"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            print("✅ MCP Server 已注册（聊天记录查询）")
        else:
            # 可能已经注册过了
            if "already exists" in result.stderr.lower():
                print("✅ MCP Server 已注册（聊天记录查询）")
            else:
                print(f"⚠️  MCP Server 注册可能有问题: {result.stderr.strip()}")
    except FileNotFoundError:
        print("⚠️  跳过 MCP Server 注册（未找到 claude 命令）")
    except Exception as e:
        print(f"⚠️  MCP Server 注册失败: {e}")


def write_mcp_json():
    """在当前目录写入 .mcp.json。"""
    mcp_json_path = Path.cwd() / ".mcp.json"

    if mcp_json_path.exists():
        # 读取现有内容，合并
        try:
            existing = json.loads(mcp_json_path.read_text(encoding="utf-8"))
            servers = existing.get("mcpServers", {})
            if "wechat" in servers:
                print("✅ .mcp.json 已包含微信 channel 配置")
                return
            servers["wechat"] = MCP_JSON_CONTENT["mcpServers"]["wechat"]
            existing["mcpServers"] = servers
            mcp_json_path.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print("✅ .mcp.json 已更新（添加微信 channel）")
        except Exception:
            # 解析失败，备份后覆盖
            backup = mcp_json_path.with_suffix(".mcp.json.bak")
            mcp_json_path.rename(backup)
            mcp_json_path.write_text(
                json.dumps(MCP_JSON_CONTENT, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"✅ .mcp.json 已创建（旧文件备份到 {backup.name}）")
    else:
        mcp_json_path.write_text(
            json.dumps(MCP_JSON_CONTENT, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("✅ .mcp.json 已创建")


def main():
    print("🔧 微信 × Claude Code 一键配置\n")

    ok = True

    # 检查环境
    if not check_node():
        ok = False

    if not check_claude():
        ok = False

    if not ok:
        print("\n请先安装缺失的依赖，然后重新运行 wechat-mcp-setup")
        sys.exit(1)

    print()

    # 注册 MCP Server
    register_mcp_server()

    # 写入 .mcp.json
    write_mcp_json()

    # 完成
    print("\n" + "=" * 50)
    print("🎉 配置完成！")
    print()
    print("启动微信聊天：")
    print("  wechat-mcp-chat")
    print()
    print("首次启动会弹出微信二维码，用手机扫码登录即可。")
    print("之后每次只需运行 wechat-mcp-chat 即可自动连接。")
    print("=" * 50)


if __name__ == "__main__":
    main()
