#!/usr/bin/env python3
"""Generate a voices manifest for the agitwo web build.

Input: a "voice lines" JSON file — a list of objects:
    {"text": "<exact game text>", "speaker": "narrator", "file": "0001-narrator.mp3", ...}
(extra keys are ignored; entries with "skip": true are ignored)

Output: manifest.json mapping fnv1a64(normalized text) -> clip filename,
written next to the input file unless -o is given.

The normalization here MUST match common/voiceover.cpp in the scummvm tree:
collapse every run of [space, \\n, \\r, \\t] to a single space, trim ends.
Hash: 64-bit FNV-1a over the normalized bytes (latin-1/cp437 bytes as-is).
"""
import json
import sys
import os


def normalize(text: str) -> str:
    out = []
    pending = False
    for c in text:
        if c in " \n\r\t":
            pending = len(out) > 0
        else:
            if pending:
                out.append(" ")
                pending = False
            out.append(c)
    return "".join(out)


def fnv1a64(data: bytes) -> str:
    h = 0xCBF29CE484222325
    for b in data:
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def text_hash(text: str) -> str:
    return fnv1a64(normalize(text).encode("cp437", errors="replace"))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__)
        sys.exit(1)
    src = args[0]
    out = args[1] if len(args) > 1 else os.path.join(os.path.dirname(src), "manifest.json")
    lines = json.load(open(src))
    manifest = {}
    for entry in lines:
        if entry.get("skip"):
            continue
        h = text_hash(entry["text"])
        if h in manifest and manifest[h] != entry["file"]:
            print(f"WARNING: hash collision/duplicate text for {entry['file']} vs {manifest[h]}")
        manifest[h] = entry["file"]
    json.dump(manifest, open(out, "w"), indent=1)
    print(f"wrote {out}: {len(manifest)} clips")


if __name__ == "__main__":
    main()
