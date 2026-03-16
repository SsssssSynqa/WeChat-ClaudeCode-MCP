#!/usr/bin/env python3
"""
Poll for new WeChat messages in a specific conversation.

Directly queries the encrypted WeChat database via sqlcipher3.

Usage:
    wechat-mcp-poll <chat_username> [interval_seconds]
    wechat-mcp-poll wxid_xxx 5
    wechat-mcp-poll 12345@chatroom 10
"""

import sqlcipher3
import hashlib
import json
import os
import sys
import time
from datetime import datetime

from wechat_mcp.config import get_keys_path, get_db_base
import glob as _glob


def find_db_storage():
    db_base = get_db_base()
    pattern = os.path.join(db_base, "*", "db_storage")
    candidates = _glob.glob(pattern)
    return candidates[0] if candidates else None


def open_encrypted_db(db_path, key_hex):
    conn = sqlcipher3.connect(db_path)
    conn.execute(f"PRAGMA key = \"x'{key_hex}'\"")
    conn.execute("PRAGMA cipher_page_size = 4096")
    return conn


def load_contacts_from_encrypted(db_storage, keys):
    """Load contacts directly from encrypted contact.db."""
    contacts = {}
    key = keys.get("contact/contact.db")
    if not key:
        return contacts
    db_path = os.path.join(db_storage, "contact", "contact.db")
    if not os.path.isfile(db_path):
        return contacts
    try:
        conn = open_encrypted_db(db_path, key)
        for username, remark, nick_name in conn.execute(
            "SELECT username, remark, nick_name FROM contact"
        ):
            contacts[username] = remark or nick_name or username
        conn.close()
    except Exception:
        pass
    return contacts


def username_to_table(username):
    h = hashlib.md5(username.encode()).hexdigest()
    return f"Msg_{h}"


def get_latest_timestamp(conn, chat_username):
    table = username_to_table(chat_username)
    try:
        rows = conn.execute(
            f"SELECT create_time FROM [{table}] ORDER BY create_time DESC LIMIT 1"
        ).fetchall()
        return rows[0][0] if rows else 0
    except Exception:
        return 0


def get_new_messages(conn, chat_username, baseline_ts, contacts):
    table = username_to_table(chat_username)
    is_group = "@chatroom" in chat_username
    try:
        rows = conn.execute(
            f"SELECT local_type, create_time, message_content FROM [{table}] "
            f"WHERE create_time > ? ORDER BY create_time ASC",
            (baseline_ts,),
        ).fetchall()
    except Exception:
        return []

    messages = []
    for local_type, ts, content in rows:
        if isinstance(content, bytes):
            try:
                content = content.decode("utf-8", errors="replace")
            except Exception:
                content = ""

        sender = ""
        text = content or ""
        if is_group and ":\n" in text:
            sender, text = text.split(":\n", 1)
            sender = contacts.get(sender, sender)
        if not sender and not is_group:
            sender = contacts.get(chat_username, chat_username) if local_type != 10000 else ""

        time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        messages.append({
            "sender": sender,
            "text": text,
            "timestamp": ts,
            "time_str": time_str,
            "type": local_type,
        })

    return messages


def main():
    if len(sys.argv) < 2:
        print("Usage: wechat-mcp-poll <chat_username> [interval_seconds]")
        sys.exit(1)

    chat_username = sys.argv[1]
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    keys_file = get_keys_path()
    if not os.path.isfile(keys_file):
        print(f"[-] Key file not found: {keys_file}", file=sys.stderr)
        sys.exit(1)

    with open(keys_file) as f:
        keys = json.load(f)

    msg_key = keys.get("message/message_0.db")
    if not msg_key:
        print("[-] No key found for message/message_0.db", file=sys.stderr)
        sys.exit(1)

    db_storage = find_db_storage()
    if not db_storage:
        print(f"[-] Could not find db_storage", file=sys.stderr)
        sys.exit(1)

    enc_msg_db = os.path.join(db_storage, "message", "message_0.db")

    contacts = load_contacts_from_encrypted(db_storage, keys)

    conn = open_encrypted_db(enc_msg_db, msg_key)
    baseline = get_latest_timestamp(conn, chat_username)
    conn.close()

    print(f"Polling {chat_username} every {interval}s, baseline_ts={baseline}", file=sys.stderr)

    while True:
        time.sleep(interval)
        try:
            conn = open_encrypted_db(enc_msg_db, msg_key)
            messages = get_new_messages(conn, chat_username, baseline, contacts)
            conn.close()
        except Exception as e:
            print(f"[-] Query error: {e}", file=sys.stderr)
            continue

        if messages:
            for m in messages:
                sender = m["sender"] or "me"
                print(f'[{m["time_str"]}] {sender}: {m["text"]}')
            print("NEW_MESSAGE=YES")
            sys.exit(0)


if __name__ == "__main__":
    main()
