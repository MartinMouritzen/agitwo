#!/usr/bin/env bash
# Assemble a per-platform "QFG1 Voiced Edition" bundle from a CI engine artifact.
# Usage: tools/make_bundle.sh <win|linux|mac> <path-to-engine-dir>
set -euo pipefail
OS="$1"; ENGINE="$2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VOICES="$ROOT/dist/voicepack/qfg1/agitwo-voices"
OUT="$ROOT/dist/out/QFG1-Voiced-$OS"
rm -rf "$OUT"; mkdir -p "$OUT/game"
cp -R "$ENGINE"/. "$OUT"/
cp -R "$VOICES" "$OUT/agitwo-voices"
cp "$ROOT/dist/pkg/common/README.txt" "$OUT/README.txt"
: > "$OUT/game/PUT-YOUR-QFG1-EGA-FILES-HERE.txt"
case "$OS" in
  win)   cp "$ROOT/dist/pkg/win-launcher.bat"     "$OUT/Play QFG1 (Voiced).bat" ;;
  linux) cp "$ROOT/dist/pkg/linux-launcher.sh"    "$OUT/play-qfg1-voiced.sh"; chmod +x "$OUT/play-qfg1-voiced.sh" ;;
  mac)   cp "$ROOT/dist/pkg/mac-launcher.command" "$OUT/Play QFG1 (Voiced).command"; chmod +x "$OUT/Play QFG1 (Voiced).command" ;;
esac
( cd "$ROOT/dist/out" && zip -qr "QFG1-Voiced-$OS.zip" "QFG1-Voiced-$OS" )
echo "built: dist/out/QFG1-Voiced-$OS.zip ($(du -h "$ROOT/dist/out/QFG1-Voiced-$OS.zip" | cut -f1))"
