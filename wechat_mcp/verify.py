#!/usr/bin/env python3
"""
Verify that extracted keys can decrypt the corresponding WeChat databases.

Requirements:
    brew install sqlcipher

Usage:
    wechat-mcp-verify
    wechat-mcp-verify --keys path/to/wechat_keys.json
"""

import json
import os
import subprocess
import sys
import glob
import argparse

from wechat_mcp.config import get_keys_path, get_db_base

PAGE_SZ = 4096
SALT_SZ = 16


def find_db_dir():
    db_base = get_db_base()
    pattern = os.path.join(db_base, "*", "db_storage")
    candidates = glob.glob(pattern)
    if len(candidates) >= 1:
        return candidates[0]
    if os.path.isdir(db_base) and os.path.basename(db_base) == "db_storage":
        return db_base
    return None


def find_sqlcipher():
    brew_path = "/opt/homebrew/opt/sqlcipher/bin/sqlcipher"
    if os.path.isfile(brew_path):
        return brew_path
    for p in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(p, "sqlcipher")
        if os.path.isfile(candidate):
            return candidate
    return None


def verify_key(sqlcipher_bin, db_path, key_hex):
    if not os.path.isfile(db_path):
        return False, "file not found"

    sz = os.path.getsize(db_path)
    if sz < PAGE_SZ:
        return False, f"file too small ({sz} bytes)"

    with open(db_path, "rb") as f:
        salt = f.read(SALT_SZ).hex()

    sql_commands = f"""PRAGMA key = "x'{key_hex}'";
PRAGMA cipher_page_size = 4096;
SELECT count(*) FROM sqlite_master;
"""

    try:
        result = subprocess.run(
            [sqlcipher_bin, db_path],
            input=sql_commands,
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0 and output and "Error" not in stderr:
            lines = output.strip().split("\n")
            last_line = lines[-1].strip()
            if last_line.isdigit():
                table_count = int(last_line)
                return True, f"OK ({table_count} tables, salt={salt})"

        if "file is not a database" in stderr or "not a database" in output:
            return False, f"wrong key (salt={salt})"

        return False, f"unknown error: {stderr or output}"

    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Verify WeChat database keys")
    parser.add_argument(
        "--keys", default=None,
        help="Path to wechat_keys.json (auto-detected if not specified)",
    )
    args = parser.parse_args()

    keys_file = args.keys or get_keys_path()
    if not os.path.isfile(keys_file):
        print(f"[-] Key file not found: {keys_file}")
        sys.exit(1)

    with open(keys_file, "r") as f:
        data = json.load(f)

    sqlcipher_bin = find_sqlcipher()
    if not sqlcipher_bin:
        print("[-] sqlcipher not found. Install it with: brew install sqlcipher")
        sys.exit(1)
    print(f"[*] Using sqlcipher: {sqlcipher_bin}")

    db_dir = find_db_dir()
    if not db_dir:
        print(f"[-] Could not find db_storage directory")
        sys.exit(1)
    print(f"[*] DB storage: {db_dir}")

    entries = {k: v for k, v in data.items() if not k.startswith("__")}
    print(f"[*] Verifying {len(entries)} keys...\n")

    passed = 0
    failed = 0

    for db_rel_path, key_hex in sorted(entries.items()):
        db_abs_path = os.path.join(db_dir, db_rel_path)
        success, detail = verify_key(sqlcipher_bin, db_abs_path, key_hex)

        if success:
            print(f"  ok   {db_rel_path}: {detail}")
            passed += 1
        else:
            print(f"  FAIL {db_rel_path}: {detail}")
            failed += 1

    print(f"\n[*] Results: {passed} passed, {failed} failed, {passed + failed} total")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
