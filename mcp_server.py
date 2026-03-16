#!/usr/bin/env python3
"""Backwards-compatible wrapper. Use `wechat-mcp` command instead."""
from wechat_mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
