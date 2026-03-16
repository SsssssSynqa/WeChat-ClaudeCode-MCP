#!/usr/bin/env python3
"""
Extract ALL WeChat database keys by scanning process memory (macOS).

Requirements:
    - lldb (brew install llvm)
    - SIP disabled (csrutil disable)

Usage:
    PYTHONPATH=$(lldb -P) wechat-mcp-keygen
    PYTHONPATH=$(lldb -P) python3 -m wechat_mcp.keygen
"""

import sys
import os
import re
import glob
import json
import struct
import hashlib
import hmac as hmac_mod

import lldb

from wechat_mcp.config import get_db_base, get_default_output_dir

PAGE_SZ = 4096
KEY_SZ = 32
SALT_SZ = 16

# Regex to match x'<hex>' patterns in memory (96 hex chars = 64 key + 32 salt)
HEX_PATTERN = re.compile(rb"x'([0-9a-fA-F]{64,192})'")


def find_db_dir():
    db_base = get_db_base()
    pattern = os.path.join(db_base, "*", "db_storage")
    candidates = glob.glob(pattern)
    if candidates:
        return candidates[0]
    return None


def collect_db_files(db_dir):
    """Collect all .db files with their first page and salt."""
    db_files = []
    salt_to_dbs = {}

    for root, dirs, files in os.walk(db_dir):
        for f in files:
            if not f.endswith(".db"):
                continue
            if f.endswith("-wal") or f.endswith("-shm"):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, db_dir)
            sz = os.path.getsize(path)
            if sz < PAGE_SZ:
                continue
            with open(path, "rb") as fh:
                page1 = fh.read(PAGE_SZ)
            salt = page1[:SALT_SZ].hex()
            db_files.append((rel, path, sz, salt, page1))
            salt_to_dbs.setdefault(salt, []).append(rel)

    return db_files, salt_to_dbs


def verify_key_for_db(enc_key_bytes, db_page1):
    """Verify enc_key can decrypt this DB's page 1 using HMAC-SHA512."""
    salt = db_page1[:SALT_SZ]
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key_bytes, mac_salt, 2, dklen=KEY_SZ)

    hmac_data = db_page1[SALT_SZ : PAGE_SZ - 80 + 16]
    stored_hmac = db_page1[PAGE_SZ - 64 : PAGE_SZ]

    h = hmac_mod.new(mac_key, hmac_data, hashlib.sha512)
    h.update(struct.pack("<I", 1))
    return h.digest() == stored_hmac


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract WeChat encryption keys (macOS)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output key file path (default: ~/.wechat-mcp/wechat_keys.json)")
    args = parser.parse_args()

    output_file = args.output
    if not output_file:
        # Default: ~/.wechat-mcp/wechat_keys.json, but also write to CWD if it exists there
        cwd_keys = os.path.join(os.getcwd(), "wechat_keys.json")
        if os.path.isfile(cwd_keys):
            output_file = cwd_keys
        else:
            output_file = os.path.join(get_default_output_dir(), "wechat_keys.json")

    print("=" * 60)
    print("  WeChat Memory Scanner - Extract ALL Database Keys")
    print("=" * 60)

    # 1. Collect DB files
    db_dir = find_db_dir()
    if not db_dir:
        print(f"[-] Could not find db_storage directory")
        sys.exit(1)

    db_files, salt_to_dbs = collect_db_files(db_dir)
    print(f"\n[*] Found {len(db_files)} databases, {len(salt_to_dbs)} unique salts")
    for salt_hex, dbs in sorted(salt_to_dbs.items()):
        print(f"    salt {salt_hex}: {', '.join(dbs)}")

    # 2. Attach to WeChat via lldb
    print("\n[*] Attaching to WeChat...")
    debugger = lldb.SBDebugger.Create()
    debugger.SetAsync(False)
    target = debugger.CreateTarget("")
    error = lldb.SBError()

    process = target.AttachToProcessWithName(
        debugger.GetListener(), "WeChat", False, error
    )
    if not error.Success():
        print(f"[-] Error attaching: {error.GetCString()}")
        print("[!] Make sure WeChat is running and SIP is disabled.")
        sys.exit(1)

    pid = process.GetProcessID()
    print(f"[+] Attached to WeChat (PID: {pid})")

    # 3. Enumerate and scan memory regions
    key_map = {}
    remaining_salts = set(salt_to_dbs.keys())
    all_hex_matches = 0
    total_scanned = 0

    region_info = lldb.SBMemoryRegionInfo()
    addr = 0

    regions = []
    while True:
        err = process.GetMemoryRegionInfo(addr, region_info)
        if err.Fail():
            break
        base = region_info.GetRegionBase()
        end = region_info.GetRegionEnd()
        if end <= base:
            break
        if region_info.IsReadable() and not region_info.IsExecutable():
            size = end - base
            if 0 < size < 500 * 1024 * 1024:
                regions.append((base, size))
        addr = end
        if addr == 0:
            break

    total_bytes = sum(s for _, s in regions)
    print(f"[*] Scanning {len(regions)} memory regions ({total_bytes / 1024 / 1024:.0f} MB)")

    for reg_idx, (base, size) in enumerate(regions):
        chunk_size = 8 * 1024 * 1024
        offset = 0

        while offset < size:
            read_size = min(chunk_size, size - offset)
            read_addr = base + offset
            data = process.ReadMemory(read_addr, read_size, error)
            offset += read_size
            total_scanned += read_size

            if not error.Success() or not data:
                continue

            for m in HEX_PATTERN.finditer(data):
                hex_str = m.group(1).decode()
                all_hex_matches += 1
                hex_len = len(hex_str)

                if hex_len == 96:
                    enc_key_hex = hex_str[:64]
                    salt_hex = hex_str[64:]
                elif hex_len == 64:
                    enc_key_hex = hex_str
                    salt_hex = None
                elif hex_len > 96 and hex_len % 2 == 0:
                    enc_key_hex = hex_str[:64]
                    salt_hex = hex_str[-32:]
                else:
                    continue

                if salt_hex and salt_hex in remaining_salts:
                    enc_key = bytes.fromhex(enc_key_hex)
                    for rel, path, sz, s, page1 in db_files:
                        if s == salt_hex:
                            if verify_key_for_db(enc_key, page1):
                                key_map[salt_hex] = enc_key_hex
                                remaining_salts.discard(salt_hex)
                                dbs = salt_to_dbs[salt_hex]
                                print(f"\n  [FOUND] salt={salt_hex}")
                                print(f"    key={enc_key_hex}")
                                print(f"    databases: {', '.join(dbs)}")
                            break

                elif salt_hex is None and remaining_salts:
                    enc_key = bytes.fromhex(enc_key_hex)
                    for rel, path, sz, salt_hex_db, page1 in db_files:
                        if salt_hex_db in remaining_salts:
                            if verify_key_for_db(enc_key, page1):
                                key_map[salt_hex_db] = enc_key_hex
                                remaining_salts.discard(salt_hex_db)
                                dbs = salt_to_dbs[salt_hex_db]
                                print(f"\n  [FOUND] salt={salt_hex_db} (key-only match)")
                                print(f"    key={enc_key_hex}")
                                print(f"    databases: {', '.join(dbs)}")
                                break

        if (reg_idx + 1) % 50 == 0 or reg_idx == len(regions) - 1:
            progress = total_scanned / total_bytes * 100 if total_bytes else 100
            print(
                f"  [{progress:.1f}%] {len(key_map)}/{len(salt_to_dbs)} keys found, "
                f"{all_hex_matches} hex patterns, "
                f"{total_scanned / 1024 / 1024:.0f}/{total_bytes / 1024 / 1024:.0f} MB"
            )

        if not remaining_salts:
            print(f"\n[+] All keys found!")
            break

    # 4. Cross-verify
    missing_salts = set(salt_to_dbs.keys()) - set(key_map.keys())
    if missing_salts and key_map:
        print(f"\n[*] {len(missing_salts)} salts remaining, trying cross-verification...")
        for salt_hex in list(missing_salts):
            for rel, path, sz, s, page1 in db_files:
                if s == salt_hex:
                    for known_salt, known_key_hex in key_map.items():
                        enc_key = bytes.fromhex(known_key_hex)
                        if verify_key_for_db(enc_key, page1):
                            key_map[salt_hex] = known_key_hex
                            dbs = salt_to_dbs[salt_hex]
                            print(f"  [CROSS] salt={salt_hex} uses same key as {known_salt}")
                            print(f"    databases: {', '.join(dbs)}")
                            missing_salts.discard(salt_hex)
                    break

    # 5. Detach
    process.Detach()
    print("\n[*] Detached from WeChat.")

    # 6. Save results
    print(f"\n{'=' * 60}")
    print(f"Results: {len(key_map)}/{len(salt_to_dbs)} keys found")

    result = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, "r") as f:
                result = json.load(f)
        except Exception:
            pass

    for rel, path, sz, salt_hex, page1 in db_files:
        if salt_hex in key_map:
            result[rel] = key_map[salt_hex]
            print(f"  ✅ {rel} ({sz / 1024 / 1024:.1f} MB)")
        else:
            print(f"  ❌ {rel} (salt={salt_hex})")

    result["__salts__"] = sorted(set(result.get("__salts__", [])) | set(key_map.keys()))

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n[*] Keys saved to {output_file}")

    missing = [rel for rel, _, _, s, _ in db_files if s not in key_map]
    if missing:
        print(f"\n[!] Missing keys for: {', '.join(missing)}")


if __name__ == "__main__":
    main()
