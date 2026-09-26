#!/usr/bin/env python3
"""Extract all displayable text from a Sierra SCI1 (early/middle/late) game, e.g. Police Quest III.

SCI1 sits between the two formats the other extractors handle: its text is still in TEXT
resources and SCI0-style script string blocks (like extract_sci0.py), but its resource map has
the SCI1 type-offset header with 6-byte entries (volume in the top 4 bits of the offset) and each
volume entry has a 9-byte header: type, number, packed size + 4, unpacked size, method
(ScummVM engines/sci/resource/resource.cpp, kResVersionSci1Middle/Late). Compression: 0 stored,
1 Huffman, 2 LZW1, 3/4 LZW1 view/picture, 18-20 DCL.

Loose patch files (NNN.TEX, NNN.SCR) override the volume copies, as in the interpreter.

Output records match extract_sci0.py: {"game", "res": "text"|"script", "num", "idx", "text"}

Usage: python3 extract_sci1.py <game_dir> [-o out.json] [--game-id pq3]
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_sci0 as sci0  # noqa: E402
from extract_sci11 import _explode, find_file, read_map  # noqa: E402

T_SCRIPT, T_TEXT = 2, 3
PATCH_EXT = {T_SCRIPT: "SCR", T_TEXT: "TEX"}


def load(game_dir, vols, vol, off):
    if vol not in vols:
        vols[vol] = open(find_file(game_dir, f"RESOURCE.{vol:03d}"), "rb").read()
    data = vols[vol]
    rtype, num, packed, unpacked, method = struct.unpack_from("<BHHHH", data, off)
    src = data[off + 9: off + 9 + packed - 4]
    if method == 0:
        return src[:unpacked]
    if method == 1:
        return sci0.unpack_huffman(src, unpacked)
    if method == 2:
        return sci0.unpack_lzw(src, unpacked, lzw1=True)
    if method == 3:
        return sci0.unpack_lzw1_view(src, unpacked)
    if method in (18, 19, 20):
        return _explode(src, unpacked)
    raise ValueError(f"resource {rtype:#x}/{num}: unsupported compression {method}")


def patch(game_dir, rtype, num):
    p = find_file(game_dir, f"{num}.{PATCH_EXT[rtype]}")
    if not p:
        return None
    raw = open(p, "rb").read()
    return raw[2 + raw[1]:]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("game_dir")
    ap.add_argument("-o", "--output")
    ap.add_argument("--game-id", default="")
    a = ap.parse_args()
    index = read_map(find_file(a.game_dir, "RESOURCE.MAP"))
    nums = {t: {n for (tt, n) in index if tt == t} for t in (T_TEXT, T_SCRIPT)}
    for entry in os.listdir(a.game_dir):
        stem, ext = os.path.splitext(entry)
        for t, e in PATCH_EXT.items():
            if stem.isdigit() and ext[1:].upper() == e:
                nums[t].add(int(stem))
    vols, out = {}, []
    for rtype, kind, parse in ((T_TEXT, "text", sci0.extract_text_resource),
                               (T_SCRIPT, "script", sci0.extract_script_strings)):
        for num in sorted(nums[rtype]):
            data = patch(a.game_dir, rtype, num)
            if data is None:
                data = load(a.game_dir, vols, *index[(rtype, num)])
            for idx, text in parse(data):
                out.append({"game": a.game_id, "res": kind, "num": num, "idx": idx, "text": text})
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if a.output:
        open(a.output, "w").write(text + "\n")
        print(f"{len(out)} strings -> {a.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
