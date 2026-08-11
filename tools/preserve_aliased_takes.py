#!/usr/bin/env python3
"""Give every lab take row that aliases a shipped clip its own file.

The lab imported the original pack as takes by REFERENCE: a take row's "file" is the
bare game clip name (`qfg1-2044-fenrus.mp3`) rather than a file under `<char>/takes/`.
That makes the shipped clip and the lab's record of one particular take the same bytes
on disk, so anything that writes a new version of a clip - a recast regeneration, or
promote_takes.py - silently destroys the old take. In the lab both rows then play the
same audio, which is what "all takes sound the same" looks like.

This restores the aliased rows from a known-good copy of the pack (the released zip,
or any pack directory that predates the overwrite), writes each into `<char>/takes/`,
and re-points takes.json at it. The shipped clip keeps the current, selected audio.

    python3 tools/preserve_aliased_takes.py <reference-pack-dir>
    python3 tools/preserve_aliased_takes.py <reference-pack-dir> --write

Only rows whose clip actually differs from the reference are touched, so it is safe to
re-run. takes.json is rewritten atomically (temp file + rename) because the lab server
may be live; reload the lab afterwards.
"""
import hashlib, json, os, shutil, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICES = os.path.join(ROOT, "scummvm/build-emscripten/voices/qfg1")
DATA = os.path.join(ROOT, "lab/data/qfg1")
SOURCES = ["voices-src/qfg1-lines.json", "voices-src/qfg1-intro-lines.json",
           "voices-src/full/qfg1-full-lines.json"]


def md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def lab_keys():
    """clip filename -> (charId, labkey); mirrors tools/wire_segments.py exactly."""
    out, percid = {}, {}
    for s in SOURCES:
        for e in json.load(open(os.path.join(ROOT, s))):
            if e.get("skip"):
                continue
            cid, f = e["speaker"], e["file"]
            st = percid.setdefault(cid, {"seen": set(), "i": 0})
            if f in st["seen"]:
                continue
            st["seen"].add(f)
            out[f] = (cid, "%s_%d" % (e.get("num", 0), st["i"]))
            st["i"] += 1
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__)
        return 1
    ref, write = args[0], "--write" in sys.argv
    keys = lab_keys()
    takes_path = os.path.join(DATA, "takes.json")
    takes = json.load(open(takes_path))

    restored, missing = [], []
    for bucket, lines in sorted(takes.items()):
        for key, rec in sorted(lines.items()):
            for t in rec.get("takes", []):
                clip = t.get("file") or ""
                if "/" in clip:
                    continue                      # already has its own file
                cur = os.path.join(VOICES, clip)
                old = os.path.join(ref, clip)
                if not os.path.exists(old) or not os.path.exists(cur):
                    continue
                if md5(cur) == md5(old):
                    continue                      # clip unchanged; row is still truthful
                vid = str(t.get("voiceId") or "mag").replace("mag_", "")
                ts = int(os.path.getmtime(old))
                newrel = "%s/takes/%s__mag%s__%d.mp3" % (bucket, key, vid, ts)
                dest = os.path.join(VOICES, newrel)
                restored.append((bucket, key, clip, newrel, t))
                if write:
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(old, dest)
                    t["file"] = newrel
                    if rec.get("selected") == clip:
                        rec["selected"] = newrel

    for b, k, clip, newrel, _ in restored:
        print("  %-13s %-16s %-26s -> %s" % (b, k, clip, newrel))
    print("\n%s %d aliased take(s) from %s"
          % ("restored" if write else "would restore", len(restored), ref))

    if write and restored:
        fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(takes, fh, indent=1)
        os.replace(tmp, takes_path)       # atomic; the lab server may be live
        print("rewrote takes.json atomically - reload the lab to pick it up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
