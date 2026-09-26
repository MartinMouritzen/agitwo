#!/usr/bin/env python3
"""Extract the talking-head portraits of a Sierra SCI1.1 game (Quest for Glory I VGA, III).

In SCI1.1 every speaking character is a Talker object: a frame view plus bust, eyes and mouth
Props that animate over it. This tool finds every Talker instance in the game's scripts, composes
its portrait the way the interpreter draws it at rest (frame, then bust, eyes and mouth on top),
and writes one PNG per talker, plus talkers.json describing what it found.

How it finds them (all ported from ScummVM engines/sci):
  - selector names come from vocab 997, the class table (class number -> script) from vocab 996
  - a heap object is 0x1234, varCount, propDict, methDict, classScript, species, superClass,
    -info-, name, then properties; which selector each variable holds comes from the class's
    propDict in the script resource (engine/script.cpp initializeObjectsSci11)
  - an object is a Talker when its class chain has the bust/eyes/mouth selectors
  - views are the SCI1.1 VGA view format with RLE + literal streams (graphics/view.cpp); the
    palette is the view's embedded one over the game's palette 999

Loose patch files (NNN.SCR, NNN.HEP, NNN.V56, NNN.PAL) override the volume copies, as in the
interpreter.

Usage: python3 extract_sci11_talkers.py <game_dir> <out_dir> [--scale 3]
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_sci11 import find_file, load_resource, read_map  # noqa: E402

T_VIEW, T_PIC, T_SCRIPT, T_VOCAB, T_PALETTE, T_HEAP = 0x00, 0x01, 0x02, 0x06, 0x0B, 0x11
PATCH_EXT = {T_VIEW: "V56", T_PIC: "P56", T_SCRIPT: "SCR", T_VOCAB: "VOC", T_PALETTE: "PAL", T_HEAP: "HEP"}


class Game:
    def __init__(self, game_dir):
        self.dir = game_dir
        self.index = read_map(find_file(game_dir, "RESOURCE.MAP"))
        self.volumes = {}

    def load(self, rtype, num):
        patch = find_file(self.dir, f"{num}.{PATCH_EXT[rtype]}")
        if patch:
            raw = open(patch, "rb").read()
            return raw[2 + raw[1]:]
        if (rtype, num) not in self.index:
            return None
        vol, off = self.index[(rtype, num)]
        if vol not in self.volumes:
            self.volumes[vol] = open(find_file(self.dir, f"RESOURCE.{vol:03d}"), "rb").read()
        return load_resource(self.volumes[vol], off)

    def numbers(self, rtype):
        nums = {n for (t, n) in self.index if t == rtype}
        for entry in os.listdir(self.dir):
            stem, ext = os.path.splitext(entry)
            if stem.isdigit() and ext[1:].upper() == PATCH_EXT[rtype]:
                nums.add(int(stem))
        return sorted(nums)


def vocab_strings(data):
    count = struct.unpack_from("<H", data, 0)[0]
    out = []
    for i in range(count):
        off = struct.unpack_from("<H", data, 2 + 2 * i)[0]
        n = struct.unpack_from("<H", data, off)[0]
        out.append(data[off + 2: off + 2 + n].decode("latin-1"))
    return out


def heap_string(heap, off):
    end = heap.find(0, off)
    return heap[off:end].decode("latin-1") if 0 <= off < len(heap) and end > off else ""


def heap_objects(heap):
    """[(offset, [vars...])] for every object in a SCI1.1 heap."""
    pos = 4 + struct.unpack_from("<H", heap, 2)[0] * 2
    out = []
    while pos + 4 <= len(heap) and struct.unpack_from("<H", heap, pos)[0] == 0x1234:
        count = struct.unpack_from("<H", heap, pos + 2)[0]
        if count < 9 or pos + count * 2 > len(heap):
            break                     # not an object header after all: end of the object list
        out.append((pos, list(struct.unpack_from(f"<{count}H", heap, pos))))
        pos += count * 2
    return out


def load_objects(game):
    selectors = vocab_strings(game.load(T_VOCAB, 997))
    sel = {name: i for i, name in enumerate(selectors)}
    classes, instances = {}, []
    for num in game.numbers(T_HEAP):
        heap, script = game.load(T_HEAP, num), game.load(T_SCRIPT, num)
        if not heap or not script:
            continue
        for off, v in heap_objects(heap):
            info, species = v[7], v[5]
            rec = {"script": num, "offset": off, "vars": v, "heap": heap, "name": heap_string(heap, v[8])}
            if info & 0x8000:     # kInfoFlagClass
                ids = list(struct.unpack_from(f"<{len(v)}H", script, v[2]))
                rec["selectors"] = ids
                classes[species] = rec
            instances.append(rec)
    for rec in instances:
        v = rec["vars"]
        cls = classes.get(v[5]) if v[7] & 0x8000 else classes.get(v[6])
        if cls and "selectors" not in rec:
            rec["selectors"] = cls["selectors"][:len(v)]
        rec["props"] = {selectors[s]: val for s, val in zip(rec.get("selectors", []), v) if s < len(selectors)}
        rec["className"] = cls["name"] if cls else "?"
    return sel, classes, instances


def chain(classes, rec):
    """Class names from the object's class up to the root."""
    names, seen = [], set()
    cur = classes.get(rec["vars"][6]) if not rec["vars"][7] & 0x8000 else rec
    while cur and cur["vars"][5] not in seen:
        seen.add(cur["vars"][5])
        names.append(cur["name"])
        cur = classes.get(cur["vars"][6])
    return names


# --- views ----------------------------------------------------------------------------------------
def parse_palette(data):
    colors = {}
    if len(data) < 37:
        return colors
    if (data[0] == 0 and data[1] == 1) or (data[0] == 0 and data[1] == 0 and struct.unpack_from("<H", data, 29)[0] == 0):
        fmt, off, start, count = 0, 260, 0, 256
    else:
        fmt, off, start, count = data[32], 37, data[25], struct.unpack_from("<H", data, 29)[0]
    for c in range(start, min(256, start + count)):
        if fmt == 1:
            if off + 3 > len(data):
                break
            colors[c] = tuple(data[off:off + 3]); off += 3
        else:
            if off + 4 > len(data):
                break
            colors[c] = tuple(data[off + 1:off + 4])
            off += 4
    return colors


def is_vga11(view):
    """SCI1.1 views start with a header size word; SCI1 VGA views start with the loop count byte
    and a flags byte (PQ1 VGA pairs SCI1.1 messages with SCI1 views, so both occur)."""
    header = struct.unpack_from("<H", view, 0)[0] + 2
    return 16 <= header <= 64 and len(view) > 14 and view[12] >= 16 and view[13] >= 32


def decode_cel_vga(view, loop, cel):
    """SCI1 VGA view (ScummVM kViewVga): LoopCount:BYTE Flags:BYTE Mirror:WORD Version:WORD
    PaletteOffset:WORD LoopOffsets..., loops are CelCount:WORD ?:WORD CelOffsets..., cels are
    Width:WORD Height:WORD DisplaceX:BYTE DisplaceY:BYTE ClearKey:BYTE ?:BYTE then RLE data."""
    loops = view[0]
    compressed = not (view[1] & 0x40)
    mirror_bits = struct.unpack_from("<H", view, 2)[0]
    pal_off = struct.unpack_from("<H", view, 6)[0]
    loop = loop if loop < loops else 0
    mirror = bool((mirror_bits >> loop) & 1)
    lo = struct.unpack_from("<H", view, 8 + loop * 2)[0]
    count = struct.unpack_from("<H", view, lo)[0]
    cel = cel if cel < count else 0
    co = struct.unpack_from("<H", view, lo + 4 + cel * 2)[0]
    w, h = struct.unpack_from("<HH", view, co)
    dx, dy = struct.unpack_from("<bB", view, co + 4)
    key = view[co + 6]
    n = w * h
    if not compressed:
        px = bytearray(view[co + 8: co + 8 + n])
    else:
        px = bytearray([key]) * n
        r, i = co + 8, 0
        while i < n and r < len(view):
            b = view[r]; r += 1
            run, kind = b & 0x3F, b & 0xC0
            if kind in (0x00, 0x40):
                run = min(run + (64 if kind == 0x40 else 0), n - i)
                px[i:i + run] = view[r:r + run]; r += run
            elif kind == 0x80:
                run = min(run, n - i)
                px[i:i + run] = bytes([view[r]]) * run; r += 1
            else:
                run = min(run, n - i)
            i += run
    if mirror:
        px = bytearray(b"".join(bytes(px[y * w:(y + 1) * w][::-1]) for y in range(h)))
        dx = -dx
    pal = parse_palette(view[pal_off:]) if pal_off and pal_off != 0x100 else {}
    return w, h, dx, dy, key, bytes(px), pal


def decode_cel(view, loop, cel):
    """(width, height, displaceX, displaceY, clearKey, pixels, palette) for one cel."""
    if not is_vga11(view):
        return decode_cel_vga(view, loop, cel)
    header = struct.unpack_from("<H", view, 0)[0] + 2
    loops = view[2]
    pal_off = struct.unpack_from("<I", view, 8)[0]
    loop_size, cel_size = view[12], view[13]
    if loop >= loops:
        loop = 0
    ld = header + loop * loop_size
    mirror = False
    while view[ld] != 255:
        mirror = True
        ld = header + view[ld] * loop_size
    count = view[ld + 2]
    if cel >= count:
        cel = 0
    cd = struct.unpack_from("<I", view, ld + 12)[0] + cel * cel_size
    w, h, dx, dy = struct.unpack_from("<hhhh", view, cd)
    if dy < 0:
        dy += 255
    key = view[cd + 8]
    rle, lit = struct.unpack_from("<II", view, cd + 24)
    if rle and not lit:
        rle, lit = lit, rle
    n = w * h
    px = bytearray([key]) * n
    if rle == 0:
        px[:] = view[lit:lit + n]
    else:
        r, l, i = rle, lit, 0
        while i < n:
            b = view[r]; r += 1
            run = b & 0x3F
            kind = b & 0xC0
            if kind in (0x00, 0x40):
                if kind == 0x40:
                    run += 64
                run = min(run, n - i)
                if lit:
                    px[i:i + run] = view[l:l + run]; l += run
                else:
                    px[i:i + run] = view[r:r + run]; r += run
            elif kind == 0x80:
                run = min(run, n - i)
                if lit:
                    c = view[l]; l += 1
                else:
                    c = view[r]; r += 1
                px[i:i + run] = bytes([c]) * run
            else:
                run = min(run, n - i)
            i += run
    if mirror:
        px = bytearray(b"".join(bytes(px[y * w:(y + 1) * w][::-1]) for y in range(h)))
        dx = -dx
    return w, h, dx, dy, key, bytes(px), parse_palette(view[pal_off:]) if pal_off else {}


def misplaced(img, layer, pos):
    """True when an eye/mouth layer would land on solid frame pixels it does not match: the frame
    already holds that feature and the layer's position is wrong (PQ1 VGA's Marie). Layers that
    fill a transparent hole, or that repaint the same pixels, are fine."""
    ip, lp = img.load(), layer.load()
    solid = diff = n = 0
    under = {}
    for y in range(0, layer.height, 2):
        for x in range(0, layer.width, 2):
            if lp[x, y][3] == 0:
                continue
            X, Y = pos[0] + x, pos[1] + y
            if not (0 <= X < img.width and 0 <= Y < img.height):
                continue
            n += 1
            if ip[X, Y][3]:
                solid += 1
                diff += sum(abs(a - b) for a, b in zip(ip[X, Y][:3], lp[x, y][:3])) / 3
                under[ip[X, Y][:3]] = under.get(ip[X, Y][:3], 0) + 1
    # A layer over a plain backdrop (QFG3's aardvark snout) is where it belongs.
    backdrop = solid and max(under.values()) > 0.4 * solid
    return n and solid > 0.95 * n and diff / solid > 40 and not backdrop


def compose(game, parts, base_pal, scale):
    """Draw [(view, loop, cel, left, top)] in order onto one RGBA image.

    Talkers draw their frame and features with DrawCel at fixed top-left positions (the frame at
    0,0, the eyes and mouth at their nsLeft/nsTop), not by the bottom-centre anchor Views use."""
    from PIL import Image
    layers = []
    for view_no, loop, cel, left, top in parts:
        view = game.load(T_VIEW, view_no)
        if not view:
            continue
        w, h, dx, dy, key, px, pal = decode_cel(view, loop, cel)
        palette = dict(base_pal)
        palette.update(pal)
        layers.append((left, top, w, h, key, px, palette))
    if not layers:
        return None
    x0 = min(l[0] for l in layers); y0 = min(l[1] for l in layers)
    x1 = max(l[0] + l[2] for l in layers); y1 = max(l[1] + l[3] for l in layers)
    img = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    for i, (left, top, w, h, key, px, palette) in enumerate(layers):
        layer = Image.new("RGBA", (w, h))
        layer.putdata([(0, 0, 0, 0) if c == key else palette.get(c, (255, 0, 255)) + (255,) for c in px])
        if i and misplaced(img, layer, (left - x0, top - y0)):
            continue
        img.alpha_composite(layer, (left - x0, top - y0))
    # SCI draws on a 320x200 screen shown at 4:3, so every pixel is 1.2x taller than wide.
    return img.resize((img.width * scale, round(img.height * 1.2 * scale)), Image.NEAREST)


def signed(v):
    return v - 0x10000 if v >= 0x8000 else v


def cel_width(game, part):
    view = game.load(T_VIEW, part[0])
    if not view:
        return None
    try:
        return decode_cel(view, part[1], part[2])[0]
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("game_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--scale", type=int, default=3)
    a = ap.parse_args()
    game = Game(a.game_dir)
    base_pal = parse_palette(game.load(T_PALETTE, 999) or b"")
    sel, classes, objs = load_objects(game)
    by_offset = {(o["script"], o["offset"]): o for o in objs}
    os.makedirs(a.out_dir, exist_ok=True)
    found = []
    for o in objs:
        p = o.get("props", {})
        if o["vars"][7] & 0x8000 or not {"bust", "eyes", "mouth"} <= set(p):
            continue
        if not p.get("view"):
            continue
        # bust/eyes/mouth are only filled in at runtime (Talker init:), so find the features the
        # way the scripts do: Props in the same script drawn from the talker's own view.
        parts = [(p["view"], p.get("loop", 0), p.get("cel", 0), 0, 0)]
        for q in objs:
            qp = q.get("props", {})
            if (q["script"] == o["script"] and q is not o and "Prop" in chain(classes, q)
                    and qp.get("view") == p["view"]
                    and qp.get("loop", 0) != p.get("loop", 0)):
                parts.append((qp["view"], qp.get("loop", 0), qp.get("cel", 0), signed(qp.get("nsLeft", 0)), signed(qp.get("nsTop", 0))))
        # Eyes and mouths are small patches. A feature-sized Prop as big as the frame is an
        # alternate pose used by a cutscene, and pasting it on top doubles the face.
        frame_w = cel_width(game, parts[0])
        parts = parts[:1] + [pt for pt in parts[1:] if frame_w is None or cel_width(game, pt) < frame_w * 0.5]
        # A portrait's colours are resolved against the screen palette of the room it talks in:
        # palette 999, then the room picture's palette, then the view's own entries on top.
        palette = dict(base_pal)
        pic = game.load(T_PIC, o["script"])
        if pic and len(pic) > 32:
            palette.update(parse_palette(pic[struct.unpack_from("<I", pic, 28)[0]:]))
        entry = {"script": o["script"], "object": o["name"], "class": o["className"], "chain": chain(classes, o),
                 "parts": parts, "file": None}
        try:
            img = compose(game, parts, palette, a.scale)
        except Exception as e:     # a malformed part should not stop the other talkers
            entry["error"] = str(e)
            img = None
        if img is not None and img.width < 60 * a.scale:
            # In-scene talkers (no bust, just a mouth animated on the room background) have no
            # portrait; their frame view is a few pixels of mouth.
            entry["skipped"] = "in-scene talker, no portrait"
            img = None
        if img is not None:
            fname = f"{o['script']}_{o['name'].replace(' ', '_')}.png"
            img.save(os.path.join(a.out_dir, fname))
            entry["file"] = fname
        found.append(entry)
    json.dump(found, open(os.path.join(a.out_dir, "talkers.json"), "w"), indent=1)
    print(f"{len(found)} talkers, {sum(1 for f in found if f['file'])} portraits -> {a.out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
