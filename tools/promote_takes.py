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
    python3 tools/promote_takes.py --adopt --write   # also register shipped-but-unknown clips

`--adopt` handles the reverse drift: a clip regenerated outside the lab (a recast run,
say) is audio the lab has no take row for, so the lab still shows the OLD take as
selected and this script would happily promote that old take back over the new clip,
silently undoing the recast. Adopting copies the shipped clip into `<char>/takes/`,
adds a row for it and selects it, so the lab and the pack agree again. It only
considers characters passed with --only, because most narrator clips were never
imported as takes at all and adopting 2000+ of them is not the intent.

    python3 tools/promote_takes.py --adopt --only dryad,warlock --write

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

    Per character, in source order, first sighting of a clip wins, and the running index
    is per character rather than per text resource.

    It deliberately does NOT honour "skip". That flag means "do not put this line in the
    manifest" (the boot-screen legal notices), not "this line does not exist" -- and the
    lab's characters.json was enumerated with them counted. Skipping here shifts every
    later index for that character, which for the narrator meant 2,376 of 3,811 lines
    mapping to the wrong clip, and would have promoted takes onto their neighbours.
    Verified against characters.json: without skip, 3,811/3,811 line texts match."""
    keyfile, percid = {}, {}
    for s in SOURCES:
        for e in json.load(open(os.path.join(ROOT, s))):
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


def src_voices():
    """clip filename -> voiceId that actually generated it, per voices-src."""
    out = {}
    for s in SOURCES + ["voices-src/qfg1-expansions.json"]:
        p = os.path.join(ROOT, s)
        if not os.path.exists(p):
            continue
        for e in json.load(open(p)):
            out.setdefault(e["file"], e.get("voiceId"))
    return out


SRC_VOICE = {}


def adopt(takes, keyfile, only, write):
    """Register shipped clips the lab has no take row for, and select them."""
    adopted = []
    for bucket, lines in sorted(takes.items()):
        if bucket not in only:
            continue
        for key, rec in sorted(lines.items()):
            if "~" in key:
                continue
            clip = keyfile.get((bucket, key))
            if not clip:
                continue
            cp = os.path.join(VOICES, clip)
            if not os.path.exists(cp):
                continue
            known = set()
            for t in rec.get("takes", []):
                p = os.path.join(VOICES, t["file"])
                if os.path.exists(p):
                    known.add(md5(p))
            if md5(cp) in known:
                continue
            # The voice comes from voices-src, which is what actually generated the
            # shipped clip. Inheriting it from the row's first take mislabels every
            # recast -- it would tag a new mag_332 Dryad clip as the old mag_684.
            vid = "mag_%s" % SRC_VOICE.get(clip, "unknown")
            ts = int(os.path.getmtime(cp))
            newrel = "%s/takes/%s__%s__%d.mp3" % (bucket, key, vid.replace("_", "", 1), ts)
            adopted.append((bucket, key, clip, newrel))
            if write:
                dest = os.path.join(VOICES, newrel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(cp, dest)
                rec.setdefault("takes", []).append(
                    {"file": newrel, "voiceId": vid, "ts": ts})
                rec["selected"] = newrel
    return adopted


def main():
    write = "--write" in sys.argv
    keyfile = lab_keys()
    takes_path = os.path.join(DATA, "takes.json")
    takes = json.load(open(takes_path))

    if "--adopt" in sys.argv:
        SRC_VOICE.update(src_voices())
        only = set()
        for i, a in enumerate(sys.argv):
            if a == "--only" and i + 1 < len(sys.argv):
                only = set(sys.argv[i + 1].split(","))
        got = adopt(takes, keyfile, only, write)
        for b, k, clip, newrel in got:
            print("  adopt %-13s %-16s %s -> %s" % (b, k, clip, newrel))
        print("\n%s %d shipped clip(s) into the lab" % ("adopted" if write else "would adopt", len(got)))
        if write and got:
            fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".json")
            with os.fdopen(fd, "w") as fh:
                json.dump(takes, fh, indent=1)
            os.replace(tmp, takes_path)   # atomic; the lab server may be live
            print("rewrote takes.json atomically - reload the lab")
        return 0
    plan = {p["file"]: p for p in
            json.load(open(os.path.join(ROOT, "voices-src/recast/segment-plan.json")))}
    segkeys = list(json.load(open(os.path.join(DATA, "line_segments.json"))))
    seg_owner = {}
    for f, p in plan.items():
        for s in p["segments"]:
            seg_owner[os.path.basename(s["tmp"])] = f

    promoted, restitched, skipped, problems, legacy = [], [], 0, [], []
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
                # Shared-lab convention: "<lineKey>~g<i>" / "<lineKey>~c<i>". The line key
                # alone does not say which character owns the line (a gm segment lives in
                # the narrator bucket), so find the owning line through line_segments,
                # whose keys ARE character-scoped.
                labkey, _, which = key.rpartition("~")
                if not labkey or not which[:1] in ("g", "c") or not which[1:].isdigit():
                    problems.append((bucket, key, "unparseable segment key"))
                    continue
                cid = next((sk.split("~", 1)[0] for sk in segkeys
                            if sk.split("~", 1)[1] == labkey), None)
                clip = keyfile.get((cid, labkey)) if cid else None
                entry = plan.get(clip) if clip else None
                if not entry:
                    if labkey in segkeys:
                        # Old character-scoped key from the retired lab fork, e.g.
                        # "hero~55_0~c0". The shared lab never reads these, so it is
                        # stale bookkeeping rather than something to promote.
                        legacy.append((bucket, key))
                    else:
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
            if clip in plan:
                # A split line's clip is narrator framing + character speech stitched
                # together. Its whole-line take predates the split, so copying that over
                # the clip would silently drop the narrator half. Only the per-segment
                # takes (the "~g0"/"~c0" keys) may drive a stitched clip.
                skipped += 1
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
    for b, k in legacy:
        print("  legacy  %-13s %-16s (old lab-fork key; the shared lab does not read it)" % (b, k))
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
