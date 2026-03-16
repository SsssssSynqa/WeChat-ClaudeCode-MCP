#!/usr/bin/env python3
"""
Export WeChat chat messages from decrypted databases.

Usage:
    wechat-mcp-export                          # list all conversations
    wechat-mcp-export -c wxid_xxx              # export a specific chat
    wechat-mcp-export -c 12345@chatroom        # export a group chat
    wechat-mcp-export --all                    # export all chats
    wechat-mcp-export -c wxid_xxx -n 50        # last 50 messages
    wechat-mcp-export -s "keyword"             # search keyword
"""

import sqlite3
import os
import re
import sys
import hashlib
import argparse
import glob
from datetime import datetime

MSG_TYPE_MAP = {
    1: "text",
    3: "image",
    34: "voice",
    42: "card",
    43: "video",
    47: "emoji",
    48: "location",
    49: "link/file",
    10000: "system",
    10002: "revoke",
}


def load_contacts(decrypted_dir):
    contact_db = os.path.join(decrypted_dir, "contact", "contact.db")
    contacts = {}
    if not os.path.isfile(contact_db):
        return contacts
    conn = sqlite3.connect(contact_db)
    try:
        for username, remark, nick_name in conn.execute(
            "SELECT username, remark, nick_name FROM contact"
        ):
            name = remark or nick_name or username
            if name:
                contacts[username] = name
        for username, remark, nick_name in conn.execute(
            "SELECT username, remark, nick_name FROM stranger"
        ):
            if username not in contacts:
                name = remark or nick_name or username
                if name:
                    contacts[username] = name
    finally:
        conn.close()
    return contacts


def resolve_username(chat_name, contacts):
    if chat_name in contacts or chat_name.startswith("wxid_") or "@chatroom" in chat_name:
        return chat_name
    chat_lower = chat_name.lower()
    for uname, display in contacts.items():
        if chat_lower == display.lower():
            return uname
    for uname, display in contacts.items():
        if chat_lower in display.lower():
            return uname
    return None


def get_all_msg_dbs(decrypted_dir):
    msg_dir = os.path.join(decrypted_dir, "message")
    if not os.path.isdir(msg_dir):
        return []
    dbs = []
    for f in sorted(os.listdir(msg_dir)):
        if re.match(r"^message_\d+\.db$", f):
            dbs.append(os.path.join(msg_dir, f))
    return dbs


def get_session_db_path(decrypted_dir):
    return os.path.join(decrypted_dir, "session", "session.db")


def username_to_table(username):
    h = hashlib.md5(username.encode()).hexdigest()
    return f"Msg_{h}"


def find_msg_db_for_username(msg_dbs, username):
    table = username_to_table(username)
    for db_path in msg_dbs:
        conn = sqlite3.connect(db_path)
        try:
            exists = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()[0]
            if exists:
                return db_path
        finally:
            conn.close()
    return None


def collect_all_usernames(msg_dbs):
    username_to_db = {}
    for db_path in msg_dbs:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT user_name FROM Name2Id WHERE user_name != ''"
            ).fetchall()
            for (username,) in rows:
                if username not in username_to_db:
                    username_to_db[username] = db_path
        finally:
            conn.close()
    return username_to_db


def format_message(row, is_group, contacts):
    local_id, local_type, create_time, sender_id, content, source = row
    ts = datetime.fromtimestamp(create_time).strftime("%Y-%m-%d %H:%M:%S") if create_time else "?"
    type_name = MSG_TYPE_MAP.get(local_type, f"type:{local_type}")

    sender = ""
    body = content or ""
    if isinstance(body, bytes):
        try:
            body = body.decode("utf-8", errors="replace")
        except Exception:
            body = "(binary content)"

    if is_group and body and ":\n" in body:
        parts = body.split(":\n", 1)
        raw_sender = parts[0]
        body = parts[1]
        sender = contacts.get(raw_sender, raw_sender)

    if local_type != 1:
        body = f"[{type_name}] {body[:100]}" if body else f"[{type_name}]"

    if sender:
        return f"[{ts}] {sender}: {body}"
    return f"[{ts}] {body}"


def list_conversations(msg_dbs, session_db_path, contacts):
    sessions = {}
    if os.path.isfile(session_db_path):
        conn = sqlite3.connect(session_db_path)
        try:
            rows = conn.execute(
                "SELECT username, type, summary, last_sender_display_name, "
                "last_timestamp FROM SessionTable ORDER BY sort_timestamp DESC"
            ).fetchall()
            for username, stype, summary, sender, ts in rows:
                sessions[username] = {
                    "type": "group" if "@chatroom" in username else "private",
                    "summary": (summary or "")[:60],
                    "sender": sender or "",
                    "time": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "",
                }
        finally:
            conn.close()

    username_to_db = collect_all_usernames(msg_dbs)
    all_tables = {}
    for db_path in msg_dbs:
        conn = sqlite3.connect(db_path)
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
                ).fetchall()
            }
            all_tables[db_path] = tables
        finally:
            conn.close()

    results = []
    for username, db_path in username_to_db.items():
        table = username_to_table(username)
        has_msgs = table in all_tables.get(db_path, set())
        info = sessions.get(username, {})
        display_name = contacts.get(username, "")
        results.append({
            "username": username,
            "display_name": display_name,
            "db": os.path.basename(db_path),
            "has_msgs": has_msgs,
            **info,
        })

    results.sort(key=lambda x: x.get("time", ""), reverse=True)
    return results


def export_chat(msg_dbs, username, contacts, limit=None):
    table = username_to_table(username)
    is_group = "@chatroom" in username
    db_path = find_msg_db_for_username(msg_dbs, username)
    if not db_path:
        return None, f"No message table found for {username}"

    conn = sqlite3.connect(db_path)
    try:
        total = conn.execute(f"SELECT count(*) FROM [{table}]").fetchone()[0]
        query = (
            f"SELECT local_id, local_type, create_time, real_sender_id, "
            f"message_content, source FROM [{table}] ORDER BY create_time ASC"
        )
        if limit:
            query = (
                f"SELECT * FROM (SELECT local_id, local_type, create_time, "
                f"real_sender_id, message_content, source FROM [{table}] "
                f"ORDER BY create_time DESC LIMIT {limit}) ORDER BY create_time ASC"
            )
        rows = conn.execute(query).fetchall()
        lines = [format_message(r, is_group, contacts) for r in rows]
        display_name = contacts.get(username, username)
        return lines, f"{display_name} | total: {total}, showing: {len(lines)} | db: {os.path.basename(db_path)}"
    finally:
        conn.close()


def safe_filename(display_name, username):
    name = display_name or username
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    name = name.strip('. ')
    if not name:
        name = username.replace('@', '_at_')
    if len(name) > 80:
        name = name[:80]
    return name


def export_to_file(msg_dbs, username, output_dir, contacts, limit=None):
    lines, info = export_chat(msg_dbs, username, contacts, limit)
    if lines is None:
        return False, info
    os.makedirs(output_dir, exist_ok=True)
    display_name = contacts.get(username, "")
    fname = safe_filename(display_name, username)
    output_path = os.path.join(output_dir, f"{fname}.txt")
    if os.path.exists(output_path):
        output_path = os.path.join(output_dir, f"{fname}_{username.replace('@', '_at_')}.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Chat: {display_name or username} ({username})\n")
        f.write(f"# {info}\n")
        f.write(f"# Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("\n".join(lines))
        f.write("\n")
    return True, f"{os.path.basename(output_path)} | {info}"


def main():
    parser = argparse.ArgumentParser(description="Export WeChat chat messages")
    parser.add_argument("-d", "--dir", default="decrypted",
                        help="Decrypted database directory (default: decrypted)")
    parser.add_argument("-c", "--chat", help="Username or chatroom ID to export")
    parser.add_argument("--all", action="store_true", help="Export all conversations")
    parser.add_argument("-n", "--limit", type=int, default=None, help="Number of recent messages")
    parser.add_argument("-o", "--output", default="exported", help="Output directory (default: exported)")
    parser.add_argument("-s", "--search", help="Search keyword across all conversations")
    args = parser.parse_args()

    msg_dbs = get_all_msg_dbs(args.dir)
    if not msg_dbs:
        print(f"[-] No message databases found in {args.dir}/message/")
        print(f"    Run 'wechat-mcp-decrypt' first.")
        sys.exit(1)

    print(f"[*] Loaded {len(msg_dbs)} message databases")
    session_db = get_session_db_path(args.dir)
    contacts = load_contacts(args.dir)
    print(f"[*] Loaded {len(contacts)} contacts")

    if args.search:
        print(f"[*] Searching for '{args.search}'...\n")
        username_to_db = collect_all_usernames(msg_dbs)
        found = 0
        for username, db_path in username_to_db.items():
            table = username_to_table(username)
            is_group = "@chatroom" in username
            conn = sqlite3.connect(db_path)
            try:
                exists = conn.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()[0]
                if not exists:
                    continue
                rows = conn.execute(
                    f"SELECT local_id, local_type, create_time, real_sender_id, "
                    f"message_content, source FROM [{table}] "
                    f"WHERE message_content LIKE ? ORDER BY create_time DESC LIMIT 10",
                    (f"%{args.search}%",),
                ).fetchall()
                if rows:
                    display = contacts.get(username, username)
                    print(f"-- {display} ({username}) --")
                    for r in rows:
                        print(f"  {format_message(r, is_group, contacts)}")
                    print()
                    found += len(rows)
            finally:
                conn.close()
        print(f"[*] Found {found} messages matching '{args.search}'")

    elif args.chat:
        username = resolve_username(args.chat, contacts)
        if not username:
            print(f"[-] Could not find chat: {args.chat}")
            sys.exit(1)
        if username != args.chat:
            display = contacts.get(username, username)
            print(f"[*] Matched '{args.chat}' -> {display} ({username})")
        lines, info = export_chat(msg_dbs, username, contacts, args.limit)
        if lines is None:
            print(f"[-] {info}")
            sys.exit(1)
        print(f"[*] {info}\n")
        for line in lines:
            print(line)
        success, result_info = export_to_file(msg_dbs, username, args.output, contacts, args.limit)
        print(f"\n[*] Saved: {result_info}")

    elif args.all:
        convos = list_conversations(msg_dbs, session_db, contacts)
        os.makedirs(args.output, exist_ok=True)
        exported = 0
        for c in convos:
            if not c["has_msgs"]:
                continue
            success, info = export_to_file(msg_dbs, c["username"], args.output, contacts, args.limit)
            if success:
                print(f"  ok {info}")
                exported += 1
        print(f"\n[*] Exported {exported} conversations to {args.output}/")

    else:
        convos = list_conversations(msg_dbs, session_db, contacts)
        active = [c for c in convos if c.get("time") or c["has_msgs"]]
        print(f"[*] Found {len(active)} active conversations\n")
        print(f"{'Display Name':<20} {'Username':<35} {'DB':<15} {'Time':<18} {'Last Message'}")
        print("-" * 120)
        for c in active:
            if not c.get("time"):
                continue
            marker = "DM" if c.get("type") == "private" else "GC"
            display = c.get("display_name", "")[:18] or ""
            summary = c.get("summary", "")[:40]
            time_str = c.get("time", "")
            db_name = c.get("db", "")
            print(f"{marker} {display:<18} {c['username']:<35} {db_name:<15} {time_str:<18} {summary}")

        print(f"\n[*] To export a chat: wechat-mcp-export -c <username>")
        print(f"[*] To export all:    wechat-mcp-export --all")
        print(f"[*] To search:        wechat-mcp-export -s <keyword>")


if __name__ == "__main__":
    main()
