# Marketing assets - QFG1 Voiced Edition

Everything needed for the Nexus Mods page lives here.

## video/
- `qfg1-voices-promo.mp4` - 1:48 showcase. Title card held throughout, with a
  lower-third naming each character and its voice actor while their real clip
  plays. 11 voices. Nexus does not host video, so upload this to YouTube
  (unlisted is fine) and link it in the description.

## images/
- `qfg1-title-card.png` (1280x720) - use as the **mod thumbnail / header**.
- `promo-still-baba-yaga.png`, `promo-still-2.png` - stills pulled from the promo
  video; good as gallery images.
- `voicelab-cast.png` - the voice lab showing the full 47-character cast and the
  voice assigned to each. Nice "behind the scenes" shot.
- `voicelab-narrator-split.png` - the lab showing a line split into a Narrator row
  and a character row, which illustrates the narration/dialogue separation.

## text/
- `nexus-description.txt` - the mod description, ready to paste.
- `promo-video-voice-list.json` - which characters/voices appear in the promo, in
  order, with the line each one speaks.

## The downloadable packages (not stored here - they are large)
Built to `dist/out/` and copied to `C:\temp\agitwo-release\`:
- `QFG1-Voiced-win.zip` (389 MB) - tested
- `QFG1-Voiced-mac.zip` (333 MB) - Apple Silicon, untested
- `QFG1-Voiced-linux.zip` (342 MB) - untested

## Upload checklist
1. Nexus QFG1-5 page -> Upload -> Add a new mod.
2. Category: Miscellaneous (no audio/overhaul category exists on that page).
3. Files tab: upload each zip as a separate main file, named per OS.
4. Images: `qfg1-title-card.png` as thumbnail, plus the gallery shots above.
5. Description: paste `text/nexus-description.txt`.
6. Add the YouTube link for the promo video.
7. State clearly that the player must own QFG1 EGA.

## Missing / could add
In-game screenshots (the game actually running with voices) were lost in a reboot.
These would strengthen the page a lot and can be recaptured from the working
Windows build in `C:\temp\qfg1wintest`.
