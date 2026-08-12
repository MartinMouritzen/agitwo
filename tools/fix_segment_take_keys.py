#!/usr/bin/env python3
"""Re-key QFG1's segment takes to the convention the shared Voice Lab actually reads.

wire_segments.py was written against the old per-game lab fork in games/agitwo/lab/ and
stored segment takes under a character-scoped key: `narrator / sheriff~300_0~g0`. The lab
Martin actually runs is the shared one (voices/lab/), and its segsFor() builds take keys
from the PLAIN line key:

    gm segment    ->  bucket "narrator", key "<lineKey>~g<i>"          e.g. 300_0~g0
    char segment  ->  bucket "<charId>",  key "<lineKey>~c<i>"
                      ...or just "<lineKey>" when the line has a single char segment

Only line_segments.json is character-scoped, and the lab handles that explicitly
(`SEGS[`${id}~${key}`] || SEGS[key]`). The TAKE keys were never meant to carry the prefix,
so every narrator half of a split line looked unvoiced: the row offered "Generate" while a
perfectly good clip sat in takes.json under a key nothing reads. Confirmed against the
working games: Tyranny and Dead Man's Switch both use `<lineKey>~g0` / `~c0`.

Single-char lines are deliberately left alone. There the lab's char row IS the line row
(plain key), which already holds the stitched whole-line take, so moving the char-only
segment on top of it would replace "narrator + character" with "character" in the one slot
the pack builds from.

    python3 tools/fix_segment_take_keys.py            # report
    python3 tools/fix_segment_take_keys.py --write    # migrate, atomically
"""
import json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "lab/data/qfg1")


def main():
    write = "--write" in sys.argv
    segs = json.load(open(os.path.join(DATA, "line_segments.json")))
    takes_path = os.path.join(DATA, "takes.json")
    takes = json.load(open(takes_path))

    moved, kept, missing = [], [], []
    for seg_key, parts in sorted(segs.items()):
        cid, _, line_key = seg_key.partition("~")
        nchar = sum(1 for p in parts if p["who"] == "char")
        gi = ci = 0
        for p in parts:
            if p["who"] == "gm":
                bucket = "narrator"
                old, new = "%s~%s~g%d" % (cid, line_key, gi), "%s~g%d" % (line_key, gi)
                gi += 1
            else:
                bucket = cid
                old = "%s~%s~c%d" % (cid, line_key, ci)
                new = line_key if nchar == 1 else "%s~c%d" % (line_key, ci)
                ci += 1
                if nchar == 1:
                    if old in takes.get(bucket, {}):
                        kept.append((bucket, old))
                    continue
            rec = takes.get(bucket, {}).get(old)
            if rec is None:
                missing.append((bucket, old))
                continue
            if new in takes.get(bucket, {}):
                kept.append((bucket, old))   # never clobber an existing row
                continue
            moved.append((bucket, old, new))
            if write:
                takes[bucket][new] = rec
                del takes[bucket][old]

    for b, o, n in moved[:8]:
        print("  %-12s %-28s -> %s" % (b, o, n))
    if len(moved) > 8:
        print("  ... and %d more" % (len(moved) - 8))
    print("\n%s %d segment take(s)" % ("moved" if write else "would move", len(moved)))
    print("left alone (single-char lines, or target already taken): %d" % len(kept))
    if missing:
        print("no take under the old key: %d" % len(missing))

    if write and moved:
        fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(takes, fh, indent=1)
        os.replace(tmp, takes_path)   # atomic; the lab server runs live
        print("rewrote takes.json atomically - reload the lab")
    return 0


if __name__ == "__main__":
    sys.exit(main())
