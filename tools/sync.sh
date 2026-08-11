#!/usr/bin/env bash
# QFG1 sync, run by the Voice Lab's "sync" button (games/qfg1ega/game.json).
#
# The lab runs a game's sync entry with `bash <path>`. This game.json used to point
# straight at tools/gen_voice_manifest.py, so the lab was running a Python file through
# bash: bash reads the module docstring's `"""` as an unterminated quote and blocks on
# stdin forever, which surfaced in the header as a sync failure. Every other game points
# at a .sh, so this now does too.
#
# The lab looks for the word SYNCED in the output to decide success.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== promoting the lab's selected takes onto their game clips"
python3 tools/promote_takes.py --write

echo "== rebuilding the manifest and syncing every pack"
python3 tools/build_voicepack.py --write

echo "SYNCED qfg1"
