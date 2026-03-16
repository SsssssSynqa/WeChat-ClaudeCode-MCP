"""Centralized path resolution for WeChat MCP."""

import os
import sys
import glob as _glob


def get_keys_path():
    """Find wechat_keys.json. Search order:
    1. WECHAT_MCP_KEYS env var
    2. ./wechat_keys.json (current directory)
    3. ~/.wechat-mcp/wechat_keys.json
    """
    env = os.environ.get("WECHAT_MCP_KEYS")
    if env and os.path.isfile(env):
        return env

    cwd = os.path.join(os.getcwd(), "wechat_keys.json")
    if os.path.isfile(cwd):
        return cwd

    home = os.path.expanduser("~/.wechat-mcp/wechat_keys.json")
    if os.path.isfile(home):
        return home

    # Also check for Windows keys
    for name in ("wechat_keys_win.json",):
        cwd_win = os.path.join(os.getcwd(), name)
        if os.path.isfile(cwd_win):
            return cwd_win
        home_win = os.path.expanduser(f"~/.wechat-mcp/{name}")
        if os.path.isfile(home_win):
            return home_win

    return home  # fallback path


def get_db_base():
    """Get WeChat database base directory, OS-aware."""
    env = os.environ.get("WECHAT_MCP_DB_BASE")
    if env and os.path.isdir(env):
        return env

    if sys.platform == "darwin":
        base = os.path.expanduser(
            "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
        )
        # Also check Parallels shared folder (Windows WeChat accessed from Mac)
        if not os.path.isdir(base):
            alt = os.path.expanduser("~/Documents/xwechat_files")
            if os.path.isdir(alt):
                return alt
        return base
    elif sys.platform == "win32":
        for base in [
            os.path.expanduser(r"~\Documents\xwechat_files"),
            r"C:\Mac\Home\Documents\xwechat_files",
        ]:
            if os.path.isdir(base):
                return base
        return os.path.expanduser(r"~\Documents\xwechat_files")
    else:
        return os.path.expanduser("~/xwechat_files")


def get_db_storage():
    """Find the db_storage directory."""
    db_base = get_db_base()
    candidates = _glob.glob(os.path.join(db_base, "*", "db_storage"))
    return candidates[0] if candidates else None


def get_default_output_dir():
    """Get default output directory for keys and decrypted files."""
    d = os.path.expanduser("~/.wechat-mcp")
    os.makedirs(d, exist_ok=True)
    return d
