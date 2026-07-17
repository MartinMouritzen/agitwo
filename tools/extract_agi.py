#!/usr/bin/env python3
"""Extract all displayable message text from a Sierra AGI v2 game.

Parses LOGDIR to locate every LOGIC resource inside VOL.n files, decodes the
message section of each logic (XOR-decrypted with the repeating key
"Avis Durgan"), and emits a JSON manifest.

Format reference: ScummVM engines/agi/loader_v2.cpp, logic.cpp, global.cpp.

Usage:
    python3 extract_agi.py <game_dir> [-o output.json] [--game-id pq1]
"""

import argparse
import json
import os
import struct
import sys

CRYPT_KEY = b"Avis Durgan"  # 11 bytes, repeating XOR key
EMPTY_OFFSET = 0xFFFFF      # AGI _EMPTY: directory entry marks no resource


def find_file(game_dir, name):
    """Case-insensitive lookup of a file in game_dir."""
    for entry in os.listdir(game_dir):
        if entry.upper() == name.upper():
            return os.path.join(game_dir, entry)
    return None


def read_logdir(game_dir):
    """Parse LOGDIR: 3-byte entries -> list of (logic_nr, volume, offset)."""
    path = find_file(game_dir, "LOGDIR")
    if path is None:
        raise FileNotFoundError("LOGDIR not found in %s" % game_dir)
    data = open(path, "rb").read()
    entries = []
    for i in range(0, len(data) - 2, 3):
        volume = data[i] >> 4
        offset = ((data[i] << 16) | (data[i + 1] << 8) | data[i + 2]) & EMPTY_OFFSET
        if offset == EMPTY_OFFSET:
            continue
        entries.append((i // 3, volume, offset))
    return entries


def read_volume_resource(game_dir, volume, offset, vol_cache):
    """Read one resource from VOL.<n> at offset. 5-byte header:
    u16 BE magic 0x1234, u8 volume, u16 LE length. Returns bytes or None."""
    if volume not in vol_cache:
        path = find_file(game_dir, "VOL.%d" % volume)
        if path is None:
            vol_cache[volume] = None
        else:
            vol_cache[volume] = open(path, "rb").read()
    vol = vol_cache[volume]
    if vol is None or offset + 5 > len(vol):
        return None
    magic = struct.unpack_from(">H", vol, offset)[0]
    if magic != 0x1234:
        return None
    length = struct.unpack_from("<H", vol, offset + 3)[0]
    return vol[offset + 5 : offset + 5 + length]


def decrypt(buf):
    """XOR with repeating "Avis Durgan" key."""
    return bytes(b ^ CRYPT_KEY[i % len(CRYPT_KEY)] for i, b in enumerate(buf))


def is_displayable(text):
    """Keep human-readable strings, drop empties and binary garbage."""
    stripped = text.strip()
    if not stripped:
        return False
    if not any(c.isalnum() for c in stripped):
        return False
    printable = sum(1 for c in text if c.isprintable() or c in "\n\t")
    return printable / len(text) >= 0.75


def extract_logic_messages(data):
    """Decode the message section of one LOGIC resource.

    Layout (ScummVM logic.cpp decodeLogic):
      u16 LE  bytecode size
      u8[]    bytecode
      u8      message count
      u16 LE  messages size (2 + offset table + strings)
      u16[]   string offsets, relative to (message section + 1)
      char[]  null-terminated strings, XOR-encrypted (uncompressed v2 logics)

    Returns list of (1-based msg number, text).
    """
    if len(data) < 2:
        return []
    bytecode_size = struct.unpack_from("<H", data, 0)[0]
    msg_section = 2 + bytecode_size
    if msg_section + 3 > len(data):
        return []
    count = data[msg_section]
    msgs_size = struct.unpack_from("<H", data, msg_section + 1)[0]
    offsets_pos = msg_section + 3
    strings_pos = offsets_pos + 2 * count
    strings_size = msgs_size - 2 - 2 * count
    if count == 0 or strings_size <= 0 or strings_pos > len(data):
        return []
    strings_size = min(strings_size, len(data) - strings_pos)

    # AGI v2 logics are never LZW-compressed, so strings are always encrypted.
    plain = decrypt(data[strings_pos : strings_pos + strings_size])
    buf = data[:strings_pos] + plain

    messages = []
    for i in range(count):
        off = struct.unpack_from("<H", buf, offsets_pos + 2 * i)[0]
        if off == 0:
            continue
        start = msg_section + 1 + off
        if start >= len(buf):
            continue
        end = buf.find(b"\x00", start)
        if end == -1:
            end = len(buf)
        text = buf[start:end].decode("cp437", errors="replace")
        if is_displayable(text):
            messages.append((i + 1, text))
    return messages


def main():
    ap = argparse.ArgumentParser(description="Extract AGI v2 logic messages")
    ap.add_argument("game_dir", help="directory containing LOGDIR + VOL.n")
    ap.add_argument("-o", "--output", help="output JSON path (default stdout)")
    ap.add_argument("--game-id", default="pq1", help='value for the "game" field')
    args = ap.parse_args()

    vol_cache = {}
    out = []
    bad = 0
    for logic_nr, volume, offset in read_logdir(args.game_dir):
        data = read_volume_resource(args.game_dir, volume, offset, vol_cache)
        if data is None:
            bad += 1
            print("warning: logic %d (vol %d off 0x%05x) unreadable"
                  % (logic_nr, volume, offset), file=sys.stderr)
            continue
        for msg_nr, text in extract_logic_messages(data):
            out.append({"game": args.game_id, "logic": logic_nr,
                        "msg": msg_nr, "text": text})

    payload = json.dumps(out, ensure_ascii=False, indent=1)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    else:
        print(payload)

    logics = len({m["logic"] for m in out})
    print("extracted %d messages from %d logics (%d unreadable resources)"
          % (len(out), logics, bad), file=sys.stderr)


if __name__ == "__main__":
    main()
