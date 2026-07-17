# agitwo

Play early Sierra adventure games with AI voice-overs, one fixed voice per character. Built on a patched ScummVM.

Currently covers:

- **Quest for Glory I: So You Want To Be A Hero** (SCI0 / EGA, 1989) - **fully voiced**, ~3,800 lines across ~40 characters plus narrator.
- **Police Quest: In Pursuit of the Death Angel** (AGI / EGA, 1987) - pilot voices (30 lines), full coverage pending.

The engine, the extraction/tagging tools, and the voice-generation pipeline all live here. The game data and the generated audio do **not** (see "Distribution & legal").

## How it works

1. Every message the game displays is funneled through a hook we add to ScummVM's AGI and SCI engines (`AgiEngine::sayText`, `SciTTS::text/button`).
2. The hook normalizes the text (collapse whitespace), hashes it (64-bit FNV-1a), and looks the hash up in a per-game manifest (`manifest.json`: hash -> clip filename). The manifest contains **no game text**, only hashes.
3. On a hit it plays the matching clip and suppresses the engine's own text-to-speech.
   - **Browser build (Emscripten/WASM):** playback via the page's `agitwoPlayVoice()` and HTML5 Audio (`common/voiceover.cpp`, `dists/emscripten/custom_shell.html`).
   - **Native build:** playback through ScummVM's own audio mixer (`audio/agitwo_voiceover.cpp`), loading `agitwo-voices/manifest.json` + clips from next to the game.

Clips are generated once from the extracted text and are keyed by the same hash everywhere, so a clip made for the browser also works native.

## Repository layout

- `patches/agitwo-scummvm.patch` - all our ScummVM engine changes (voice hook, native + browser playback, an upstream-worthy `rate.cpp` fix, an SDL3 keyboard fix). Base: ScummVM master `e5af35640de1b3c3a1969720b71d19d853677315`.
- `patches/sdl3-emscripten-keyboard-leak.patch` - fix applied inside the emsdk SDL3 port (see below).
- `tools/extract_agi.py`, `tools/extract_sci0.py` - dump every message from the games with script/room context.
- `tools/gen_voice_manifest.py` - turn a voice-lines file into a hash->clip manifest. Its normalization + hash must match `voiceover.cpp`.
- `voices-src/` - the casting and speaker-tagging work: which character says each line, and which catalog voice plays them.
- `text/` - extracted message dumps (game-derived; regenerable with the tools).
- `web/` - landing page for the browser build.

## Building the browser version

    # 1. clone ScummVM at the base commit and apply our patches
    git clone https://github.com/scummvm/scummvm.git
    cd scummvm && git checkout e5af3564 && git apply ../patches/agitwo-scummvm.patch

    # 2. build the WASM target with only the AGI + SCI engines
    ./dists/emscripten/build.sh setup libs configure make dist \
        --disable-all-engines --enable-engine=agi,sci

    # 3. (one-time) fix the SDL3 keyboard-listener leak in the emsdk port
    #    apply patches/sdl3-emscripten-keyboard-leak.patch under
    #    dists/emscripten/emsdk-*/upstream/emscripten/cache/ports/sdl3/...
    #    then: embuilder build sdl3 --force  &&  relink

    # 4. drop voice packs into build-emscripten/voices/<game>/ and serve the folder
    cd build-emscripten && python3 -m http.server 9123 --bind 0.0.0.0

Open `http://localhost:9123/scummvm.html#qfg1`. Voices start after the first keypress/click (browser autoplay policy).

## Generating voices

Add lines to a `voices-src/<game>-lines.json` (exact game text + speaker + voiceId), generate clips with a TTS provider, drop them in the voices dir, then:

    python3 tools/gen_voice_manifest.py voices-src/qfg1-full-lines.json <voices-dir>/manifest.json

The manifest always hashes the `text` field (the `say` field, when present, is what gets spoken but is not part of the key).

## Distribution & legal

The **engine and tools** here are our own work plus GPL-licensed ScummVM changes, and are freely shareable.

The **game data** (Sierra's `RESOURCE.*` etc.) and the **generated voice audio** are **not** in this repo:

- Game data is copyrighted; users must own their own copy.
- The voice clips are AI-generated audio of Sierra's copyrighted script (a derivative work). They are distributed separately as a per-game pack, on the "you must own the game" fan-patch model, non-commercial.

`text/` and `voices-src/*-lines.json` contain verbatim script text. Keep this repo **private**, or strip those before making it public.

## Status

- Full QFG1 voice coverage: done and browser-verified.
- Native (Windows) voice playback path: implemented; portable Windows build + per-game "unzip into your game folder + one .bat" pack: in progress.
