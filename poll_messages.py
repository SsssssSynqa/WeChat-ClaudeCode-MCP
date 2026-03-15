#!/usr/bin/env python3
"""
Poll for new WeChat messages in a specific conversation.

Monitors a chat for new messages by timestamp, prints them when detected.
Useful for real-time chat monitoring with Claude Code.

Usage:
    python3 poll_messages.py <chat_username> [interval_seconds]

Examples:
    python3 poll_messages.py wxid_xxx            # poll every 8 seconds
    python3 poll_messages.py wxid_xxx 5          # poll every 5 seconds
    python3 poll_messages.py 12345@chatroom 10   # poll a group chat
"""

import sqlite3
import hashlib
import os
import sys
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DECRYPTED_DIR = os.path.join(SCRIPT_DIR, "decrypted")
MSG_DB = os.path.join(DECRYPTED_DIR, "message", "message_0.db")
CONTACT_DB = os.path.join(DECRYPTED_DIR, "contact", "contact.db")


def load_contacts():
    contacts = {}
    if not os.path.isfile(CONTACT_DB):
        return contacts
    conn = sqlite3.connect(CONTACT_DB)
    try:
        for username, remark, nick_name in conn.execute(
            "SELECT username, remark, nick_name FROM contact"
        ):
            contacts[username] = remark or nick_name or username
    finally:
        conn.close()
    return contacts


def username_to_table(username):
    h = hashlib.md5(username.encode()).hexdigest()
    return f"Msg_{h}"


def get_latest_timestamp(chat_username):
    table = username_to_table(chat_username)
    conn = sqlite3.connect(MSG_DB)
    try:
        rows = conn.execute(
            f"SELECT create_time FROM [{table}] ORDER BY create_time DESC LIMIT 1"
        ).fetchall()
        return rows[0][0] if rows else 0
    except Exception:
        return 0
    finally:
        conn.close()


def get_new_messages(chat_username, baseline_ts, contacts):
    table = username_to_table(chat_username)
    is_group = "@chatroom" in chat_username
    conn = sqlite3.connect(MSG_DB)
    try:
        rows = conn.execute(
            f"SELECT local_type, create_time, message_content FROM [{table}] "
            f"WHERE create_time > ? ORDER BY create_time ASC",
            (baseline_ts,),
        ).fetchall()
    except Exception:
        return []
    finally:
        conn.close()

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
        print("Usage: python3 poll_messages.py <chat_username> [interval_seconds]")
        sys.exit(1)

    chat_username = sys.argv[1]
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    if not os.path.isfile(MSG_DB):
        print(f"[-] Message database not found: {MSG_DB}", file=sys.stderr)
        print("[-] Run decrypt_db.py first.", file=sys.stderr)
        sys.exit(1)

    contacts = load_contacts()
    baseline = get_latest_timestamp(chat_username)
    print(f"Polling {chat_username} every {interval}s, baseline_ts={baseline}", file=sys.stderr)

    while True:
        time.sleep(interval)
        messages = get_new_messages(chat_username, baseline, contacts)
        if messages:
            for m in messages:
                sender = m["sender"] or "me"
                print(f'[{m["time_str"]}] {sender}: {m["text"]}')
            print("NEW_MESSAGE=YES")
            sys.exit(0)


if __name__ == "__main__":
    main()
