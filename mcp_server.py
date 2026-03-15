#!/usr/bin/env python3
"""
WeChat MCP Server — let AI query your WeChat messages directly.

Queries encrypted databases directly via sqlcipher3, no decryption step needed.

Requirements:
    pip3 install fastmcp sqlcipher3

Setup with Claude Code:
    claude mcp add wechat -- python3 /path/to/mcp_server.py

Tools provided:
    - get_recent_sessions(limit)   — recent chat sessions
    - get_chat_history(chat_name)  — chat history (fuzzy name match)
    - search_messages(keyword)     — search across all chats
    - get_contacts(query)          — search contacts
"""

import sqlcipher3
import os
import re
import hashlib
import json
import glob as _glob
from datetime import datetime

from fastmcp import FastMCP

# ── Configuration ────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(SCRIPT_DIR, "wechat_keys.json")

DB_BASE = os.path.expanduser(
    "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
)

MSG_TYPE_MAP = {
    1: "文本", 3: "图片", 34: "语音", 42: "名片",
    43: "视频", 47: "表情", 48: "位置", 49: "链接/文件",
    50: "通话", 10000: "系统", 10002: "撤回",
}


# ── Encrypted DB helpers ────────────────────────────────────────────────────

_db_storage = None
_keys = None


def _get_db_storage():
    global _db_storage
    if _db_storage is None:
        candidates = _glob.glob(os.path.join(DB_BASE, "*", "db_storage"))
        _db_storage = candidates[0] if candidates else ""
    return _db_storage


def _get_keys():
    global _keys
    if _keys is None:
        if os.path.isfile(KEYS_FILE):
            with open(KEYS_FILE) as f:
                _keys = json.load(f)
        else:
            _keys = {}
    return _keys


def _open_db(db_rel_path):
    """Open an encrypted WeChat database directly. Returns a connection."""
    db_storage = _get_db_storage()
    keys = _get_keys()
    if not db_storage or db_rel_path not in keys:
        return None

    db_path = os.path.join(db_storage, db_rel_path)
    if not os.path.isfile(db_path):
        return None

    key_hex = keys[db_rel_path]
    conn = sqlcipher3.connect(db_path)
    conn.execute(f"PRAGMA key = \"x'{key_hex}'\"")
    conn.execute("PRAGMA cipher_page_size = 4096")
    return conn


def _username_to_table(username):
    h = hashlib.md5(username.encode()).hexdigest()
    return f"Msg_{h}"


# ── Contact cache ────────────────────────────────────────────────────────────

_contacts = None  # {username: display_name}
_contacts_full = None  # [{username, nick_name, remark}]


def _load_contacts():
    global _contacts, _contacts_full
    if _contacts is not None:
        return

    _contacts = {}
    _contacts_full = []

    conn = _open_db("contact/contact.db")
    if not conn:
        return

    try:
        for username, remark, nick_name in conn.execute(
            "SELECT username, remark, nick_name FROM contact"
        ):
            display = remark or nick_name or username
            _contacts[username] = display
            _contacts_full.append({
                "username": username,
                "nick_name": nick_name or "",
                "remark": remark or "",
            })
        # Also load strangers
        try:
            for username, remark, nick_name in conn.execute(
                "SELECT username, remark, nick_name FROM stranger"
            ):
                if username not in _contacts:
                    display = remark or nick_name or username
                    _contacts[username] = display
                    _contacts_full.append({
                        "username": username,
                        "nick_name": nick_name or "",
                        "remark": remark or "",
                    })
        except Exception:
            pass
    finally:
        conn.close()


def _get_contacts():
    _load_contacts()
    return _contacts


def _resolve_username(chat_name):
    """Resolve chat_name (display name, remark, or wxid) to username."""
    names = _get_contacts()

    # Direct match
    if chat_name in names or chat_name.startswith("wxid_") or "@chatroom" in chat_name:
        return chat_name

    # Exact match on display name
    chat_lower = chat_name.lower()
    for uname, display in names.items():
        if chat_lower == display.lower():
            return uname

    # Fuzzy match (contains)
    for uname, display in names.items():
        if chat_lower in display.lower():
            return uname

    return None


# ── Message DB helpers ───────────────────────────────────────────────────────

def _get_msg_db_keys():
    """Get all message_N.db key entries."""
    keys = _get_keys()
    return [k for k in sorted(keys.keys()) if re.match(r"^message/message_\d+\.db$", k)]


def _find_msg_table(username):
    """Find which DB contains messages for this username. Returns (db_rel, table_name)."""
    table = _username_to_table(username)
    for db_rel in _get_msg_db_keys():
        conn = _open_db(db_rel)
        if not conn:
            continue
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if exists:
                return db_rel, table
        finally:
            conn.close()
    return None, None


def _find_all_msg_tables(username):
    """Find ALL DBs that contain messages for this username."""
    table = _username_to_table(username)
    results = []
    for db_rel in _get_msg_db_keys():
        conn = _open_db(db_rel)
        if not conn:
            continue
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if exists:
                results.append((db_rel, table))
        finally:
            conn.close()
    return results


def _parse_message(content, local_type, is_group, names):
    """Parse message content, return formatted string."""
    if content is None:
        return ""
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8", errors="replace")
        except Exception:
            return "(binary content)"

    sender = ""
    text = content
    if is_group and ":\n" in content:
        sender, text = content.split(":\n", 1)
        sender = names.get(sender, sender)

    type_label = MSG_TYPE_MAP.get(local_type, f"type={local_type}")
    if local_type != 1:
        text = f"[{type_label}] {text[:200]}" if text else f"[{type_label}]"

    if len(text) > 500:
        text = text[:500] + "..."

    if sender:
        return f"{sender}: {text}"
    return text


# ── MCP Server ───────────────────────────────────────────────────────────────

mcp = FastMCP("wechat", instructions="查询微信消息、联系人等数据。直连加密数据库，实时读取最新消息。")


@mcp.tool()
def get_recent_sessions(limit: int = 20) -> str:
    """获取微信最近会话列表，包含最新消息摘要、未读数、时间等。
    用于了解最近有哪些人/群在聊天。

    Args:
        limit: 返回的会话数量，默认20
    """
    conn = _open_db("session/session.db")
    if not conn:
        return "错误: 无法打开 session.db"

    names = _get_contacts()
    try:
        rows = conn.execute("""
            SELECT username, unread_count, summary, last_timestamp,
                   last_msg_type, last_sender_display_name
            FROM SessionTable
            WHERE last_timestamp > 0
            ORDER BY last_timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()

    results = []
    for username, unread, summary, ts, msg_type, sender_name in rows:
        display = names.get(username, username)
        is_group = "@chatroom" in username
        time_str = datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")

        if isinstance(summary, str) and ":\n" in summary:
            summary = summary.split(":\n", 1)[1]
        summary = (summary or "(no content)")[:80]

        type_label = MSG_TYPE_MAP.get(msg_type, "")

        entry = f"[{time_str}] {display}"
        if is_group:
            entry += " [群]"
        if unread and unread > 0:
            entry += f" ({unread}条未读)"
        entry += f"\n  {type_label}: "
        if is_group and sender_name:
            entry += f"{sender_name}: "
        entry += str(summary)
        results.append(entry)

    return f"最近 {len(results)} 个会话:\n\n" + "\n\n".join(results)


@mcp.tool()
def get_chat_history(chat_name: str, limit: int = 50, start_date: str = "", end_date: str = "") -> str:
    """获取指定聊天的消息记录。支持模糊匹配联系人名/备注名，支持按日期范围筛选。

    Args:
        chat_name: 聊天对象的名字、备注名或wxid，自动模糊匹配
        limit: 返回的消息数量，默认50
        start_date: 起始日期（含），格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM，留空不限
        end_date: 结束日期（含），格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM，留空不限
    """
    username = _resolve_username(chat_name)
    if not username:
        return f"找不到聊天对象: {chat_name}\n提示: 用 get_contacts(query='{chat_name}') 搜索联系人"

    names = _get_contacts()
    display_name = names.get(username, username)
    is_group = "@chatroom" in username

    db_tables = _find_all_msg_tables(username)
    if not db_tables:
        return f"找不到 {display_name} 的消息记录"

    # Build time filter
    conditions = []
    time_params = []
    if start_date:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                ts = int(datetime.strptime(start_date, fmt).timestamp())
                conditions.append("create_time >= ?")
                time_params.append(ts)
                break
            except ValueError:
                continue
        else:
            return f"日期格式错误: {start_date}，请用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM"
    if end_date:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(end_date, fmt)
                if len(end_date) <= 10:
                    dt = dt.replace(hour=23, minute=59, second=59)
                ts = int(dt.timestamp())
                conditions.append("create_time <= ?")
                time_params.append(ts)
                break
            except ValueError:
                continue
        else:
            return f"日期格式错误: {end_date}，请用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM"

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Query all matching databases and merge results
    rows = []
    for db_rel, table_name in db_tables:
        conn = _open_db(db_rel)
        if not conn:
            continue
        try:
            params = time_params + [limit]
            db_rows = conn.execute(f"""
                SELECT local_type, create_time, message_content
                FROM [{table_name}]
                {where}
                ORDER BY create_time DESC
                LIMIT ?
            """, params).fetchall()
            rows.extend(db_rows)
        finally:
            conn.close()

    # Sort by time descending and take top N
    rows.sort(key=lambda x: x[1], reverse=True)
    rows = rows[:limit]

    if not rows:
        msg = f"{display_name} 无消息记录"
        if start_date or end_date:
            msg += f"（{start_date or '...'} ~ {end_date or '...'}）"
        return msg

    lines = []
    for local_type, create_time, content in reversed(rows):
        time_str = datetime.fromtimestamp(create_time).strftime("%m-%d %H:%M")
        text = _parse_message(content, local_type, is_group, names)
        lines.append(f"[{time_str}] {text}")

    header = f"{display_name} 的 {len(lines)} 条消息"
    if start_date or end_date:
        header += f"（{start_date or '...'} ~ {end_date or '...'}）"
    if is_group:
        header += " [群聊]"
    return header + ":\n\n" + "\n".join(lines)


@mcp.tool()
def search_messages(keyword: str, limit: int = 20) -> str:
    """在所有聊天记录中搜索包含关键词的消息。

    Args:
        keyword: 搜索关键词
        limit: 返回的结果数量，默认20
    """
    if not keyword:
        return "请提供搜索关键词"

    names = _get_contacts()
    results = []

    for db_rel in _get_msg_db_keys():
        if len(results) >= limit:
            break

        conn = _open_db(db_rel)
        if not conn:
            continue

        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
            ).fetchall()

            # Build reverse hash -> username mapping
            name2id = {}
            try:
                for (uname,) in conn.execute("SELECT user_name FROM Name2Id"):
                    h = hashlib.md5(uname.encode()).hexdigest()
                    name2id[f"Msg_{h}"] = uname
            except Exception:
                pass

            for (tname,) in tables:
                if len(results) >= limit:
                    break
                username = name2id.get(tname, "")
                is_group = "@chatroom" in username
                display = names.get(username, username) if username else tname

                try:
                    rows = conn.execute(f"""
                        SELECT local_type, create_time, message_content
                        FROM [{tname}]
                        WHERE message_content LIKE ?
                        ORDER BY create_time DESC
                        LIMIT ?
                    """, (f"%{keyword}%", limit - len(results))).fetchall()
                except Exception:
                    continue

                for local_type, ts, content in rows:
                    text = _parse_message(content, local_type, is_group, names)
                    time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                    entry = f"[{time_str}] [{display}] {text}"
                    if len(entry) > 300:
                        entry = entry[:300] + "..."
                    results.append((ts, entry))
        finally:
            conn.close()

    results.sort(key=lambda x: x[0], reverse=True)
    entries = [r[1] for r in results[:limit]]

    if not entries:
        return f'未找到包含 "{keyword}" 的消息'

    return f'搜索 "{keyword}" 找到 {len(entries)} 条结果:\n\n' + "\n\n".join(entries)


@mcp.tool()
def get_contacts(query: str = "", limit: int = 50) -> str:
    """搜索或列出微信联系人。

    Args:
        query: 搜索关键词（匹配昵称、备注名、wxid），留空列出所有
        limit: 返回数量，默认50
    """
    _load_contacts()
    contacts = _contacts_full or []

    if not contacts:
        return "错误: 无法加载联系人数据"

    if query:
        q = query.lower()
        filtered = [
            c for c in contacts
            if q in c["nick_name"].lower()
            or q in c["remark"].lower()
            or q in c["username"].lower()
        ]
    else:
        filtered = contacts

    filtered = filtered[:limit]

    if not filtered:
        return f'未找到匹配 "{query}" 的联系人'

    lines = []
    for c in filtered:
        line = c["username"]
        if c["remark"]:
            line += f"  备注: {c['remark']}"
        if c["nick_name"]:
            line += f"  昵称: {c['nick_name']}"
        lines.append(line)

    header = f"找到 {len(filtered)} 个联系人"
    if query:
        header += f" (搜索: {query})"
    return header + ":\n\n" + "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
