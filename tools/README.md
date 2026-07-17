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

## Notes

- Strings are decoded as cp437; empty and non-human-readable (mostly
  non-printable) strings are filtered out, everything else is kept verbatim,
  including single words (SCI script string blocks also contain object/class
  names, which are kept).
- Generated manifests live in `../text/pq1-messages.json` and
  `../text/qfg1-messages.json`.
