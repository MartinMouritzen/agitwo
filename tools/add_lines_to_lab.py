#!/usr/bin/env python3
"""Add newly-voiced lines to the Voice Lab's line list, and register their takes.

The lab reads lab/data/qfg1/characters.json, which was built once from three voices-src
files. Anything added later is shipped in the pack but invisible in the lab: you cannot
hear it, re-roll it or pick a different take. That was true of all 31 clips added on
2026-08-12 -- the 19 spell/Meep/password expansions and the 12 generic reads for lines
the game assembles at runtime, including Sheriff Schultz's "Good luck in your quest".

New lines are APPENDED, and each character's running index continues from where it left
off, because a line's key is "<textRes>_<index>" and renumbering would repoint every
existing take in takes.json at a different line.

For the generic (template) lines the lab shows the words that are actually SPOKEN, not
the raw "%s" template, since that is what you audition. The template stays in
voices-src/qfg1-generic.json.

    python3 tools/add_lines_to_lab.py            # report
    python3 tools/add_lines_to_lab.py --write    # append, atomically
"""
import json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "lab/data/qfg1")
VOICES = os.path.join(ROOT, "scummvm/build-emscripten/voices/qfg1")
BASE = ["voices-src/qfg1-lines.json", "voices-src/qfg1-intro-lines.json",
        "voices-src/full/qfg1-full-lines.json"]
NEW = ["voices-src/qfg1-expansions.json", "voices-src/qfg1-generic.json"]

# The lab prints voiceName on the take chip, so it has to be the catalog name
# ("Blake Hudson"), not the character id.
VOICE_NAMES = {v["magId"]: v["name"] for v in
               json.load(open(os.path.join(ROOT, "lab/data/magnific_voices.json")))["voices"]}


def main():
    write = "--write" in sys.argv
    chars = json.load(open(os.path.join(DATA, "characters.json")))
    takes_path = os.path.join(DATA, "takes.json")
    takes = json.load(open(takes_path))

    by_id = {c["id"]: c for c in chars["characters"]}
    by_id["narrator"] = chars["narrator"]

    # Continue each character's index exactly where characters.json stopped.
    nxt, seen = {}, {}
    for s in BASE:
        for e in json.load(open(os.path.join(ROOT, s))):
            cid, f = e["speaker"], e["file"]
            st = seen.setdefault(cid, set())
            if f in st:
                continue
            st.add(f)
            nxt[cid] = nxt.get(cid, 0) + 1

    added, skipped, unknown = [], 0, []
    for s in NEW:
        p = os.path.join(ROOT, s)
        if not os.path.exists(p):
            continue
        for e in json.load(open(p)):
            cid, f = e["speaker"], e["file"]
            st = seen.setdefault(cid, set())
            if f in st:
                skipped += 1
                continue
            ch = by_id.get(cid)
            if ch is None:
                unknown.append((cid, f))
                continue
            st.add(f)
            idx = nxt.get(cid, 0)
            nxt[cid] = idx + 1
            key = "%s_%d" % (e.get("num", 0), idx)
            spoken = e.get("say") or e["text"]
            added.append((cid, key, f, spoken))
            if write:
                ch.setdefault("lines", []).append(
                    {"c": e.get("num", 0), "n": idx, "t": spoken,
                     "cn": "text %s" % e.get("num", 0)})
                rec = takes.setdefault(cid, {}).setdefault(key, {"selected": None, "takes": []})
                if not any(t.get("file") == f for t in rec["takes"]):
                    rec["takes"].append({"file": f, "voiceId": "mag_%s" % e.get("voiceId"),
                                         "voiceName": VOICE_NAMES.get(e.get("voiceId"), ""),
                                         "ts": 0})
                rec["selected"] = rec["selected"] or f

    for cid, key, f, spoken in added:
        print("  %-13s %-10s %-26s %r" % (cid, key, f, spoken[:46]))
    print("\n%s %d line(s); %d already present" % ("added" if write else "would add", len(added), skipped))
    for cid, f in unknown:
        print("  UNKNOWN CHARACTER %s (%s) - not in characters.json" % (cid, f))

    missing = [f for _, _, f, _ in added if not os.path.exists(os.path.join(VOICES, f))]
    if missing:
        print("clip missing from the pack: %s" % missing)
        return 1
    if write and added:
        for path, blob in ((os.path.join(DATA, "characters.json"), chars),
                           (takes_path, takes)):
            fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".json")
            with os.fdopen(fd, "w") as fh:
                json.dump(blob, fh)
            os.replace(tmp, path)      # atomic; the lab server runs live
        print("rewrote characters.json and takes.json atomically - reload the lab")
    return 0


if __name__ == "__main__":
    sys.exit(main())
