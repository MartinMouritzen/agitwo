#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -z "$(ls -A game 2>/dev/null)" ]; then
  echo "Put your Quest for Glory 1 EGA files into the 'game' folder, then run this again."
  exit 1
fi
export LD_LIBRARY_PATH="$(pwd)/lib:$LD_LIBRARY_PATH"

CFG="$PWD/scummvm.ini"
VOICES="$PWD/agitwo-voices"

play() { ./scummvm --config="$CFG" --extrapath="$VOICES" -p game --auto-detect; }

configure() {
  # Make sure the game is listed in the launcher so per-game options can be set.
  targets=$(grep -E '^\[' "$CFG" 2>/dev/null | grep -vi '^\[scummvm\]' | wc -l)
  if [ "$targets" -eq 0 ]; then
    ./scummvm --config="$CFG" --add -p game >/dev/null 2>&1
  fi
  ./scummvm --config="$CFG" --extrapath="$VOICES"
}

# No terminal attached (double-clicked from a file manager)? Just play.
if [ ! -t 0 ]; then play; exit 0; fi

while true; do
  printf '\n  Quest for Glory I - Voiced Edition\n\n'
  printf '  1. Play QFG1 Voiced\n  2. Configure ScummVM  (graphics, audio, scalers)\n  3. Exit\n\n'
  printf '  Select an option: '
  read -r choice
  case "$choice" in
    1) play; exit 0 ;;
    2) configure ;;
    3) exit 0 ;;
  esac
done
