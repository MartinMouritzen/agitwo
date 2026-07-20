# Marketing assets - QFG1 Voiced Edition

Everything needed for the Nexus Mods page lives here.

## video/
- `qfg1-voices-promo.mp4` - 1:48 showcase. Title card held throughout, with a
  lower-third naming each character and its voice actor while their real clip
  plays. 11 voices. Nexus does not host video, so it is published on YouTube:
  https://www.youtube.com/watch?v=T29a6lJXSz4 - link that in the mod description.

## images/ (Nexus-ready, exact sizes)
Upload these directly.

- `nexus-header-1300x372.png` - **the Header banner**. Quest for Glory title screen
  (the wanted poster) on the left, "FULLY VOICED" branding on the right.
- `nexus-01-cover-1920x1080.png` - the title/cover screen. Good first gallery image.
- `nexus-02-dialogue-1920x1080.png` - the Sheriff greeting you in Spielburg,
  captioned with his voice actor. Best single shot of what the mod does.
- `nexus-03-character-1920x1080.png` - Fighter / Magic User / Thief select screen.
- `nexus-04-cast-1920x1080.png` - the voice lab showing all 47 characters and the
  voice cast for each.
- `nexus-05-split-1920x1080.png` - the lab showing narration split from dialogue.

### images/source/
Raw, uncropped originals in case you want to recompose anything: the four captured
game screens, the two voice-lab screenshots, the promo video stills, and the plain
title card used in the video.

## text/
- `nexus-description.txt` - the mod description, ready to paste.
- `promo-video-voice-list.json` - which characters/voices appear in the promo, in
  order, with the line each one speaks.

## The downloadable packages (not stored here - they are large)
Built to `dist/out/` and copied to `C:\temp\agitwo-release\`:
- `QFG1-Voiced-win.zip` (389 MB) - tested
- `QFG1-Voiced-mac.zip` (333 MB) - Apple Silicon, untested
- `QFG1-Voiced-linux.zip` (342 MB) - untested

All three launchers show a menu on start: 1 Play, 2 Configure ScummVM, 3 Exit.
Configure opens ScummVM's own options (scalers, music device, window size) and
writes to a `scummvm.ini` inside the bundle, so it never touches a player's
existing ScummVM setup. Suggested by a player on Nexus Mods.

The Windows zip is also on the GitHub release (`qfg1-v1.0`) as a mirror, since
Nexus held the download for containing an `.exe`.

## Upload checklist
1. Nexus QFG1-5 page -> Upload -> Add a new mod.
2. Category: Miscellaneous (no audio/overhaul category exists on that page).
3. Files tab: upload each zip as a separate main file, named per OS.
4. Images: `qfg1-title-card.png` as thumbnail, plus the gallery shots above.
5. Description: paste `text/nexus-description.txt`.
6. Add the YouTube link: https://www.youtube.com/watch?v=T29a6lJXSz4
7. State clearly that the player must own QFG1 EGA.

## Missing / could add
Nothing outstanding. In-game screenshots were recaptured from the live voiced build.


