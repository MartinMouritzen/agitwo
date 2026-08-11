#!/usr/bin/env python3
"""Promote the Voice Lab's selected takes onto the game clips they belong to.

The lab records a decision by pointing `takes.json[bucket][labkey]["selected"]` at a
file under `<char>/takes/`. The game, though, plays the clip the manifest names
(`qfg1-NNNN-<speaker>.mp3`), and nothing was copying one onto the other. So every
recast, every directed re-take and every audition pick made in the lab stayed
invisible to the shipped pack.

That had been quietly true for a long time: as of 2026-08-11, 43 of 49 selections
had never been promoted, including a complete 39-line Fenrus recast (mag_586 ->
mag_584) made in July, and `*scream*` / `*snores*` / `[laughing]` directed re-takes
that the pack was still playing undirected.

    python3 tools/promote_takes.py            # report what would change
    python3 tools/promote_takes.py --write    # copy takes onto their game clips

Split lines (segment keys like `hero~55_0~c0`) are not a straight copy: only that one
segment was re-recorded, so the game clip is re-stitched from the segment plan with
`tools/concat_segments.py`'s recipe. Those are reported and skipped unless --write.

After promoting, re-run tools/build_voicepack.py --write to refresh the packs.
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICES = os.path.join(ROOT, "scummvm/build-emscripten/voices/qfg1")
DATA = os.path.join(ROOT, "lab/data/qfg1")
SOURCES = ["voices-src/qfg1-lines.json", "voices-src/qfg1-intro-lines.json",
           "voices-src/full/qfg1-full-lines.json"]


def md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def lab_keys():
    """(charId, labkey) -> clip filename, using the lab's own enumeration order.

    Must stay identical to tools/wire_segments.py: per character, in source order,
    first sighting of a clip wins, and the running index is per character, not per
    text resource."""
    keyfile, percid = {}, {}
    for s in SOURCES:
        for e in json.load(open(os.path.join(ROOT, s))):
            if e.get("skip"):
                continue
            cid, f = e["speaker"], e["file"]
            st = percid.setdefault(cid, {"seen": set(), "i": 0})
            if f in st["seen"]:
                continue
            st["seen"].add(f)
            keyfile[(cid, "%s_%d" % (e.get("num", 0), st["i"]))] = f
            st["i"] += 1
    return keyfile


def restitch(entry):
    """Rebuild a split line's game clip from its segments (narrator + character)."""
    sil = os.path.join(VOICES, "_seg", "_silence.mp3")
    segs = [os.path.join(VOICES, s["tmp"]) for s in entry["segments"]]
    for p in [sil] + segs:
        if not (os.path.exists(p) and os.path.getsize(p) > 1000):
            return False, "missing segment %s" % os.path.basename(p)
    fd, lst = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as fh:
        for i, p in enumerate(segs):
            if i:
                fh.write("file '%s'\n" % sil)
            fh.write("file '%s'\n" % p)
    out = os.path.join(VOICES, entry["file"])
    r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100",
                        "-ac", "1", out], capture_output=True, text=True)
    os.unlink(lst)
    if r.returncode or os.path.getsize(out) < 2000:
        return False, (r.stderr.strip().splitlines() or ["ffmpeg failed"])[-1]
    return True, "restitched"


def main():
    write = "--write" in sys.argv
    keyfile = lab_keys()
    takes = json.load(open(os.path.join(DATA, "takes.json")))
    plan = {p["file"]: p for p in
            json.load(open(os.path.join(ROOT, "voices-src/recast/segment-plan.json")))}
    seg_owner = {}
    for f, p in plan.items():
        for s in p["segments"]:
            seg_owner[os.path.basename(s["tmp"])] = f

    promoted, restitched, skipped, problems = [], [], 0, []
    for bucket, lines in sorted(takes.items()):
        for key, rec in sorted(lines.items()):
            sel = rec.get("selected") or ""
            if "/takes/" not in sel:
                continue                      # already points at the shipped clip
            take = os.path.join(VOICES, sel)
            if not os.path.exists(take):
                problems.append((bucket, key, "take file missing: %s" % sel))
                continue
            if "~" in key:
                # A segment of a split line: "<cid>~<labkey>~[gc]<i>". Only that one
                # segment was re-recorded, so copy it over its _seg/ file and rebuild
                # the game clip from the plan; a straight copy onto the game clip
                # would throw away the other segments.
                parts = key.split("~")
                if len(parts) != 3:
                    problems.append((bucket, key, "unparseable segment key"))
                    continue
                cid, labkey, which = parts
                clip = keyfile.get((cid, labkey))
                entry = plan.get(clip) if clip else None
                if not entry:
                    problems.append((bucket, key, "segment take with no plan entry"))
                    continue
                want = "gm" if which.startswith("g") else "char"
                idx = int(which[1:])
                seq = [s for s in entry["segments"] if s["who"] == want]
                if idx >= len(seq):
                    problems.append((bucket, key, "segment index %d out of range" % idx))
                    continue
                segfile = os.path.join(VOICES, seq[idx]["tmp"])
                if os.path.exists(segfile) and md5(take) == md5(segfile):
                    skipped += 1
                    continue
                restitched.append((bucket, key, clip))
                if write:
                    shutil.copy2(take, segfile)
                continue
            clip = keyfile.get((bucket, key))
            if not clip:
                problems.append((bucket, key, "no clip maps to this lab key"))
                continue
            dest = os.path.join(VOICES, clip)
            if os.path.exists(dest) and md5(take) == md5(dest):
                skipped += 1
                continue
            promoted.append((bucket, key, sel, clip))
            if write:
                shutil.copy2(take, dest)

    for b, k, sel, clip in promoted:
        print("  %-13s %-16s -> %s" % (b, k, clip))
    for b, k, target in restitched:
        print("  %-13s %-16s -> %s (segment; re-stitch)" % (b, k, target))
        if write:
            ok, why = restitch(plan[target])
            print("      %s" % why)
    for b, k, why in problems:
        print("  PROBLEM %-13s %-16s %s" % (b, k, why))
    print("\n%s %d clip(s); %d segment line(s); %d already current; %d problem(s)"
          % ("promoted" if write else "would promote", len(promoted),
             len(restitched), skipped, len(problems)))
    if promoted and not write:
        print("re-run with --write, then: python3 tools/build_voicepack.py --write")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
