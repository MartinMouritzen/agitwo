# Sierra game text extractors

Two standalone Python 3 tools (no dependencies) that extract every displayable
message string from Sierra games and write JSON manifests.

## extract_agi.py (AGI v2, e.g. Police Quest 1)

Parses `LOGDIR` (3-byte entries: volume nibble + 20-bit big-endian offset),
reads each LOGIC resource from `VOL.n` (5-byte header: `0x1234` magic BE,
volume byte, length LE), and decodes the message section at
`2 + bytecode_size`: count byte, section size word, offset table (relative to
message section + 1), then null-terminated strings XOR-decrypted with the
repeating key `"Avis Durgan"`.

```
python3 extract_agi.py <game_dir> [-o out.json] [--game-id pq1]
```

Output records: `{"game", "logic": <logic number>, "msg": <1-based>, "text"}`

## extract_sci0.py (SCI0, e.g. Quest for Glory 1 EGA)

Parses `RESOURCE.MAP` (6-byte entries: u16 LE id = type(5 bits)<<11 |
number(11 bits); u32 LE = volume(6 bits)<<26 | offset(26 bits); terminated by
offset `0xFFFFFFFF`), reads resources from `RESOURCE.00x` (8-byte header:
u16 id, u16 packed size + 4, u16 unpacked size, u16 method) and decompresses
method 0 (store), 1 (SCI0 LZW, LSB-first 9-12 bit codes) and 2 (Huffman),
ported from ScummVM `engines/sci/resource/decompressor.cpp`. Extracts:

- TEXT resources (type 3): null-separated string lists
- SCRIPT resources (type 2): SCI0 block streams (u16 type, u16 size incl.
  header, type 0 = end); block type 5 holds null-separated strings

```
python3 extract_sci0.py <game_dir> [-o out.json] [--game-id qfg1]
```

Output records: `{"game", "res": "text"|"script", "num": <resource number>,
"idx": <0-based string index within the resource>, "text"}`

### SCI01 / SCI1-early games (e.g. Quest for Glory II)

The same tool reads them. The map's volume field is 4 bits instead of 6 (picked by checking that
every entry's volume header carries the id the map claims), and compression methods are numbered
differently: 1 = Huffman, 2 = LZW1 (most-significant-bit first, "early change" code size). The
numbering is detected by decoding the text resources both ways.

## extract_sci1.py (SCI1 text games, e.g. Police Quest III)

TEXT resources and SCI0-style script strings, read through the SCI1 map (type-offset header,
6-byte entries) and 9-byte volume headers; compression 0, 1 (Huffman), 2 (LZW1), 3 (LZW1View,
ported from ScummVM reorderView) and 18-20 (DCL). Same output records as extract_sci0.py.

```
python3 extract_sci1.py <game_dir> [-o out.json] [--game-id pq3]
```

## extract_sci11.py (SCI1 late / SCI1.1 message games, e.g. QFG1 VGA, QFG3)

Reads MESSAGE resources (from `RESOURCE.MAP` or a separate `MESSAGE.MAP` + `RESOURCE.MSG`),
decompresses DCL (methods 18-20), parses message versions 3 and 4, and lets loose `NNN.MSG`
patch files (e.g. the NRS fan patch) override the volume copies. Every record keeps its tuple
(room, noun, verb, cond, seq) and its talker id, which names the speaker.

```
python3 extract_sci11.py <game_dir> [-o out.json] [--game-id qfg1vga]
```

## extract_sci11_talkers.py (talking-head portraits)

Finds every Talker object in the scripts (selectors from vocab 997, class table from vocab 996,
SCI1.1 heap objects) and composes its portrait: the frame view, with the eyes and mouth Props
from the same script drawn at their nsLeft/nsTop. Colours come from palette 999, then the room
picture's palette, then the view's own palette. Writes one PNG per talker plus `talkers.json`.

```
python3 extract_sci11_talkers.py <game_dir> <out_dir> [--scale 3]
```

## extract_sci0_sprites.py (SCI0 character sprites)

Renders every named script object's view (the largest cel, since the starting cel is often only
the animated head) from SCI0 EGA views, or SCI1 VGA views with palette 999. `--render-map` renders
hand-picked view/loop/cel choices; `--compose-map` composes inset portraits from named room
objects (Police Quest III). Writes one PNG per object plus `sprites.json`, so
characters can be matched to sprites by name.

```
python3 extract_sci0_sprites.py <game_dir> <out_dir> [--scale 4]
```

Output from all of these is verbatim game data: keep it out of this public repo (the Voice Lab
keeps it in the private `games/<id>/source/`).

## Notes

- Strings are decoded as cp437; empty and non-human-readable (mostly
  non-printable) strings are filtered out, everything else is kept verbatim,
  including single words (SCI script string blocks also contain object/class
  names, which are kept).
- Generated manifests live in `../text/pq1-messages.json` and
  `../text/qfg1-messages.json`.
