#!/usr/bin/env python3
"""Stitch per-line voice segments into the single game clip.

Reads voices-src/recast/segment-plan.json (each line: file + ordered segments,
each segment having a "tmp" clip under voices/qfg1/_seg/). Concatenates the
segments in order with a short silence between them and overwrites the line's
game clip voices/qfg1/<file>, so the engine still plays one clip per line but
you hear narrator -> character in sequence.

Usage: python3 tools/concat_segments.py
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VDIR = os.path.join(ROOT, "scummvm/build-emscripten/voices/qfg1")
SIL = os.path.join(VDIR, "_seg", "_silence.mp3")
plan = json.load(open(os.path.join(ROOT, "voices-src/recast/segment-plan.json")))

done = 0; failed = []
for p in plan:
    segfiles = [os.path.join(VDIR, s["tmp"]) for s in p["segments"]]
    missing = [f for f in segfiles if not (os.path.exists(f) and os.path.getsize(f) > 2000)]
    if missing:
        failed.append((p["file"], "missing segments: " + ", ".join(os.path.basename(m) for m in missing)))
        continue
    # interleave silence between segments
    seq = []
    for i, f in enumerate(segfiles):
        if i: seq.append(SIL)
        seq.append(f)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fl:
        for f in seq:
            fl.write("file '%s'\n" % f.replace("'", "'\\''"))
        listfile = fl.name
    out = os.path.join(VDIR, p["file"])
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
         "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", "-ac", "1", out],
        capture_output=True, text=True)
    os.unlink(listfile)
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 2000:
        failed.append((p["file"], "ffmpeg: " + r.stderr.strip().splitlines()[-1] if r.stderr else "unknown"))
    else:
        done += 1

print(f"stitched: {done}/{len(plan)} lines")
if failed:
    print("FAILED:")
    for f, why in failed:
        print("  ", f, "->", why)
