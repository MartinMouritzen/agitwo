#!/usr/bin/env python3
"""Wire the generated segment clips into the lab as Shadowrun-style segments.

For each split line in voices-src/recast/segment-plan.json this writes:
  - lab/data/qfg1/line_segments.json[ "<cid>~<labkey>" ] = [{who,t}, ...]
  - lab/data/qfg1/takes.json[ bucket ][ "<cid>~<labkey>~g#/c#" ] = a take pointing
    at that segment's clip (narrator bucket for 'gm', character bucket for 'char').
Keys are character-scoped to match the patched segsFor() in lab.html.

Run AFTER the segment clips exist under voices/qfg1/_seg/. Idempotent.
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "lab/data/qfg1")
VDIR = os.path.join(ROOT, "scummvm/build-emscripten/voices/qfg1")
mag = {v["voice_id"]: v for v in json.load(open(os.path.join(ROOT, "lab/data/magnific_voices.json")))["voices"]}
def vname(vid): return mag.get(f"mag_{vid}", {}).get("name", str(vid))

# file -> (cid, labkey), same enumeration as characters.json was built
keyfile = {}
percid = {}
for s in ("voices-src/qfg1-lines.json", "voices-src/qfg1-intro-lines.json", "voices-src/full/qfg1-full-lines.json"):
    for e in json.load(open(os.path.join(ROOT, s))):
        # "skip" means "keep out of the manifest", not "does not exist". characters.json
        # counted these, so skipping here shifts every later index for that character.
        cid = e["speaker"]; f = e["file"]
        st = percid.setdefault(cid, {"seen": set(), "i": 0})
        if f in st["seen"]:
            continue
        st["seen"].add(f); keyfile[f] = (cid, f"{e.get('num',0)}_{st['i']}"); st["i"] += 1

plan = json.load(open(os.path.join(ROOT, "voices-src/recast/segment-plan.json")))
line_segments = json.load(open(os.path.join(D, "line_segments.json"))) if os.path.exists(os.path.join(D, "line_segments.json")) else {}
takes = json.load(open(os.path.join(D, "takes.json")))

wired = 0; missing = []
for p in plan:
    f = p["file"]
    if f not in keyfile:
        missing.append((f, "no lab key")); continue
    cid, labkey = keyfile[f]
    sk = f"{cid}~{labkey}"
    line_segments[sk] = [{"who": s["who"], "t": s["t"]} for s in p["segments"]]
    gi = ci = 0
    ok = True
    for s in p["segments"]:
        clip = s["tmp"]  # "_seg/<stem>__s#.mp3", served via audio/qfg1/
        if not os.path.exists(os.path.join(VDIR, clip)):
            ok = False; missing.append((clip, "clip not generated")); continue
        # Take keys use the PLAIN line key. Only line_segments is character-scoped
        # (the lab tries `${id}~${key}` then falls back to `${key}`); segsFor() builds
        # take keys as `${lineKey}~g<i>` / `${lineKey}~c<i>`, and uses the bare line key
        # when the line has a single char segment. Writing `${cid}~${lineKey}~g0` here is
        # what left every narrator half of a split line showing "Generate" with a
        # perfectly good clip sitting under a key nothing reads.
        nchar = sum(1 for x in p["segments"] if x["who"] == "char")
        if s["who"] == "gm":
            segkey = f"{labkey}~g{gi}"; gi += 1; bucket = "narrator"
        else:
            segkey = labkey if nchar == 1 else f"{labkey}~c{ci}"
            ci += 1; bucket = cid
            if nchar == 1:
                # That key is the line's own take (the stitched narrator+character clip
                # the pack is built from). Do not overwrite it with the character half.
                continue
        vid = s["voiceId"]
        takes.setdefault(bucket, {})[segkey] = {
            "selected": clip,
            "takes": [{"file": clip, "voiceId": f"mag_{vid}", "voiceName": vname(vid), "stability": 0.5, "ts": 0}],
        }
    if ok:
        wired += 1

json.dump(line_segments, open(os.path.join(D, "line_segments.json"), "w"))
json.dump(takes, open(os.path.join(D, "takes.json"), "w"))
print(f"wired {wired}/{len(plan)} split lines into the lab segment UI")
if missing:
    print("issues:")
    for m in missing:
        print("  ", m)
