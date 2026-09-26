#!/usr/bin/env python3
"""Extract the sprites of named characters from a Sierra SCI0/SCI01 game (Quest for Glory II).

SCI0 games have no talking-head portraits, but every on-screen character is a script object
(Actor, Prop or View) with a name and a view. This tool reads every object in every script,
keeps those with a view, renders a front-facing cel of that view, and writes one PNG per object
plus sprites.json, so characters can be matched to their sprite by name.

Formats (ported from ScummVM engines/sci):
  - script resources are block streams (u16 type, u16 size); type 1 = object, 6 = class. An
    object block is 0x1234, localsOffset, funcSelectorOffset, varCount, then the variables; a
    class block is followed by its variables' selector ids (engine/object.cpp Object::init)
  - selector names come from vocab 997, the class table (class number -> script) from vocab 996
  - SCI0 EGA views: loop count, mirror mask, loop offsets; cels are width, height, displaceX,
    displaceY, clearKey, then bytes of (run length << 4 | EGA colour) (graphics/view.cpp)

Usage: python3 extract_sci0_sprites.py <game_dir> <out_dir> [--scale 4]
       python3 extract_sci0_sprites.py <game_dir> <out_dir> --render-map map.json
         (map.json: {"sprites": {"<name>": [view, loop, cel], ...}} -> <out_dir>/<name>.png)
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_sci0 as sci0  # noqa: E402

T_VIEW, T_SCRIPT, T_VOCAB = 0, 2, 6
PATCH_NAME = {T_VIEW: "VIEW", T_SCRIPT: "SCRIPT", T_VOCAB: "VOCAB"}
EGA = [(0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170), (170, 0, 0), (170, 0, 170), (170, 85, 0), (170, 170, 170),
       (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255), (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255)]


class Game:
    def __init__(self, game_dir):
        self.dir = game_dir
        entries = sci0.read_map(game_dir)
        sci0.detect_scheme(game_dir, entries)
        self.index = {(t, n): (v, o) for t, n, v, o in entries}
        self.cache = {}

    def load(self, rtype, num):
        patch = sci0.find_file(self.dir, f"{PATCH_NAME[rtype]}.{num:03d}")
        if patch:
            raw = open(patch, "rb").read()
            return raw[2 + raw[1]:] if raw[1] < 0x80 else raw[2:]
        if (rtype, num) not in self.index:
            return None
        return sci0.load_resource(self.dir, *self.index[(rtype, num)], self.cache)

    def numbers(self, rtype):
        nums = {n for (t, n) in self.index if t == rtype}
        for entry in os.listdir(self.dir):
            stem, _, ext = entry.partition(".")
            if stem.upper() == PATCH_NAME[rtype] and ext.isdigit():
                nums.add(int(ext))
        return sorted(nums)


def vocab_strings(data):
    count = struct.unpack_from("<H", data, 0)[0]
    out = []
    for i in range(count):
        off = struct.unpack_from("<H", data, 2 + 2 * i)[0]
        n = struct.unpack_from("<H", data, off)[0]
        out.append(data[off + 2: off + 2 + n].decode("latin-1"))
    return out


def cstring(buf, off):
    end = buf.find(0, off)
    return buf[off:end].decode("latin-1") if 0 <= off < len(buf) and end > off else ""


def script_objects(script):
    """[(kind, vars, baseVars)] for object (1) and class (6) blocks."""
    out, pos = [], 0
    if len(script) >= 2 and struct.unpack_from("<H", script, 0)[0] == 0:
        pos = 2      # SCI01 scripts may start with a 0 word before the first block
    while pos + 4 <= len(script):
        btype, size = struct.unpack_from("<HH", script, pos)
        if btype == 0 or size < 4:
            break
        if btype in (1, 6) and struct.unpack_from("<H", script, pos + 4)[0] == 0x1234:
            count = struct.unpack_from("<H", script, pos + 10)[0]
            vars_ = list(struct.unpack_from(f"<{count}H", script, pos + 12))
            base = list(struct.unpack_from(f"<{count}H", script, pos + 12 + 2 * count)) if btype == 6 else None
            out.append((btype, vars_, base))
        pos += size
    return out


def load_objects(game):
    selectors = vocab_strings(game.load(T_VOCAB, 997))
    classes, objects = {}, []
    for num in game.numbers(T_SCRIPT):
        script = game.load(T_SCRIPT, num)
        if not script:
            continue
        for kind, vars_, base in script_objects(script):
            rec = {"script": num, "kind": kind, "vars": vars_, "buf": script}
            if kind == 6:
                rec["selectors"] = base
                classes[vars_[0]] = rec     # species
            objects.append(rec)
    for rec in objects:
        cls = rec if rec["kind"] == 6 else classes.get(rec["vars"][1])
        if not cls:
            continue
        ids = cls["selectors"][:len(rec["vars"])]
        props = {selectors[s]: v for s, v in zip(ids, rec["vars"]) if s < len(selectors)}
        rec["props"] = props
        rec["name"] = cstring(rec["buf"], props.get("name", -1))
        rec["className"] = cstring(cls["buf"], cls["vars"][3]) if len(cls["vars"]) > 3 else "?"
    return objects


def render(game, view_no, loop, cel, scale):
    from PIL import Image
    view = game.load(T_VIEW, view_no)
    if not view or len(view) < 8:
        return None
    loops = view[0]
    if loops == 0:
        return None
    loop = loop if loop < loops else 0
    mirror = bool((struct.unpack_from("<H", view, 2)[0] >> loop) & 1)
    lo = struct.unpack_from("<H", view, 8 + loop * 2)[0]
    cels = struct.unpack_from("<H", view, lo)[0]
    if cels == 0:
        return None
    cel = cel if cel < cels else 0
    co = struct.unpack_from("<H", view, lo + 4 + cel * 2)[0]
    w, h = struct.unpack_from("<HH", view, co)
    key = view[co + 6] & 0x0F
    if not (0 < w <= 320 and 0 < h <= 200):
        return None
    px, p = [], co + 7
    while len(px) < w * h and p < len(view):
        b = view[p]; p += 1
        px.extend([b & 0x0F] * (b >> 4))
    px = px[:w * h] + [key] * max(0, w * h - len(px))
    img = Image.new("RGBA", (w, h))
    img.putdata([(0, 0, 0, 0) if c == key else EGA[c] + (255,) for c in px])
    if mirror:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    # SCI0 screen pixels are 1.2x taller than wide at 4:3.
    return img.resize((w * scale, round(h * 1.2 * scale)), Image.NEAREST)


def best_cel(game, view_no, scale):
    """(loop, cel, image) of the cel with the most opaque pixels in the view."""
    view = game.load(T_VIEW, view_no)
    if not view or len(view) < 8:
        return 0, 0, None
    best = (0, 0, None, -1)
    for loop in range(view[0]):
        lo = struct.unpack_from("<H", view, 8 + loop * 2)[0]
        if lo + 2 > len(view):
            continue
        for cel in range(min(struct.unpack_from("<H", view, lo)[0], 16)):
            img = render(game, view_no, loop, cel, 1)
            if img is None:
                continue
            area = sum(1 for px in img.getchannel("A").getdata() if px)
            if area > best[3]:
                best = (loop, cel, img, area)
    if best[2] is None:
        return 0, 0, None
    return best[0], best[1], render(game, view_no, best[0], best[1], scale)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("game_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--render-map", help="render exactly these view/loop/cel picks instead of scanning scripts")
    a = ap.parse_args()
    game = Game(a.game_dir)
    os.makedirs(a.out_dir, exist_ok=True)
    if a.render_map:
        picks = json.load(open(a.render_map))["sprites"]
        for name, (view, loop, cel) in picks.items():
            img = render(game, view, loop, cel, a.scale)
            if img is None:
                raise SystemExit(f"{name}: view {view} loop {loop} cel {cel} does not render")
            img.save(os.path.join(a.out_dir, f"{name}.png"))
        print(f"{len(picks)} sprites -> {a.out_dir}", file=sys.stderr)
        return
    found = []
    for o in load_objects(game):
        p = o.get("props") or {}
        if o["kind"] != 1 or not p.get("view") or not o.get("name"):
            continue
        # The loop/cel an object starts with is often just the piece that animates (a talking
        # head, a mouth), so take the view's largest cel: that is the whole figure.
        loop, cel, img = best_cel(game, p["view"], a.scale)
        entry = {"script": o["script"], "object": o["name"], "class": o["className"], "view": p["view"],
                 "loop": loop, "cel": cel, "file": None}
        if img is not None and img.width >= 8 * a.scale and img.height >= 12 * a.scale:
            fname = f"{o['script']}_{o['name'].replace(' ', '_').replace('/', '_')}.png"
            img.save(os.path.join(a.out_dir, fname))
            entry["file"] = fname
        found.append(entry)
    json.dump(found, open(os.path.join(a.out_dir, "sprites.json"), "w"), indent=1)
    print(f"{len(found)} objects with a view, {sum(1 for f in found if f['file'])} sprites -> {a.out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
