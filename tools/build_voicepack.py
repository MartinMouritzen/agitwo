#!/usr/bin/env python3
"""Build the QFG1 voice manifest from the canonical line sources, and verify it.

Until now nothing in the repo actually built the shipped manifest: it was the
union of several `voices-src` files merged by hand, which is how
`qfg1-4675-sheriff-wife.mp3` ended up in the manifest with no clip behind it in
any pack. This script is the single source of truth for that union.

    python3 tools/build_voicepack.py                      # report only
    python3 tools/build_voicepack.py --write              # rewrite every pack's manifest

Sources are merged in order; a later file wins a hash it shares with an earlier
one. Entries with "skip": true are left out (see TEXT.2.1, the boot-screen legal
notice, which is an 11.8s narrator clip the title window disposes immediately).

Verification is the point: every clip a manifest names must exist, at a
plausible size, in every pack directory. A missing clip is silent on the web
build (404) and a failed open natively, so it must fail the build, not ship.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from gen_voice_manifest import text_hash

SOURCES = [
    "voices-src/full/qfg1-full-lines.json",
    "voices-src/qfg1-intro-lines.json",
    "voices-src/qfg1-lines.json",
    "voices-src/qfg1-expansions.json",
]

# Every place a qfg1 pack lives. The web build and the native packs must stay
# byte-identical: the same clips keyed by the same hashes.
PACKS = [
    "scummvm/build-emscripten/voices/qfg1",
    "dist/voicepack/qfg1/agitwo-voices",
    "dist/out/QFG1-Voiced-win/agitwo-voices",
    "dist/out/QFG1-Voiced-linux/agitwo-voices",
    "dist/out/QFG1-Voiced-mac/agitwo-voices",
]

MIN_CLIP_BYTES = 2000


def build():
    manifest, origin, skipped = {}, {}, 0
    for src in SOURCES:
        path = os.path.join(ROOT, src)
        if not os.path.exists(path):
            print("  (missing source, ignored: %s)" % src)
            continue
        for e in json.load(open(path)):
            if e.get("skip"):
                skipped += 1
                continue
            h = text_hash(e["text"])
            manifest[h] = e["file"]
            origin[h] = src
    return manifest, origin, skipped


def main():
    write = "--write" in sys.argv
    manifest, origin, skipped = build()
    print("manifest: %d hashes -> %d distinct clips (%d skipped)"
          % (len(manifest), len(set(manifest.values())), skipped))

    ok = True
    for pack in PACKS:
        pdir = os.path.join(ROOT, pack)
        if not os.path.isdir(pdir):
            print("  %-46s ABSENT" % pack)
            continue
        have = {f for f in os.listdir(pdir) if f.endswith(".mp3")}
        want = set(manifest.values())
        missing = sorted(want - have)
        tiny = sorted(f for f in (want & have)
                      if os.path.getsize(os.path.join(pdir, f)) < MIN_CLIP_BYTES)
        orphan = sorted(have - want)
        state = "OK" if not (missing or tiny) else "BROKEN"
        if missing or tiny:
            ok = False
        print("  %-46s %-7s missing=%d tiny=%d orphan=%d"
              % (pack, state, len(missing), len(tiny), len(orphan)))
        for f in missing[:10]:
            print("      MISSING %s" % f)
        for f in tiny[:10]:
            print("      TINY    %s" % f)
        for f in orphan[:10]:
            print("      orphan  %s" % f)
        if write:
            json.dump(manifest, open(os.path.join(pdir, "manifest.json"), "w"), indent=1)

    if write:
        print("wrote manifest.json into every present pack")
    if not ok:
        print("\nFAILED: a manifest names a clip that is not in the pack.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
