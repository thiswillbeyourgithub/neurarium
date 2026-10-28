# Demo recorder

A small, **site-agnostic** tool to record showcase demos of a website: it drives a headless Chromium through a scripted click sequence with a visible glowing cursor, captures it **frame by frame on a faked clock**, and produces

- an **animated WebP** (`*.webp`), the README-embeddable hero: full colour, so no GIF 256-colour banding on gradients and glows,
- an **AV1** master (`*.av1.mp4`, `libsvtav1`), the compact shareable video,
- optionally a **gifski GIF** (`*.gif`, `gif=True`) for hosts that take nothing else.

Built with the help of Claude Code.

## How capture works

Playwright's fake clock (`page.clock`) owns `Date`, timers, `performance.now` and `requestAnimationFrame`. The page loads in real time; `begin()` pauses the clock, and from then on every `wait()` advances it by exactly one frame (1/`fps` s), steps the page's CSS transitions and Web Animations by the same amount (they run on the compositor, outside the faked clock), and grabs a lossless PNG screenshot at `scale` x the viewport (default 2x, so 2560x1440 for a 1280x720 viewport). So:

- the output is exactly `fps` and never drops a frame, however slow the renderer is (a SwiftShader software-WebGL run only takes longer, it is not choppier);
- frames are supersampled, then downscaled with lanczos by the encoders, so text and edges stay sharp;
- a run is deterministic.

Anything the page animates must therefore go through timers / `requestAnimationFrame` / CSS animations; the browser's native smooth scroll does not, which is why `scroll()` tweens on `requestAnimationFrame` instead.

## Files

- `recorder.py`: the engine. Import `Demo` and script a page with the Python API (`goto` / `wait` / `wait_for` / `wait_gone` / `begin` / `move` / `click` / `hover` / `type` / `key` / `scroll` / `slider` / `drag` / `zoom`). Generic: point it at any URL. Copy this one file to use it in another project.
- `neurarium.py`: the neurarium showcase, five scripted stories (`STORIES`, each `name -> (story, output basename, start page)`). It serves the local site with `tools/serve.py` on a free port, marks the tour + "What's new" as seen, clicks through the loading overlay, then records one story per output:
    - `drug` (`preview`, the README hero): the whole brain auto-rotating -> exploded -> olanzapine searched (gem dots + effect flow, zoomed in) -> its binding profile opened and scrolled.
    - `anatomy` (`demo-anatomy`): explode + reassemble, the hippocampus isolated, the Papez circuit pulsing, fluoxetine's serotonergic flow.
    - `compare` (`demo-compare`): haloperidol's binding profile, then clozapine's much broader one.
    - `drugsmap` (`demo-drugsmap`): the drugs map page (`drugs-map.html`), its antipsychotic presets, a few drugs hovered.
    - `receptor` (`demo-receptor`): 5-HT2A's expression regions, the drugs binding it, then LSD picked from that list.

## Requirements

- `playwright` + a browser: `pip install playwright && playwright install chromium` (or run a scenario with `uv run`, which resolves the inline dep).
- `ffmpeg` built with `libwebp` (WebP) and `libsvtav1` (AV1); `av1_nvenc` also works (`av1_encoder=`).
- `gifski` on `PATH`, only for `gif=True`.

In this checkout the run needs the Claude Code sandbox off (Chromium launch + GPU access).

## Run the neurarium demos

```sh
uv run tools/demos/neurarium.py                 # every story -> docs/images/<base>.webp + docs/videos/<base>.av1.mp4
uv run tools/demos/neurarium.py --story compare # one story
uv run tools/demos/neurarium.py --fps 30        # half the capture time (draft takes)
uv run tools/demos/neurarium.py --out-dir /tmp/nd
uv run tools/demos/neurarium.py --keep-frames   # keep the PNGs to re-encode without re-recording
```

A 60 fps take of a ~20 s story captures ~1200 frames at about 7 frames/s of wall clock, so roughly 3-5 minutes plus encoding.

## Write your own scenario

```python
from recorder import Demo

with Demo("http://localhost:5173/", out="login_demo") as d:
    d.wait_for("#email")        # real time, not captured
    d.begin()                   # capture starts
    d.click("#email")
    d.type("#email", "demo@example.com", click_first=False)
    d.click("button[type=submit]")
    d.wait(1500)
    d.scroll(to="bottom")
    d.wait(1000)
# WebP + AV1 are written on exit.
```

### Tuning knobs (`Demo(...)`)

| arg | default | note |
| --- | --- | --- |
| `width`, `height` | `1280`, `720` | viewport (CSS px) |
| `scale` | `2` | device pixel ratio of the captured frames |
| `fps` | `60` | capture rate; the AV1 keeps it |
| `gl` | `"gpu"` | `"swiftshader"` where no GPU is reachable (slower, same output) |
| `init_scripts` | `()` | JS run before the page's own (e.g. seed `localStorage`) |
| `cursor` / `cursor_speed` | `True` / `1600` | the injected cursor; px/s glide speed |
| `webp_fps` / `webp_width` / `webp_quality` | `24` / `1280` / `75` | the size levers of the hero file |
| `av1_width` / `av1_crf` / `av1_preset` | `1920` / `36` / `6` | lower crf = better/bigger |
| `gif` / `gif_fps` / `gif_width` | `False` / `20` / `640` | optional GIF |
| `keep_frames` | `False` | keep the PNG frames dir (its path is logged) |

### Notes

- WebP size scales with duration x `webp_fps` x `webp_width`^2: it has no inter-frame motion prediction, so a moving 3D scene costs a lot per frame. The AV1 is several times smaller at better quality, but a GitHub README cannot embed a repo-committed video, so the WebP is the hero and the AV1 the shareable file.
- Interact only with visible elements; a hidden target fails fast at `action_timeout` (default 8 s).
