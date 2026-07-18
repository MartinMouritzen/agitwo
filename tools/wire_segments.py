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
        if e.get("skip"):
            continue
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
        if s["who"] == "gm":
            segkey = f"{cid}~{labkey}~g{gi}"; gi += 1; bucket = "narrator"
        else:
            segkey = f"{cid}~{labkey}~c{ci}"; ci += 1; bucket = cid
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
