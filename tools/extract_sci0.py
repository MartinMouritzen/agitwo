#!/usr/bin/env python3
"""Extract all displayable text from a Sierra SCI0 game.

Parses RESOURCE.MAP, reads resources from RESOURCE.00x volumes, decompresses
them (method 0 = none, 1 = SCI0 LZW, 2 = Huffman; algorithms ported from
ScummVM engines/sci/resource/decompressor.cpp), and extracts:
  - TEXT resources (type 3): null-separated string lists
  - SCRIPT resources (type 2): block type 5 (SCI_OBJ_STRINGS) string blocks

Usage:
    python3 extract_sci0.py <game_dir> [-o output.json] [--game-id qfg1]
"""

import argparse
import json
import os
import struct
import sys

RES_TYPE_SCRIPT = 2
RES_TYPE_TEXT = 3
SCI_OBJ_STRINGS = 5


def find_file(game_dir, name):
    for entry in os.listdir(game_dir):
        if entry.upper() == name.upper():
            return os.path.join(game_dir, entry)
    return None


# ---------------------------------------------------------------------------
# Bit readers (port of ScummVM Decompressor helpers)
# ---------------------------------------------------------------------------

class BitReader:
    """Mirrors ScummVM's Decompressor bit buffer over the packed byte range."""

    def __init__(self, src):
        self.src = src
        self.pos = 0        # bytes consumed (_dwRead)
        self.bits = 0       # _dwBits (32-bit buffer)
        self.nbits = 0      # _nBits

    def _read_byte(self):
        if self.pos < len(self.src):
            b = self.src[self.pos]
        else:
            b = 0  # reading past end returns 0, like a drained stream
        self.pos += 1
        return b

    def fetch_msb(self):
        while self.nbits <= 24:
            self.bits |= self._read_byte() << (24 - self.nbits)
            self.nbits += 8

    def get_bits_msb(self, n):
        if self.nbits < n:
            self.fetch_msb()
        ret = self.bits >> (32 - n)
        self.bits = (self.bits << n) & 0xFFFFFFFF
        self.nbits -= n
        return ret

    def fetch_lsb(self):
        while self.nbits <= 24:
            self.bits |= self._read_byte() << self.nbits
            self.bits &= 0xFFFFFFFF
            self.nbits += 8

    def get_bits_lsb(self, n):
        if self.nbits < n:
            self.fetch_lsb()
        ret = self.bits & ~(0xFFFFFFFF << n) & 0xFFFFFFFF
        self.bits >>= n
        self.nbits -= n
        return ret


# ---------------------------------------------------------------------------
# Decompressors (exact ports from ScummVM decompressor.cpp)
# ---------------------------------------------------------------------------

def unpack_none(src, unpacked_size):
    return bytes(src[:unpacked_size])


def unpack_lzw(src, unpacked_size):
    """SCI0 LZW: LSB-first codes, 9..12 bits, codes 256=reset 257=end.

    Port of DecompressorLZW::unpackLZW with _compression == kCompLZW.
    """
    br = BitReader(src)
    dest = bytearray()
    code_bit_length = 9
    table_size = 258
    code_limit = 512
    string_offsets = [0] * 4096
    string_lengths = [0] * 4096

    def finished():
        return len(dest) == unpacked_size and br.pos >= len(src)

    while not finished():
        code = br.get_bits_lsb(code_bit_length)
        if code >= table_size:
            break  # corrupt stream
        if code == 257:  # terminator
            break
        if code == 256:  # reset
            code_bit_length = 9
            table_size = 258
            code_limit = 512
            continue

        new_string_offset = len(dest)
        if code <= 255:
            dest.append(code)
        else:
            # note: length is stored as written+1; the extra byte handles the
            # KwKwK case by re-reading the byte just appended to dest
            for i in range(string_lengths[code]):
                if finished():
                    break
                dest.append(dest[string_offsets[code] + i])

        if table_size >= 4096:
            continue
        if table_size == code_limit and code_bit_length < 12:
            code_bit_length += 1
            code_limit = 1 << code_bit_length
        string_offsets[table_size] = new_string_offset
        string_lengths[table_size] = len(dest) - new_string_offset + 1
        table_size += 1

    return bytes(dest[:unpacked_size])


def unpack_huffman(src, unpacked_size):
    """Port of DecompressorHuffman::unpack / getc2."""
    if len(src) < 2:
        return b""
    num_nodes = src[0]
    terminator = src[1] | 0x100
    nodes = src[2 : 2 + (num_nodes << 1)]
    br = BitReader(src[2 + (num_nodes << 1):])
    dest = bytearray()

    def getc2():
        node = 0  # index into nodes, in node units *2
        while nodes[node + 1]:
            if br.get_bits_msb(1):
                nxt = nodes[node + 1] & 0x0F
                if nxt == 0:
                    return br.get_bits_msb(8) | 0x100
            else:
                nxt = nodes[node + 1] >> 4
            node += nxt << 1
        return nodes[node] | (nodes[node + 1] << 8)

    while len(dest) < unpacked_size:
        c = getc2()
        if c == terminator or c < 0:
            break
        dest.append(c & 0xFF)
    return bytes(dest)


# ---------------------------------------------------------------------------
# RESOURCE.MAP / RESOURCE.00x parsing (SCI0)
# ---------------------------------------------------------------------------

def read_map(game_dir):
    """6-byte entries: u16 LE id (type = id>>11, number = id & 0x7FF),
    u32 LE offset (volume = offset>>26, offset &= 0x03FFFFFF).
    Terminated by an entry with offset 0xFFFFFFFF."""
    path = find_file(game_dir, "RESOURCE.MAP")
    if path is None:
        raise FileNotFoundError("RESOURCE.MAP not found in %s" % game_dir)
    data = open(path, "rb").read()
    entries = []
    seen = set()
    for i in range(0, len(data) - 5, 6):
        rid, raw_off = struct.unpack_from("<HI", data, i)
        if raw_off == 0xFFFFFFFF:
            break
        rtype = rid >> 11
        rnum = rid & 0x7FF
        if (rtype, rnum) in seen:  # keep first occurrence, like ScummVM
            continue
        seen.add((rtype, rnum))
        entries.append((rtype, rnum, raw_off >> 26, raw_off & 0x03FFFFFF))
    return entries


def load_resource(game_dir, volume, offset, vol_cache):
    """SCI0 volume entry: {u16 id, u16 packed+4, u16 unpacked, u16 method}
    followed by (packed) bytes. Returns decompressed bytes or None."""
    if volume not in vol_cache:
        path = find_file(game_dir, "RESOURCE.%03d" % volume)
        vol_cache[volume] = open(path, "rb").read() if path else None
    vol = vol_cache[volume]
    if vol is None or offset + 8 > len(vol):
        return None
    _rid, packed, unpacked, method = struct.unpack_from("<HHHH", vol, offset)
    packed -= 4  # field counts the unpacked-size and method words
    src = vol[offset + 8 : offset + 8 + packed]
    if method == 0:
        return unpack_none(src, unpacked)
    if method == 1:
        return unpack_lzw(src, unpacked)
    if method == 2:
        return unpack_huffman(src, unpacked)
    print("warning: unsupported compression method %d at vol %d off %d"
          % (method, volume, offset), file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def is_displayable(text):
    stripped = text.strip()
    if not stripped:
        return False
    if not any(c.isalnum() for c in stripped):
        return False
    printable = sum(1 for c in text if c.isprintable() or c in "\n\t")
    return printable / len(text) >= 0.75


def split_strings(buf):
    """Yield (index, text) for each null-separated string in buf."""
    idx = 0
    for chunk in buf.split(b"\x00"):
        yield idx, chunk.decode("cp437", errors="replace")
        idx += 1


def extract_text_resource(data):
    """TEXT resource: a plain list of null-terminated strings."""
    results = []
    for idx, text in split_strings(data.rstrip(b"\x00") + b"\x00"):
        if text and is_displayable(text):
            results.append((idx, text))
    return results


def extract_script_strings(data):
    """SCI0 script: sequence of blocks {u16 type, u16 size incl. header}.
    Type 0 ends the script; type 5 holds null-terminated strings."""
    results = []
    pos = 0
    idx = 0
    while pos + 2 <= len(data):
        block_type = struct.unpack_from("<H", data, pos)[0]
        if block_type == 0:
            break
        if pos + 4 > len(data):
            break
        block_size = struct.unpack_from("<H", data, pos + 2)[0]
        if block_size < 4 or pos + block_size > len(data):
            break  # corrupt block table
        if block_type == SCI_OBJ_STRINGS:
            body = data[pos + 4 : pos + block_size]
            for chunk in body.split(b"\x00"):
                text = chunk.decode("cp437", errors="replace")
                if text:
                    if is_displayable(text):
                        results.append((idx, text))
                    idx += 1
        pos += block_size
    return results


def main():
    ap = argparse.ArgumentParser(description="Extract SCI0 text + script strings")
    ap.add_argument("game_dir", help="directory containing RESOURCE.MAP/00x")
    ap.add_argument("-o", "--output", help="output JSON path (default stdout)")
    ap.add_argument("--game-id", default="qfg1", help='value for the "game" field')
    args = ap.parse_args()

    vol_cache = {}
    out = []
    bad = 0
    for rtype, rnum, volume, offset in read_map(args.game_dir):
        if rtype not in (RES_TYPE_SCRIPT, RES_TYPE_TEXT):
            continue
        data = load_resource(args.game_dir, volume, offset, vol_cache)
        if data is None:
            bad += 1
            print("warning: %s %d (vol %d off %d) unreadable"
                  % ("script" if rtype == RES_TYPE_SCRIPT else "text",
                     rnum, volume, offset), file=sys.stderr)
            continue
        if rtype == RES_TYPE_TEXT:
            for idx, text in extract_text_resource(data):
                out.append({"game": args.game_id, "res": "text",
                            "num": rnum, "idx": idx, "text": text})
        else:
            for idx, text in extract_script_strings(data):
                out.append({"game": args.game_id, "res": "script",
                            "num": rnum, "idx": idx, "text": text})

    payload = json.dumps(out, ensure_ascii=False, indent=1)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    else:
        print(payload)

    n_text = sum(1 for m in out if m["res"] == "text")
    n_script = sum(1 for m in out if m["res"] == "script")
    print("extracted %d strings (%d from text resources, %d from scripts), "
          "%d unreadable resources" % (len(out), n_text, n_script, bad),
          file=sys.stderr)


if __name__ == "__main__":
    main()
