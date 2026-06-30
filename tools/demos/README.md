# Demo recorder

A small, **site-agnostic** tool to record showcase demos of a website: it drives
a real (non-headless) browser through a scripted click sequence with a visible
glowing cursor, records the page at an exact 720p, and produces

- an **AV1** master (`*.av1.mp4`, `libsvtav1`) for maximum compressibility, and
- a **gifski GIF** (`*.gif`) with a **configurable framerate** for smoothness.

Capture is Playwright-native (the page surface, not the OS window), so the
output is deterministic and exactly the chosen size; the cursor is injected DOM,
so it is part of the recording. Built with the help of Claude Code.

## Files

- `recorder.py` — the engine. Import `Demo` and script a page with the Python
  API (`goto` / `wait` / `wait_for` / `wait_gone` / `begin` / `move` / `click` /
  `hover` / `type` / `key` / `scroll` / `slider`). Generic: point it at any URL.
  Copy this one file to use it in another project. `begin()` marks the clip start
  (trims a slow startup off the front); `slider()` drags a range input smoothly.
- `neurarium.py` — the neurarium showcase tour (an example scenario). It serves
  the local site with `tools/serve.py`, waits out the loading overlay, runs the
  tour (assemble -> explode -> reassemble -> drug focus), and writes the outputs.

## Requirements

All already present in this environment; for a fresh machine:

- `playwright` + a browser: `pip install playwright && playwright install chromium`
  (or run a scenario with `uv run`, which resolves the inline dep).
- `ffmpeg` built with `libsvtav1` (AV1) — `av1_nvenc` also works (`av1_encoder=`).
- `gifski` on `PATH` (`cargo install gifski`, or the prebuilt binary).
- A GPU + display for hardware rendering (see Rendering).

## Rendering (headless vs headed, GPU)

The engine launches Chromium with ANGLE/desktop-GL flags so it renders on the
real GPU. **Record headless** (the neurarium demo's default): the page renders on
the GPU *and* the video is captured cleanly. Plain headless without those flags
falls back to the SwiftShader software renderer (slow, choppy WebGL), and headed
mode, while it does use the GPU, can letterbox the captured video (a grey bar) on
some platforms because the headed screencast is unreliable. So: headless for the
clean capture, `--headed` only if you want to watch it run.

## Run the neurarium demo

```sh
uv run tools/demos/neurarium.py                 # -> docs/demo.gif + docs/demo.av1.mp4 (README hero)
uv run tools/demos/neurarium.py --gif-fps 24    # smaller GIF
uv run tools/demos/neurarium.py --out /tmp/nd   # choose output basename
uv run tools/demos/neurarium.py --headed        # show a window (see Rendering below)
```

## Write your own scenario

```python
from recorder import Demo

with Demo("http://localhost:5173/", out="login_demo", gif_fps=30) as d:
    d.wait(800)
    d.click("#email")
    d.type("#email", "demo@example.com", click_first=False)
    d.click("#password")
    d.type("#password", "hunter2", click_first=False)
    d.click("button[type=submit]")
    d.wait(1500)
    d.scroll(to="bottom")
    d.wait(1000)
# AV1 + GIF are written on exit.
```

### Tuning knobs (`Demo(...)`)

| arg | default | note |
| --- | --- | --- |
| `width`, `height` | `1280`, `720` | capture size (exact) |
| `headless` | `True` | renders on the GPU + captures cleanly; `False` to watch (may letterbox) |
| `cursor` | `True` | the injected glowing cursor + click ripples |
| `cursor_speed` | `1600` | px/s; glide duration derives from distance |
| `av1` / `av1_encoder` | `True` / `libsvtav1` | set `av1_encoder="av1_nvenc"` for GPU |
| `av1_crf` / `av1_preset` | `30` / `6` | lower crf = better/bigger; lower preset = slower/better |
| `gif` | `True` | also emit the GIF |
| `gif_fps` | `20` | **bump for smoothness** (e.g. `30`); drives GIF size |
| `gif_width` | `640` | `None` keeps capture width |
| `gif_quality` | `90` | gifski quality (1-100) |
| `keep_raw` | `False` | also keep the raw Playwright `.webm` |

### Notes

- GIF size scales with duration x fps x width. The AV1 master stays small
  regardless; if a GIF is too big, lower `gif_fps` / `gif_width`, or keep the
  demo short. HEVC/AV1 do not embed in most browsers/READMEs, so the GIF is the
  embeddable artifact and the AV1 is the compact shareable video.
- The GIF and AV1 come from the same single recording (same duration).
- Interact only with elements that are visible; a hidden/animating target makes
  the action time out (fast-fail at `action_timeout`, default 8s). For panels
  that hide/show, navigate them first (the neurarium tour uses Esc + search).
