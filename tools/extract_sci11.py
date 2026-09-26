#!/usr/bin/env python3
"""Extract every message from a Sierra SCI1 / SCI1.1 game that uses the message system.

Quest for Glory I VGA and Quest for Glory III (and most 1991-1993 Sierra games) keep their
dialogue in MESSAGE resources (type 0x8F). Unlike SCI0 text resources, each message is addressed
by a tuple (room, noun, verb, cond, seq) and names its TALKER, the object that displays it, so
speaker attribution comes with the data instead of having to be inferred by reading.

Handles:
  - RESOURCE.MAP with 6-byte entries (u16 number, u32 volume<<28|offset; "SCI1 late", e.g. QFG1
    VGA 2.000) or 5-byte entries (u16 number, u24 offset>>1; SCI1.1, e.g. QFG3 1.1)
  - MESSAGE.MAP + RESOURCE.MSG, where SCI1.1 games keep messages in a volume of their own
  - 9-byte volume headers (type, number, packed, unpacked, method); method 0 (stored) and
    18/19/20 (DCL implode)
  - message resource versions 3 (8-byte header, 10-byte records) and 4 (10-byte header, 11-byte
    records with a reference tuple)
  - loose patch files (NNN.MSG), which override the volume copy exactly as the interpreter does;
    fan patches such as NRS ship some of these

The DCL decompressor and the message record layouts are ported from ScummVM
(common/compression/dcl.cpp, engines/sci/engine/message.cpp).

Usage:
    python3 extract_sci11.py <game_dir> [-o out.json] [--game-id qfg1vga]

Output records: {"room", "noun", "verb", "cond", "seq", "talker", "ref": [n, v, c] | null,
"text", "source": "volume" | "patch"}
"""

import argparse
import json
import os
import struct
import sys

RES_TYPE_MESSAGE = 0x0F   # stored in maps as 0x80 | type

# Huffman trees from ScummVM's DCL decompressor. A value >= 0 is a branch node,
# (left << 12) | right; a value < 0 is a leaf holding -1 - symbol.
_LENGTH_TREE = [
    4098, 12292, 20486, 28680, 36874, 45068, -2, 53262, 61456, 69650, -4, -3, -1, 77844, 86038,
    94232, -7, -6, -5, 102426, 110620, -11, -10, -9, -8, 118814, -14, -13, -12, -16, -15
]
_DISTANCE_TREE = [
    4098, 12292, 20486, 28680, 36874, 45068, -1, 53262, 61456, 69650, 77844, 86038, 94232,
    102426, 110620, 118814, 127008, 135202, 143396, 151590, 159784, 167978, 176172, -3, -2,
    184366, 192560, 200754, 208948, 217142, 225336, 233530, 241724, 249918, 258112, 266306,
    274500, 282694, 290888, 299082, 307276, -7, -6, -5, -4, 315470, 323664, 331858, 340052,
    348246, 356440, 364634, 372828, 381022, 389216, 397410, 405604, 413798, 421992, 430186,
    438380, 446574, -22, -21, -20, -19, -18, -17, -16, -15, -14, -13, -12, -11, -10, -9, -8,
    454768, 462962, 471156, 479350, 487544, 495738, 503932, 512126, -48, -47, -46, -45, -44,
    -43, -42, -41, -40, -39, -38, -37, -36, -35, -34, -33, -32, -31, -30, -29, -28, -27, -26,
    -25, -24, -23, -64, -63, -62, -61, -60, -59, -58, -57, -56, -55, -54, -53, -52, -51, -50,
    -49
]
_ASCII_TREE = [
    4098, 12292, 20486, 28680, 36874, 45068, 53262, 61456, 69650, 77844, 86038, 94232, 102426,
    110620, 118814, 127008, 135202, 143396, 151590, 159784, 167978, 176172, 184366, 192560,
    200754, 208948, 217142, 225336, 233530, 241724, -33, 249918, 258112, 266306, 274500, 282694,
    290888, 299082, 307276, 315470, 323664, 331858, 340052, 348246, 356440, 364634, 372828,
    381022, 389216, 397410, -118, -117, -116, -115, -112, -111, -109, -106, -102, -98, -70,
    405604, 413798, 421992, 430186, 438380, 446574, 454768, 462962, 471156, 479350, 487544,
    495738, 503932, 512126, 520320, 528514, 536708, 544902, -113, -110, -105, -104, -103, -101,
    -100, -99, -85, -84, -83, -80, -79, -77, -74, -69, -68, -66, -50, -46, 553096, 561290,
    569484, 577678, 585872, 594066, 602260, 610454, 618648, 626842, 635036, 643230, 651424,
    659618, 667812, -120, -108, -86, -81, -78, -71, -67, -62, -57, -56, -54, -53, -52, -51, -49,
    -47, -45, -42, -41, -14, -11, 676006, 684200, 692394, 700588, 708782, 716976, 725170,
    733364, 741558, 749752, 757946, 766140, 774334, 782528, -122, -121, -119, -96, -92, -88,
    -73, -72, -59, -58, -55, -48, -43, -40, -35, -10, 790722, 798916, 807110, 815304, 823498,
    831692, 839886, 848080, 856274, 864468, 872662, 880856, 889050, 897244, 905438, 913632,
    921826, 930020, 938214, 946408, 954602, -94, -90, -89, -87, -76, -63, -44, 962796, 970990,
    979184, 987378, 995572, 1003766, 1011960, 1020154, 1028348, 1036542, 1044736, 1052930,
    1061124, 1069318, 1077512, 1085706, 1093900, 1102094, 1110288, 1118482, 1126676, 1134870,
    1143064, 1151258, 1159452, 1167646, 1175840, 1184034, 1192228, 1200422, 1208616, 1216810,
    1225004, 1233198, 1241392, 1249586, 1257780, -123, -114, -39, -37, -34, 1265974, 1274168,
    1282362, 1290556, 1298750, 1306944, 1315138, 1323332, 1331526, 1339720, 1347914, 1356108,
    1364302, 1372496, 1380690, 1388884, 1397078, 1405272, 1413466, 1421660, 1429854, 1438048,
    1446242, 1454436, 1462630, 1470824, 1479018, 1487212, 1495406, 1503600, 1511794, 1519988,
    1528182, 1536376, 1544570, 1552764, 1560958, 1569152, 1577346, 1585540, 1593734, 1601928,
    1610122, 1618316, 1626510, 1634704, 1642898, 1651092, 1659286, 1667480, 1675674, 1683868,
    1692062, 1700256, 1708450, 1716644, 1724838, 1733032, 1741226, 1749420, 1757614, 1765808,
    1774002, 1782196, -125, -124, -107, -93, -91, -82, -75, -64, -61, -1, 1790390, 1798584,
    1806778, 1814972, 1823166, 1831360, 1839554, 1847748, 1855942, 1864136, 1872330, 1880524,
    1888718, 1896912, 1905106, 1913300, 1921494, 1929688, 1937882, 1946076, 1954270, 1962464,
    1970658, 1978852, 1987046, 1995240, 2003434, 2011628, 2019822, 2028016, 2036210, 2044404,
    2052598, 2060792, 2068986, 2077180, 2085374, -245, -244, -243, -239, -234, -230, -226, -224,
    -223, -222, -221, -220, -219, -218, -217, -216, -215, -214, -213, -212, -211, -210, -209,
    -208, -207, -206, -205, -204, -203, -202, -201, -200, -199, -198, -197, -196, -195, -194,
    -193, -192, -191, -190, -189, -188, -187, -186, -185, -184, -183, -182, -181, -180, -179,
    -178, -177, -128, -127, -126, -97, -95, -65, -60, -38, -36, -32, -31, -30, -29, -28, -26,
    -25, -24, -23, -22, -21, -20, -19, -18, -17, -16, -15, -13, -12, -9, -8, -7, -6, -5, -4, -3,
    -2, -256, -255, -254, -253, -252, -251, -250, -249, -248, -247, -246, -242, -241, -240,
    -238, -237, -236, -235, -233, -232, -231, -229, -228, -227, -225, -176, -175, -174, -173,
    -172, -171, -170, -169, -168, -167, -166, -165, -164, -163, -162, -161, -160, -159, -158,
    -157, -156, -155, -154, -153, -152, -151, -150, -149, -148, -147, -146, -145, -144, -143,
    -142, -141, -140, -139, -138, -137, -136, -135, -134, -133, -132, -131, -130, -129, -27
]


def _explode(data, unpacked_size):
    """DCL implode decompression (PKWare DCL, as used by SCI1.1 methods 18-20)."""
    state = {"bits": 0, "n": 0, "pos": 0}

    def bits(n):
        while state["n"] < n:
            b = data[state["pos"]] if state["pos"] < len(data) else 0
            state["bits"] |= b << state["n"]
            state["n"] += 8
            state["pos"] += 1
        r = state["bits"] & ((1 << n) - 1)
        state["bits"] >>= n
        state["n"] -= n
        return r

    def huff(tree):
        pos = 0
        while tree[pos] >= 0:
            pos = (tree[pos] & 0xFFF) if bits(1) else (tree[pos] >> 12)
        return -1 - tree[pos]

    mode, dict_type = bits(8), bits(8)
    if mode not in (0, 1) or dict_type not in (4, 5, 6):
        raise ValueError(f"DCL: bad stream header mode={mode} dict={dict_type}")
    out = bytearray()
    while len(out) < unpacked_size:
        if bits(1):
            v = huff(_LENGTH_TREE)
            length = v + 2 if v < 8 else 8 + (1 << (v - 7)) + bits(v - 7)
            if length == 519:
                break
            v = huff(_DISTANCE_TREE)
            dist = ((v << 2) | bits(2)) if length == 2 else ((v << dict_type) | bits(dict_type))
            dist += 1
            if dist > len(out):
                raise ValueError("DCL: copy from before the start of the output")
            for _ in range(length):
                out.append(out[-dist])
        else:
            out.append(huff(_ASCII_TREE) if mode == 1 else bits(8))
    if len(out) != unpacked_size:
        raise ValueError(f"DCL: produced {len(out)} bytes, expected {unpacked_size}")
    return bytes(out)


def find_file(game_dir, name):
    for entry in os.listdir(game_dir):
        if entry.upper() == name.upper():
            return os.path.join(game_dir, entry)
    return None


def read_map(path):
    """Return {(type, number): (volume, offset)} for a SCI1/SCI1.1 resource map."""
    m = open(path, "rb").read()
    types, i = [], 0
    while True:
        t, off = m[i], struct.unpack_from("<H", m, i + 1)[0]
        types.append((t, off))
        i += 3
        if t == 0xFF:
            break
    spans = [(t, o, o2) for (t, o), (_, o2) in zip(types, types[1:])]
    # Entry size is not stored. Every type's span must be a whole number of entries, which
    # tells the two layouts apart (checked against both QFG1 VGA and QFG3).
    entry = next((e for e in (6, 5) if all((o2 - o) % e == 0 for _, o, o2 in spans)), None)
    if entry is None:
        raise ValueError(f"{path}: cannot determine map entry size")
    res = {}
    for t, o, o2 in spans:
        for p in range(o, o2, entry):
            num = struct.unpack_from("<H", m, p)[0]
            if entry == 6:
                raw = struct.unpack_from("<I", m, p + 2)[0]
                res[(t & 0x7F, num)] = (raw >> 28, raw & 0x0FFFFFFF)
            else:
                res[(t & 0x7F, num)] = (0, (m[p + 2] | m[p + 3] << 8 | m[p + 4] << 16) << 1)
    return res


def load_resource(volume_bytes, offset):
    rtype, num, packed, unpacked, method = struct.unpack_from("<BHHHH", volume_bytes, offset)
    data = volume_bytes[offset + 9: offset + 9 + packed]
    if method == 0:
        return data[:unpacked]
    if method in (18, 19, 20):
        return _explode(data, unpacked)
    # From SCI1 on, method 1 is Huffman and 2 is LZW1 (ScummVM Resource::readResourceInfo);
    # PQ1 VGA stores its messages this way. The decoders live in extract_sci0.py.
    if method in (1, 2):
        import extract_sci0
        if method == 1:
            return extract_sci0.unpack_huffman(data, unpacked)
        return extract_sci0.unpack_lzw(data, unpacked, lzw1=True)
    raise ValueError(f"resource {rtype:#x}/{num}: unsupported compression {method}")


def parse_messages(data, room):
    version = struct.unpack_from("<I", data, 0)[0] // 1000
    if version == 3:
        header, record = 8, 10
    elif version == 4:
        header, record = 10, 11
    else:
        raise ValueError(f"message {room}: unsupported version {version}")
    count = struct.unpack_from("<H", data, header - 2)[0]
    out = []
    for i in range(count):
        p = header + i * record
        noun, verb, cond, seq, talker = data[p:p + 5]
        so = struct.unpack_from("<H", data, p + 5)[0]
        end = data.find(0, so)
        raw = data[so:end if end >= 0 else len(data)].rstrip(b"\xff")
        ref = None
        if version == 4 and any(data[p + 7:p + 10]):
            ref = list(data[p + 7:p + 10])
        out.append({"room": room, "noun": noun, "verb": verb, "cond": cond, "seq": seq,
                    "talker": talker, "ref": ref, "text": raw.decode("cp437")})
    return out


def extract(game_dir):
    msg_map = find_file(game_dir, "MESSAGE.MAP")
    if msg_map:
        index = read_map(msg_map)
        volumes = {0: open(find_file(game_dir, "RESOURCE.MSG"), "rb").read()}
    else:
        index = read_map(find_file(game_dir, "RESOURCE.MAP"))
        volumes = {}
    records, rooms = [], set()
    for (rtype, num), (vol, off) in sorted(index.items()):
        if rtype != RES_TYPE_MESSAGE:
            continue
        # A loose patch file wins over the volume copy, as it does in the interpreter.
        patch = find_file(game_dir, f"{num}.MSG")
        if patch:
            continue
        if vol not in volumes:
            volumes[vol] = open(find_file(game_dir, f"RESOURCE.{vol:03d}"), "rb").read()
        for r in parse_messages(load_resource(volumes[vol], off), num):
            r["source"] = "volume"
            records.append(r)
        rooms.add(num)
    for entry in sorted(os.listdir(game_dir)):
        stem, ext = os.path.splitext(entry)
        if ext.upper() != ".MSG" or not stem.isdigit():
            continue
        raw = open(os.path.join(game_dir, entry), "rb").read()
        if raw[0] & 0x7F != RES_TYPE_MESSAGE:
            continue
        for r in parse_messages(raw[2 + raw[1]:], int(stem)):
            r["source"] = "patch"
            records.append(r)
    records.sort(key=lambda r: (r["room"], r["noun"], r["verb"], r["cond"], r["seq"]))
    return records


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("game_dir")
    ap.add_argument("-o", "--output")
    ap.add_argument("--game-id", default="")
    a = ap.parse_args()
    records = extract(a.game_dir)
    for r in records:
        r["game"] = a.game_id
    text = json.dumps(records, ensure_ascii=False, indent=1)
    if a.output:
        open(a.output, "w").write(text + "\n")
        print(f"{len(records)} messages -> {a.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
