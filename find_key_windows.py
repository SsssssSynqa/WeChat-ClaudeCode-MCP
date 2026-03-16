#!/usr/bin/env python3
"""
Extract encryption keys from Windows WeChat 4.x (Weixin.exe) process memory.

How it works:
    WCDB (WeChat's SQLCipher wrapper) stores encryption keys in memory as
    ASCII strings in the format:  x'<64-hex-key><32-hex-salt>'
    We read the 16-byte salt from each database file header, search for
    that salt string in the Weixin.exe process memory, then read backwards
    to extract the corresponding 64-char hex key.

Requirements:
    pip install pymem psutil

Usage:
    Run as Administrator on the same Windows machine where WeChat is logged in.
    python find_key_windows.py [--db-dir PATH] [--output PATH]
"""
import argparse
import json
import os
import sys

try:
    import pymem
    import pymem.pattern
except ImportError:
    print("pip install pymem psutil")
    sys.exit(1)


def find_db_storage(base_dirs=None):
    """Auto-detect the db_storage directory."""
    if base_dirs is None:
        base_dirs = [
            os.path.expanduser(r"~\Documents\xwechat_files"),
            r"C:\Mac\Home\Documents\xwechat_files",  # Parallels shared folder
        ]
    for base in base_dirs:
        if not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            candidate = os.path.join(base, entry, "db_storage")
            if os.path.isdir(candidate):
                return candidate
    return None


def get_db_salts(db_storage):
    """Read salt (first 16 bytes) from each encrypted database."""
    salts = {}
    for subdir in os.listdir(db_storage):
        subpath = os.path.join(db_storage, subdir)
        if not os.path.isdir(subpath):
            continue
        for fname in os.listdir(subpath):
            if not fname.endswith(".db"):
                continue
            fpath = os.path.join(subpath, fname)
            if os.path.getsize(fpath) < 100:
                continue
            with open(fpath, "rb") as f:
                raw_salt = f.read(16)
            salt_hex = raw_salt.hex()
            db_rel = f"{subdir}/{fname}"
            salts[salt_hex] = db_rel
    return salts


def extract_keys(process_name="Weixin.exe"):
    """Scan process memory for encryption keys."""
    db_storage = find_db_storage()
    if not db_storage:
        print("[-] Could not find WeChat db_storage directory")
        return None

    print(f"[*] db_storage: {db_storage}")

    salts = get_db_salts(db_storage)
    print(f"[*] Found {len(salts)} encrypted databases\n")

    try:
        pm = pymem.Pymem(process_name)
    except pymem.exception.ProcessNotFound:
        # Try alternative process name
        try:
            pm = pymem.Pymem("WeChat.exe")
            process_name = "WeChat.exe"
        except pymem.exception.ProcessNotFound:
            print(f"[-] Neither Weixin.exe nor WeChat.exe is running")
            return None

    print(f"[*] Attached to {process_name} PID {pm.process_id}")

    found_keys = {}

    for salt_hex, db_rel in salts.items():
        # Search for salt as ASCII hex string in process memory
        salt_bytes = salt_hex.encode("ascii")
        try:
            addrs = pymem.pattern.pattern_scan_all(
                pm.process_handle, salt_bytes, return_multiple=True
            )
        except Exception as e:
            print(f"  [{db_rel}] scan error: {e}")
            continue

        for addr in addrs:
            try:
                # Key format: x'<64-hex-key><32-hex-salt>'
                # Read from addr - 66 (2 for "x'" + 64 for key hex)
                start = addr - 66
                data = pm.read_bytes(start, 99)  # 2 + 64 + 32 + 1
                text = data.decode("ascii", errors="replace")

                if text[:2] == "x'" and text[98:99] == "'":
                    inner = text[2:98]
                    try:
                        bytes.fromhex(inner)
                    except ValueError:
                        continue

                    key_hex = inner[:64]
                    found_salt = inner[64:]

                    if found_salt == salt_hex:
                        found_keys[db_rel] = key_hex
                        print(f"  [+] {db_rel}: {key_hex}")
                        break
            except Exception:
                continue

    pm.close_process()
    return found_keys, db_storage


def main():
    parser = argparse.ArgumentParser(description="Extract WeChat encryption keys from memory")
    parser.add_argument("--output", "-o", default="wechat_keys_win.json",
                        help="Output key file path (default: wechat_keys_win.json)")
    parser.add_argument("--process", "-p", default="Weixin.exe",
                        help="Process name (default: Weixin.exe)")
    args = parser.parse_args()

    result = extract_keys(args.process)
    if not result:
        sys.exit(1)

    found_keys, db_storage = result

    if found_keys:
        print(f"\n[+] Extracted {len(found_keys)}/{len(get_db_salts(db_storage))} keys")
        with open(args.output, "w") as f:
            json.dump(found_keys, f, indent=2)
        print(f"[+] Saved to {args.output}")
    else:
        print("\n[-] No keys found. Make sure:")
        print("  1. WeChat is logged in and running")
        print("  2. Script is running as Administrator")
        sys.exit(1)


if __name__ == "__main__":
    main()
