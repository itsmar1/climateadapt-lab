# Architecture animation

`architecture-animation.html` is a single, standalone, offline file (no network
requests, no dependencies). It plays a 35-second animated diagram of the
ClimateAdapt Lab architecture at a fixed 1920×1080 stage, scaled to fit the
window.

## Open it

Open `architecture-animation.html` in Chrome. With no parameters it autoplays
from the start.

Useful parameters and keys:

| Control | Effect |
| --- | --- |
| Space | play / pause |
| R | restart |
| ← / → | seek ∓ / ± 1 second |
| `?t=12.5` | start paused at 12.5 s (for framing a still) |
| `?record=1` | hide cursor and all controls, 1.0 s black pre-roll, autoplay, stop on the final frame |
| `?audio=voiceover.mp3` | also play a local audio file placed next to the HTML (not in this repo) while the animation plays, to preview voiceover sync |

## Record it (OBS)

1. Open the file in Chrome with `?record=1` appended, e.g.
   `architecture-animation.html?record=1`.
2. Press F11 for fullscreen Chrome (1920×1080 display).
3. In OBS, capture that window/display at 1920×1080, 60 fps, and start
   recording just before the black pre-roll ends.
4. The animation runs 35 s and stops on the final frame; lay the ElevenLabs
   voiceover under it in your editor.

## Retime it

All timing lives in one editable `BEATS` constant at the top of the `<script>`
in `architecture-animation.html` (seconds; `END: 35.0` is the total length).
Change the beat times — and `END` if the total changes — to match a real
voiceover. Node activations, chips, particles, the validator scan, the caption
and the fade all derive from `BEATS`, so no other edits are needed.

## Font licence

The file embeds the latin-subset variable Manrope woff2 as base64
(`frontend/node_modules/@fontsource-variable/manrope`, SIL Open Font License
1.1, Copyright 2019 The Manrope Project Authors). If the embedded font fails
to load, the page falls back to `Inter, system-ui, sans-serif`. Colours match
the app tokens in `frontend/src/index.css`.

## Previews

`preview/` holds still frames captured at t = 2, 6, 9, 14, 19, 25, 28, 33 and
34.8 s for a quick visual check without playing the file.
