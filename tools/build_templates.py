#!/usr/bin/env python3
"""Build templates.json: clips for lines the game assembles at runtime.

Some lines are printf templates - "Good luck in your quest, %s." - and the hook only
ever sees the finished string, with the player's name already in it. That can never
match a hash of the template, so those lines were simply silent. Rather than enumerate
the substitutions (impossible for a name the player types), we voice a generic read
and let the engine recognise the line by its fixed head and tail.

Output entry:  {"plen": N, "phash": "...", "slen": M, "shash": "...", "clip": "..."}

Head and tail are stored as HASHES, not text, so the shipped pack keeps the property
the manifest already has: it contains no game text, only hashes. The engine hashes the
first `plen` and last `slen` bytes of the normalized string and compares.

Guards, because a bad template is worse than a silent line - it would speak the wrong
clip over a real line:
  * head and tail must be pure ASCII, or the C++/JS byte-for-byte hashes could disagree
  * plen + slen must be long enough to be unmistakable
  * no template may match any other line the game can display (checked against every
    extracted message)
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from gen_voice_manifest import normalize, fnv1a64

SRC = "voices-src/qfg1-generic.json"
MESSAGES = "text/qfg1-messages.json"
FMT = re.compile(r"%[-0-9.]*[sdcxu]")
MIN_FIXED = 12          # combined head+tail bytes; below this a match is not credible


def split_template(raw):
    """normalized head before the first substitution, tail after the last."""
    norm = normalize(raw)
    hits = list(FMT.finditer(norm))
    if not hits:
        return None
    return norm[:hits[0].start()], norm[hits[-1].end():]


def main():
    write = "--write" in sys.argv
    entries = json.load(open(os.path.join(ROOT, SRC)))
    messages = [e["text"] for e in json.load(open(os.path.join(ROOT, MESSAGES)))
                if e.get("res") == "text"]
    normed = [normalize(t) for t in messages]

    out, problems = [], []
    for e in entries:
        split = split_template(e["text"])
        if not split:
            problems.append((e["file"], "no substitution in text"))
            continue
        head, tail = split
        if not (head.isascii() and tail.isascii()):
            problems.append((e["file"], "head/tail not pure ASCII"))
            continue
        if len(head) + len(tail) < MIN_FIXED:
            problems.append((e["file"], "fixed part too short (%d bytes)" % (len(head) + len(tail))))
            continue
        # would this template also swallow some OTHER line the game can show?
        collide = [t for t in normed
                   if t.startswith(head) and t.endswith(tail)
                   and len(t) >= len(head) + len(tail)
                   and normalize(e["text"]) != t]
        if collide:
            problems.append((e["file"], "matches %d other message(s), e.g. %r"
                             % (len(collide), collide[0][:60])))
            continue
        out.append({
            "plen": len(head), "phash": fnv1a64(head.encode("cp437", "replace")),
            "slen": len(tail), "shash": fnv1a64(tail.encode("cp437", "replace")),
            "clip": e["file"],
        })
        print("  %-26s head=%-3d tail=%-3d  %r ... %r"
              % (e["file"], len(head), len(tail), head[:34], tail[-34:]))

    for f, why in problems:
        print("  PROBLEM %-26s %s" % (f, why))
    print("\n%d template(s), %d problem(s)" % (len(out), len(problems)))

    if problems:
        print("refusing to write: a template that matches the wrong line would speak over it")
        return 1
    if write:
        for pack in ["scummvm/build-emscripten/voices/qfg1",
                     "dist/voicepack/qfg1/agitwo-voices",
                     "dist/out/QFG1-Voiced-win/agitwo-voices",
                     "dist/out/QFG1-Voiced-linux/agitwo-voices",
                     "dist/out/QFG1-Voiced-mac/agitwo-voices"]:
            d = os.path.join(ROOT, pack)
            if os.path.isdir(d):
                json.dump(out, open(os.path.join(d, "templates.json"), "w"), indent=1)
        print("wrote templates.json into every present pack")
    return 0


if __name__ == "__main__":
    sys.exit(main())
