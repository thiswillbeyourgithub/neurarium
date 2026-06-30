"""Generic Playwright demo recorder (built with the help of Claude Code).

Drive any webpage through a scripted click sequence with a visible, glowing
synthetic cursor (smooth glides + click ripples), record the page at an exact
720p, then post-process to:

  - an AV1 master  (.av1.mp4, libsvtav1 or av1_nvenc) for compressibility, and
  - a gifski GIF   (.gif) with a *configurable framerate* for smoothness.

The engine is site-agnostic. Each demo is a small Python script that imports
`Demo` and calls its helper methods (the "Python API"); see `neurarium.py`.

    from recorder import Demo

    with Demo("http://localhost:8000", out="mydemo", gif_fps=30) as d:
        d.wait(1500)
        d.click("#some-button")
        d.hover(".thing")
        d.scroll(to="bottom")

On exit the context closes (flushing the video) and the AV1 + GIF are written.

Capture is Playwright-native: the video is the page surface (the injected
cursor is real DOM, so it is captured), independent of the OS window, so the
output is deterministic and exactly `width`x`height`.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# Injected at document start on every navigation: a window.__demo helper that
# owns a glowing arrow cursor + click ripples, animated with requestAnimationFrame
# so the motion is captured smoothly in the page video. Pure DOM/CSS, no deps.
CURSOR_JS = r"""
(() => {
  if (window.__demo) return;
  const state = { x: window.innerWidth / 2, y: window.innerHeight / 2, el: null, halo: null };
  const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

  function ensure() {
    if (window.__DEMO_NO_CURSOR) return;
    if (state.el && document.body && document.body.contains(state.el)) return;
    const wrap = document.createElement('div');
    wrap.setAttribute('data-demo-cursor', '');
    Object.assign(wrap.style, {
      position: 'fixed', left: '0', top: '0', zIndex: '2147483647',
      pointerEvents: 'none', width: '0', height: '0', willChange: 'transform',
      transform: `translate(${state.x}px, ${state.y}px)`,
    });
    const halo = document.createElement('div');
    Object.assign(halo.style, {
      position: 'absolute', left: '-14px', top: '-14px', width: '28px', height: '28px',
      borderRadius: '50%', transition: 'transform 0.12s ease',
      background: 'radial-gradient(circle, rgba(120,200,255,0.55), rgba(120,200,255,0) 70%)',
    });
    const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    arrow.setAttribute('width', '23'); arrow.setAttribute('height', '23');
    arrow.setAttribute('viewBox', '0 0 24 24');
    Object.assign(arrow.style, {
      position: 'absolute', left: '-3px', top: '-3px',
      filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.65))',
    });
    arrow.innerHTML = '<path d="M4 2 L4 20 L9 15 L12.5 22 L15.5 20.5 L12 14 L19 14 Z"'
      + ' fill="#ffffff" stroke="#161616" stroke-width="1.2" stroke-linejoin="round"/>';
    wrap.appendChild(halo); wrap.appendChild(arrow);
    (document.body || document.documentElement).appendChild(wrap);
    state.el = wrap; state.halo = halo;
  }
  function setPos(x, y) {
    state.x = x; state.y = y;
    if (state.el) state.el.style.transform = `translate(${x}px, ${y}px)`;
  }
  function moveTo(x, y, dur) {
    ensure();
    return new Promise((res) => {
      const sx = state.x, sy = state.y, dx = x - sx, dy = y - sy;
      if (dur <= 0 || (dx === 0 && dy === 0)) { setPos(x, y); return res(); }
      let start = null;
      const step = (ts) => {
        if (start === null) start = ts;
        const p = Math.min(1, (ts - start) / dur);
        const e = easeInOutCubic(p);
        setPos(sx + dx * e, sy + dy * e);
        if (p < 1) requestAnimationFrame(step); else res();
      };
      requestAnimationFrame(step);
    });
  }
  function press() {
    if (window.__DEMO_NO_CURSOR) return;
    ensure();
    if (state.halo) {
      state.halo.style.transform = 'scale(0.6)';
      setTimeout(() => { if (state.halo) state.halo.style.transform = 'scale(1)'; }, 140);
    }
    const r = document.createElement('div');
    Object.assign(r.style, {
      position: 'fixed', left: state.x + 'px', top: state.y + 'px', zIndex: '2147483646',
      pointerEvents: 'none', width: '12px', height: '12px', marginLeft: '-6px', marginTop: '-6px',
      borderRadius: '50%', border: '2px solid rgba(120,200,255,0.9)',
      transform: 'scale(0.3)', opacity: '0.9',
      transition: 'transform 0.45s ease-out, opacity 0.45s ease-out',
    });
    (document.body || document.documentElement).appendChild(r);
    requestAnimationFrame(() => { r.style.transform = 'scale(4)'; r.style.opacity = '0'; });
    setTimeout(() => r.remove(), 520);
  }
  function smoothScrollIntoView(sel, dur) {
    const el = document.querySelector(sel);
    if (!el) return Promise.resolve();
    el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
    return new Promise((res) => setTimeout(res, dur || 600));
  }
  function smoothScrollTo(where, dur) {
    const y = where === 'bottom' ? document.body.scrollHeight : 0;
    window.scrollTo({ top: y, behavior: 'smooth' });
    return new Promise((res) => setTimeout(res, dur || 600));
  }
  function setRange(sel, frac, x, y) {
    const el = document.querySelector(sel);
    if (!el) return;
    const min = parseFloat(el.min || '0'), max = parseFloat(el.max || '1');
    el.value = min + (max - min) * frac;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    setPos(x, y);
  }

  window.__demo = { ensure, setPos, moveTo, press, smoothScrollIntoView, smoothScrollTo,
                    setRange, pos: () => ({ x: state.x, y: state.y }) };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ensure);
  else ensure();
})();
"""

# Launch args. Two groups:
# - keep timers/animation running even if the window loses focus, so
#   requestAnimationFrame-driven sites (e.g. WebGL) record at full rate;
# - force real-GPU rendering via ANGLE-over-desktop-GL. Without this, *headless*
#   Chromium falls back to the SwiftShader software renderer, which is slow (a
#   choppy WebGL capture); these flags make it use the actual GPU. Harmless when
#   headed (which already gets the GPU). Headless avoids the headed-mode video
#   letterboxing bug while still rendering on the GPU.
_LAUNCH_ARGS = [
    "--autoplay-policy=no-user-gesture-required",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--use-gl=angle",
    "--use-angle=gl",
    "--ignore-gpu-blocklist",
    "--enable-gpu",
]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _ease(t: float) -> float:
    """easeInOutCubic."""
    return 4 * t * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2


class Demo:
    """A scripted, recorded browser session over a single page.

    Use as a context manager. Coordinates are CSS pixels in the viewport, which
    is exactly what both Playwright's mouse and the fixed-position cursor use, so
    the visible cursor always lands where the real click fires.
    """

    def __init__(
        self,
        url: str,
        out: str = "demo",
        *,
        width: int = 1280,
        height: int = 720,
        headless: bool = True,   # headless renders on the GPU + captures cleanly here
        cursor: bool = True,
        # Cursor glide tuning.
        cursor_speed: float = 1600.0,   # px/s; glide duration derives from distance
        min_glide_ms: int = 220,
        max_glide_ms: int = 1100,
        # Fail fast on a bad selector instead of Playwright's 30s default.
        action_timeout: int = 8000,
        # AV1 master.
        av1: bool = True,
        av1_encoder: str = "libsvtav1",  # or "av1_nvenc" for GPU
        av1_crf: int = 30,
        av1_preset: int = 6,             # libsvtav1: 0 (slow/best) .. 13 (fast)
        # GIF (gifski).
        gif: bool = True,
        gif_fps: int = 20,               # bump for smoothness (e.g. 30)
        gif_width: int | None = 640,     # None keeps capture width
        gif_quality: int = 90,
        # Keep the raw Playwright webm next to the outputs.
        keep_raw: bool = False,
        quiet: bool = False,
    ) -> None:
        self.url = url
        self.out = Path(out)
        self.width = width
        self.height = height
        self.headless = headless
        self.cursor = cursor
        self.cursor_speed = cursor_speed
        self.min_glide_ms = min_glide_ms
        self.max_glide_ms = max_glide_ms
        self.action_timeout = action_timeout
        self.av1 = av1
        self.av1_encoder = av1_encoder
        self.av1_crf = av1_crf
        self.av1_preset = av1_preset
        self.gif = gif
        self.gif_fps = gif_fps
        self.gif_width = gif_width
        self.gif_quality = gif_quality
        self.keep_raw = keep_raw
        self.quiet = quiet

        self.cx = width / 2.0
        self.cy = height / 2.0
        self._pw = None
        self._browser = None
        self.context = None
        self.page = None
        self._video = None
        self._video_dir = None
        self._t0 = 0.0          # monotonic time the recording started
        self._clip_start = 0.0  # seconds to trim off the front of the output

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> "Demo":
        self._log(f"launching chromium (headless={self.headless}) -> {self.url}")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless, args=_LAUNCH_ARGS)
        self._video_dir = Path(tempfile.mkdtemp(prefix="demo-video-"))
        self.context = self._browser.new_context(
            viewport={"width": self.width, "height": self.height},
            record_video_dir=str(self._video_dir),
            record_video_size={"width": self.width, "height": self.height},
            device_scale_factor=1,
        )
        self._t0 = time.monotonic()  # the video begins ~here
        # The helper is always injected (slider/glide use it); the visible cursor
        # element is suppressed when cursor=False.
        if not self.cursor:
            self.context.add_init_script("window.__DEMO_NO_CURSOR = true;")
        self.context.add_init_script(CURSOR_JS)
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.action_timeout)
        self._video = self.page.video
        self.page.goto(self.url, wait_until="load")
        if self.cursor:
            self.page.evaluate(
                "([x, y]) => window.__demo && window.__demo.setPos(x, y)",
                [self.cx, self.cy],
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc_type is not None:
                self._log(f"aborting due to {exc_type.__name__}: {exc}")
            self._finalize(success=exc_type is None)
        finally:
            if self._video_dir and self._video_dir.exists():
                shutil.rmtree(self._video_dir, ignore_errors=True)
        return False  # never swallow exceptions

    # -- scripting API ------------------------------------------------------

    def goto(self, url: str) -> "Demo":
        self.page.goto(url, wait_until="load")
        self.cx, self.cy = self.width / 2.0, self.height / 2.0
        if self.cursor:
            self.page.evaluate(
                "([x, y]) => window.__demo && window.__demo.setPos(x, y)", [self.cx, self.cy]
            )
        return self

    def wait(self, ms: int) -> "Demo":
        self.page.wait_for_timeout(ms)
        return self

    pause = wait

    def wait_for(self, selector: str, *, timeout: int = 60000) -> "Demo":
        """Block until `selector` is visible (e.g. the app is ready)."""
        self.page.wait_for_selector(selector, state="visible", timeout=timeout)
        return self

    def wait_gone(self, selector: str, *, timeout: int = 60000) -> "Demo":
        """Block until `selector` is hidden or detached (e.g. a loading overlay)."""
        self.page.wait_for_selector(selector, state="hidden", timeout=timeout)
        return self

    def begin(self) -> "Demo":
        """Mark *now* as the start of the clip; everything before is trimmed off.

        Call once the app is ready (after a loading overlay clears) so the output
        does not show the boring startup. A small lead-in is kept.
        """
        self._clip_start = max(0.0, time.monotonic() - self._t0 - 0.2)
        self._log(f"clip start marked at {self._clip_start:.1f}s (front trimmed)")
        return self

    def move(self, target, duration: int | None = None) -> "Demo":
        """Glide the cursor to a selector or an (x, y) viewport point."""
        x, y = self._coords(target)
        self._glide(x, y, duration)
        return self

    def click(self, selector: str, *, button: str = "left",
              duration: int | None = None, settle: int = 140) -> "Demo":
        loc = self.page.locator(selector).first
        loc.scroll_into_view_if_needed()
        x, y = self._center(loc)
        self._glide(x, y, duration)
        self.wait(80)
        if self.cursor:
            self.page.evaluate("() => window.__demo.press()")
        self.page.mouse.click(x, y, button=button)
        if settle:
            self.wait(settle)
        return self

    def hover(self, selector: str, *, duration: int | None = None, hold: int = 0) -> "Demo":
        loc = self.page.locator(selector).first
        loc.scroll_into_view_if_needed()
        x, y = self._center(loc)
        self._glide(x, y, duration)
        self.page.mouse.move(x, y)
        if hold:
            self.wait(hold)
        return self

    def type(self, selector: str, text: str, *, delay: int = 55,
             click_first: bool = True) -> "Demo":
        if click_first:
            self.click(selector, settle=120)
        self.page.keyboard.type(text, delay=delay)
        return self

    def key(self, name: str) -> "Demo":
        """Press a keyboard shortcut on the page body (e.g. 'm', 'Escape')."""
        self.page.keyboard.press(name)
        return self

    def scroll(self, selector: str | None = None, *, to: str | None = None,
               dur: int = 700) -> "Demo":
        if selector is not None:
            self.page.evaluate(
                "([s, d]) => window.__demo.smoothScrollIntoView(s, d)", [selector, dur]
            )
        elif to is not None:
            self.page.evaluate(
                "([w, d]) => window.__demo.smoothScrollTo(w, d)", [to, dur]
            )
        self.wait(dur)
        return self

    def slider(self, selector: str, to: float, *, dur: int = 2000, steps: int = 22) -> "Demo":
        """Drag a range <input> to fraction `to` in [0, 1], cursor riding the handle.

        Stepped from Python on the wall clock (each step sets the value, fires
        'input', and moves the cursor), so the pacing is deterministic even when
        the page throttles requestAnimationFrame under a heavy per-input handler.
        """
        to = _clamp(float(to), 0.0, 1.0)
        box = self.page.locator(selector).first.bounding_box()
        if box is None:
            raise RuntimeError(f"slider {selector!r} is not visible")
        info = self.page.evaluate(
            "(s) => { const e = document.querySelector(s);"
            " return { mn: parseFloat(e.min || '0'), mx: parseFloat(e.max || '1'),"
            " v: parseFloat(e.value) }; }",
            selector,
        )
        span = (info["mx"] - info["mn"]) or 1.0
        frm = (info["v"] - info["mn"]) / span
        cy = box["y"] + box["height"] / 2.0
        per = max(8, int(dur / steps))
        for i in range(1, steps + 1):
            frac = frm + (to - frm) * _ease(i / steps)
            cx = box["x"] + frac * box["width"]
            self.page.evaluate(
                "([s, f, x, y]) => window.__demo.setRange(s, f, x, y)",
                [selector, frac, cx, cy],
            )
            self.page.wait_for_timeout(per)
        self.cx, self.cy = box["x"] + to * box["width"], cy
        return self

    # -- internals ----------------------------------------------------------

    def _center(self, locator):
        box = locator.bounding_box()
        if box is None:
            raise RuntimeError("element is not visible / has no bounding box")
        return box["x"] + box["width"] / 2.0, box["y"] + box["height"] / 2.0

    def _coords(self, target):
        if isinstance(target, (tuple, list)) and len(target) == 2:
            return float(target[0]), float(target[1])
        loc = self.page.locator(str(target)).first
        loc.scroll_into_view_if_needed()
        return self._center(loc)

    def _glide(self, x: float, y: float, duration: int | None) -> None:
        if duration is None:
            dist = math.hypot(x - self.cx, y - self.cy)
            duration = int(_clamp(dist / self.cursor_speed * 1000.0,
                                  self.min_glide_ms, self.max_glide_ms))
        self.page.evaluate(
            "([x, y, d]) => window.__demo.moveTo(x, y, d)", [x, y, duration]
        )
        self.cx, self.cy = x, y

    # -- post-processing ----------------------------------------------------

    def _finalize(self, success: bool) -> None:
        self.context.close()  # flushes the webm to disk
        raw = Path(self._video.path())
        self._log(f"raw capture: {raw} ({_size(raw)})")

        self.out.parent.mkdir(parents=True, exist_ok=True)
        if self.keep_raw:
            webm = self.out.with_suffix(".webm")
            shutil.copyfile(raw, webm)
            self._log(f"kept raw: {webm} ({_size(webm)})")

        if self.av1:
            self._encode_av1(raw)
        if self.gif:
            self._encode_gif(raw)

        self._browser.close()
        self._pw.stop()
        if not success:
            self._log("note: finalized despite a scripting error (partial demo)")

    def _seek_args(self) -> list[str]:
        return ["-ss", f"{self._clip_start:.3f}"] if self._clip_start > 0 else []

    def _encode_av1(self, raw: Path) -> None:
        dst = self.out.with_suffix(".av1.mp4")
        cmd = ["ffmpeg", "-y", *self._seek_args(), "-i", str(raw), "-an",
               "-c:v", self.av1_encoder, "-pix_fmt", "yuv420p",
               "-movflags", "+faststart"]
        if self.av1_encoder == "libsvtav1":
            cmd += ["-crf", str(self.av1_crf), "-preset", str(self.av1_preset)]
        elif self.av1_encoder == "av1_nvenc":
            cmd += ["-cq", str(self.av1_crf), "-preset", "p5"]
        else:
            cmd += ["-crf", str(self.av1_crf)]
        cmd += [str(dst)]
        self._run(cmd, "AV1 encode")
        self._log(f"AV1: {dst} ({_size(dst)})")

    def _encode_gif(self, raw: Path) -> None:
        dst = self.out.with_suffix(".gif")
        frames_dir = Path(tempfile.mkdtemp(prefix="demo-frames-"))
        try:
            vf = f"fps={self.gif_fps}"
            if self.gif_width:
                vf += f",scale={self.gif_width}:-2:flags=lanczos"
            self._run(
                ["ffmpeg", "-y", *self._seek_args(), "-i", str(raw), "-vf", vf,
                 str(frames_dir / "f%05d.png")],
                "GIF frame extraction",
            )
            frames = sorted(frames_dir.glob("f*.png"))
            if not frames:
                raise RuntimeError("no frames extracted for the GIF")
            self._run(
                ["gifski", "-r", str(self.gif_fps), "-Q", str(self.gif_quality),
                 "-o", str(dst), *map(str, frames)],
                "gifski",
            )
            self._log(f"GIF: {dst} ({_size(dst)}, {len(frames)} frames @ {self.gif_fps}fps)")
        finally:
            shutil.rmtree(frames_dir, ignore_errors=True)

    def _run(self, cmd: list[str], what: str) -> None:
        self._log(f"{what}: {cmd[0]} ...")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr[-4000:])
            raise RuntimeError(f"{what} failed (exit {proc.returncode})")

    def _log(self, msg: str) -> None:
        if not self.quiet:
            print(f"[demo] {msg}", flush=True)


def _size(p: Path) -> str:
    try:
        n = p.stat().st_size
    except OSError:
        return "missing"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.0f}B"
