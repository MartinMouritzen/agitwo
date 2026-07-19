#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -z "$(ls -A game 2>/dev/null)" ]; then
  echo "Put your Quest for Glory 1 EGA files into the 'game' folder, then run this again."
  exit 1
fi
./scummvm --extrapath="$(pwd)/agitwo-voices" -p game --auto-detect
