"""Generic Playwright demo recorder (built with the help of Claude Code).

Drive any webpage through a scripted click sequence with a visible, glowing
synthetic cursor (smooth glides + click ripples), capture it frame by frame on a
faked clock, then encode:

  - an animated WebP (.webp), the README-embeddable hero (full colour, no GIF
    256-colour banding),
  - an AV1 master  (.av1.mp4, libsvtav1 or av1_nvenc), the compact shareable video,
  - optionally a gifski GIF (.gif) for the hosts that take nothing else.

The engine is site-agnostic. Each demo is a small Python script that imports
`Demo` and calls its helper methods (the "Python API"); see `neurarium.py`.

    from recorder import Demo

    with Demo("http://localhost:8000", out="mydemo") as d:
        d.wait(1500)          # not captured yet: the page loads in real time
        d.begin()             # capture starts here
        d.click("#some-button")
        d.hover(".thing")
        d.scroll(to="bottom")

How capture works: Playwright's fake clock (`page.clock`) owns `Date`, timers,
`performance.now` and `requestAnimationFrame`. Until `begin()` it runs in real
time; after it, the clock is paused and every `wait()` advances it one frame at a
time (1/`fps` s), steps the page's CSS/Web Animations by the same amount, and
grabs a lossless screenshot at `scale` x the viewport. So the output is exactly
`fps`, never drops a frame however slow the renderer is, and is pixel-sharp
(supersampled, then downscaled with lanczos by the encoders).
"""

from __future__ import annotations

import base64
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# Injected at document start on every navigation: a window.__demo helper that
# owns a glowing arrow cursor + click ripples (animated on requestAnimationFrame,
# so the faked clock drives them), a rAF scroll tween, and the per-frame
# Web Animations stepper. Pure DOM/CSS, no deps.
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
  // Fire-and-forget: the caller advances the clock for `dur` itself.
  function moveTo(x, y, dur) {
    ensure();
    const sx = state.x, sy = state.y, dx = x - sx, dy = y - sy;
    if (dur <= 0 || (dx === 0 && dy === 0)) { setPos(x, y); return; }
    let start = null;
    const step = (ts) => {
      if (start === null) start = ts;
      const p = Math.min(1, (ts - start) / dur);
      const e = easeInOutCubic(p);
      setPos(sx + dx * e, sy + dy * e);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
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
  // Scroll tweened on requestAnimationFrame (never the browser's native smooth
  // scroll, which runs on compositor time the faked clock cannot hold).
  // `within` names the scroll container (null = the page); `mode` is 'top',
  // 'bottom', 'by' (arg = px) or 'into' (arg = a selector centred in view).
  function tweenScroll(within, mode, arg, dur) {
    const box = within ? document.querySelector(within) : document.scrollingElement;
    if (!box) return;
    const from = box.scrollTop, max = box.scrollHeight - box.clientHeight;
    let to = mode === 'bottom' ? max : mode === 'by' ? from + arg : 0;
    if (mode === 'into') {
      const el = document.querySelector(arg);
      if (!el) return;
      const top = within ? box.getBoundingClientRect().top : 0;
      const r = el.getBoundingClientRect();
      to = from + (r.top - top) - (box.clientHeight - r.height) / 2;
    }
    to = Math.max(0, Math.min(max, to));
    let start = null;
    const step = (ts) => {
      if (start === null) start = ts;
      const p = dur > 0 ? Math.min(1, (ts - start) / dur) : 1;
      box.scrollTop = from + (to - from) * easeInOutCubic(p);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  // One frame of Web Animations time. CSS transitions and keyframe animations run
  // on the compositor, outside the faked clock, so each one is paused, seated at
  // its start the first time it is seen, then advanced by `dt` per captured frame.
  const seenAnims = new WeakSet();
  function stepAnimations(dt) {
    for (const a of document.getAnimations()) {
      if (a.playState === 'finished' || a.playState === 'idle') continue;
      if (!seenAnims.has(a)) { seenAnims.add(a); a.pause(); a.currentTime = 0; }
      else if (a.playState === 'running') a.pause();
      const end = a.effect ? a.effect.getComputedTiming().endTime : Infinity;
      const t = (a.currentTime || 0) + dt * (a.playbackRate || 1);
      if (t >= end) a.finish(); else a.currentTime = t;
    }
  }
  function setRange(sel, frac, x, y) {
    const el = document.querySelector(sel);
    if (!el) return;
    const min = parseFloat(el.min || '0'), max = parseFloat(el.max || '1');
    el.value = min + (max - min) * frac;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    setPos(x, y);
  }

  window.__demo = { ensure, setPos, moveTo, press, tweenScroll, stepAnimations,
                    setRange, pos: () => ({ x: state.x, y: state.y }) };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ensure);
  else ensure();
})();
"""

# Launch args. Two groups:
# - keep timers/animation running even if the window loses focus;
# - force real-GPU rendering via ANGLE-over-desktop-GL. Without this, *headless*
#   Chromium falls back to the SwiftShader software renderer. With frame-stepped
#   capture that only costs wall-clock time (never smoothness), so `gl="swiftshader"`
#   is the fallback where no GPU is reachable.
_BASE_ARGS = [
    "--autoplay-policy=no-user-gesture-required",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--ignore-gpu-blocklist",
    "--enable-webgl",
]
_GL_ARGS = {
    "gpu": ["--use-gl=angle", "--use-angle=gl", "--enable-gpu"],
    "swiftshader": ["--use-gl=angle", "--use-angle=swiftshader"],
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _ease(t: float) -> float:
    """easeInOutCubic."""
    return 4 * t * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2


class Demo:
    """A scripted, frame-captured browser session over a single page.

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
        scale: float = 2,          # device pixel ratio: frames are width*scale wide
        fps: int = 60,             # capture rate (the AV1 keeps it; WebP may decimate)
        headless: bool = True,
        gl: str = "gpu",           # "gpu" or "swiftshader" (see _GL_ARGS)
        cursor: bool = True,
        init_scripts: tuple[str, ...] = (),  # run before the page's own scripts
        # Cursor glide tuning.
        cursor_speed: float = 1600.0,   # px/s; glide duration derives from distance
        min_glide_ms: int = 220,
        max_glide_ms: int = 1100,
        # Fail fast on a bad selector instead of Playwright's 30s default.
        action_timeout: int = 8000,
        # Animated WebP (the README hero).
        webp: bool = True,
        webp_fps: int = 24,
        webp_width: int | None = 1280,  # None keeps the capture width
        webp_quality: int = 75,         # libwebp 0-100 (barely moves the size: frame count does)
        # AV1 master.
        av1: bool = True,
        av1_out: str | None = None,      # basename for the .av1.mp4 (defaults to `out`)
        av1_width: int | None = 1920,
        av1_encoder: str = "libsvtav1",  # or "av1_nvenc" for GPU
        av1_crf: int = 36,
        av1_preset: int = 6,             # libsvtav1: 0 (slow/best) .. 13 (fast)
        # GIF (gifski), off by default: WebP replaces it.
        gif: bool = False,
        gif_fps: int = 20,
        gif_width: int | None = 640,
        gif_quality: int = 90,
        keep_frames: bool = False,       # keep the PNG frames dir (path is logged)
        quiet: bool = False,
    ) -> None:
        self.url = url
        self.out = Path(out)
        self.width = width
        self.height = height
        self.scale = scale
        self.fps = fps
        self.headless = headless
        self.gl = gl
        self.cursor = cursor
        self.init_scripts = init_scripts
        self.cursor_speed = cursor_speed
        self.min_glide_ms = min_glide_ms
        self.max_glide_ms = max_glide_ms
        self.action_timeout = action_timeout
        self.webp = webp
        self.webp_fps = webp_fps
        self.webp_width = webp_width
        self.webp_quality = webp_quality
        self.av1 = av1
        self.av1_out = Path(av1_out) if av1_out else None
        self.av1_width = av1_width
        self.av1_encoder = av1_encoder
        self.av1_crf = av1_crf
        self.av1_preset = av1_preset
        self.gif = gif
        self.gif_fps = gif_fps
        self.gif_width = gif_width
        self.gif_quality = gif_quality
        self.keep_frames = keep_frames
        self.quiet = quiet

        self.cx = width / 2.0
        self.cy = height / 2.0
        self._pw = None
        self._browser = None
        self.context = None
        self.page = None
        self._cdp = None
        self._frames_dir = None
        self._recording = False
        self._n = 0              # frames captured
        self._t_ms = 0.0         # virtual time since begin(), in ms
        self._wall0 = 0.0

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> "Demo":
        self._log(f"launching chromium (headless={self.headless}, gl={self.gl}) -> {self.url}")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless, args=_BASE_ARGS + _GL_ARGS[self.gl])
        self.context = self._browser.new_context(
            viewport={"width": self.width, "height": self.height},
            device_scale_factor=self.scale,
        )
        # The helper is always injected (slider/glide use it); the visible cursor
        # element is suppressed when cursor=False.
        if not self.cursor:
            self.context.add_init_script("window.__DEMO_NO_CURSOR = true;")
        for script in self.init_scripts:
            self.context.add_init_script(script)
        self.context.add_init_script(CURSOR_JS)
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.action_timeout)
        self.page.clock.install()  # runs in real time until begin() pauses it
        self._cdp = self.context.new_cdp_session(self.page)
        self._frames_dir = Path(tempfile.mkdtemp(prefix="demo-frames-"))
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
            if self._frames_dir and not self.keep_frames:
                shutil.rmtree(self._frames_dir, ignore_errors=True)
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

    def wait(self, ms: float) -> "Demo":
        """Let `ms` of page time pass: captured frame by frame once begin() ran."""
        if not self._recording:
            self.page.wait_for_timeout(ms)
            return self
        for _ in range(max(1, round(ms * self.fps / 1000.0))):
            self._frame()
        return self

    pause = wait

    def wait_for(self, selector: str, *, timeout: int = 60000) -> "Demo":
        """Block until `selector` is visible (e.g. the app is ready). Not while recording."""
        self.page.wait_for_selector(selector, state="visible", timeout=timeout)
        return self

    def wait_gone(self, selector: str, *, timeout: int = 60000) -> "Demo":
        """Block until `selector` is hidden or detached (e.g. a loading overlay)."""
        self.page.wait_for_selector(selector, state="hidden", timeout=timeout)
        return self

    def begin(self) -> "Demo":
        """Pause the page clock and start capturing; nothing before is recorded.

        Call once the app is ready (after a loading overlay clears) so the output
        does not show the boring startup.
        """
        now = self.page.evaluate("Date.now()")
        self.page.clock.pause_at(now + 1)
        self._recording = True
        self._wall0 = time.monotonic()
        self._log("capture started (clock paused, frame-stepped)")
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
        for ch in text:
            self.page.keyboard.type(ch)
            self.wait(delay)
        return self

    def key(self, name: str) -> "Demo":
        """Press a keyboard shortcut on the page body (e.g. 'm', 'Escape')."""
        self.page.keyboard.press(name)
        return self

    def scroll(self, selector: str | None = None, *, to: str | None = None,
               by: float | None = None, within: str | None = None,
               dur: int = 700) -> "Demo":
        """Tween a scroll: bring `selector` to the centre, or go `to` 'top'/'bottom',
        or scroll `by` px; inside the `within` container (default: the page)."""
        if selector is not None:
            mode, arg = "into", selector
        elif by is not None:
            mode, arg = "by", by
        else:
            mode, arg = (to or "top"), None
        self.page.evaluate("([w, m, a, d]) => window.__demo.tweenScroll(w, m, a, d)",
                           [within, mode, arg, dur])
        self.wait(dur)
        return self

    def slider(self, selector: str, to: float, *, dur: int = 2000) -> "Demo":
        """Drag a range <input> to fraction `to` in [0, 1], cursor riding the handle.

        One step per captured frame (each sets the value, fires 'input', and moves
        the cursor), eased in and out.
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
        steps = max(1, round(dur * self.fps / 1000.0))
        for i in range(1, steps + 1):
            frac = frm + (to - frm) * _ease(i / steps)
            cx = box["x"] + frac * box["width"]
            self.page.evaluate(
                "([s, f, x, y]) => window.__demo.setRange(s, f, x, y)",
                [selector, frac, cx, cy],
            )
            self.wait(1000.0 / self.fps)
        self.cx, self.cy = box["x"] + to * box["width"], cy
        return self

    def drag(self, frm, to, *, dur: int = 1500) -> "Demo":
        """Press at `frm`, move to `to` (viewport points) over `dur`, release.

        Eased, one mouse move per captured frame: rotates an orbit-controlled scene.
        """
        (x0, y0), (x1, y1) = frm, to
        self._glide(x0, y0, None)
        self.page.mouse.move(x0, y0)
        self.page.mouse.down()
        steps = max(1, round(dur * self.fps / 1000.0))
        for i in range(1, steps + 1):
            e = _ease(i / steps)
            x, y = x0 + (x1 - x0) * e, y0 + (y1 - y0) * e
            self.page.mouse.move(x, y)
            if self.cursor:
                self.page.evaluate("([x, y]) => window.__demo.setPos(x, y)", [x, y])
            self.wait(1000.0 / self.fps)
        self.page.mouse.up()
        self.cx, self.cy = x1, y1
        return self

    def zoom(self, steps: int = 4, *, at=None, delta: int = -240, pause: int = 150) -> "Demo":
        """Dolly the camera by wheel-scrolling over the scene.

        Negative `delta` zooms in (OrbitControls dolly). `at` is the (x, y) point to
        scroll over (defaults to right-of-panel centre, so it lands on the canvas).
        """
        ax, ay = at if at else (self.width * 0.62, self.height * 0.5)
        self.page.mouse.move(ax, ay)
        if self.cursor:
            self.page.evaluate("([x, y]) => window.__demo.setPos(x, y)", [ax, ay])
            self.cx, self.cy = ax, ay
        for _ in range(max(1, steps)):
            self.page.mouse.wheel(0, delta)
            self.wait(pause)
        return self

    # -- internals ----------------------------------------------------------

    def _frame(self) -> None:
        """Advance page time by one frame, then capture it."""
        step = 1000.0 / self.fps
        # The fake clock takes whole milliseconds: alternate 16/17 for 60 fps.
        ticks = round(self._t_ms + step) - round(self._t_ms)
        self._t_ms += step
        self.page.clock.run_for(ticks)
        self.page.evaluate("(dt) => window.__demo.stepAnimations(dt)", ticks)
        # The clip's own `scale` is what yields device pixels: CDP alone answers at 1x.
        shot = self._cdp.send("Page.captureScreenshot", {"format": "png", "clip": {
            "x": 0, "y": 0, "width": self.width, "height": self.height, "scale": self.scale}})
        (self._frames_dir / f"f{self._n:05d}.png").write_bytes(base64.b64decode(shot["data"]))
        self._n += 1
        if self._n % (self.fps * 2) == 0:
            self._log(f"captured {self._n} frames ({self._n / self.fps:.0f}s of clip,"
                      f" {time.monotonic() - self._wall0:.0f}s wall)")

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
            "([x, y, d]) => { window.__demo.moveTo(x, y, d); }", [x, y, duration]
        )
        self.wait(duration)
        self.cx, self.cy = x, y

    # -- post-processing ----------------------------------------------------

    def _finalize(self, success: bool) -> None:
        self._browser.close()
        self._pw.stop()
        if not success:
            self._log("note: finalized despite a scripting error (partial demo)")
        if not self._n:
            self._log("no frames captured (begin() never ran): nothing to encode")
            return
        self._log(f"{self._n} frames ({self._n / self.fps:.1f}s @ {self.fps}fps) in {self._frames_dir}")
        self.out.parent.mkdir(parents=True, exist_ok=True)
        if self.webp:
            self._encode_webp()
        if self.av1:
            self._encode_av1()
        if self.gif:
            self._encode_gif()

    def _frames_input(self) -> list[str]:
        return ["-framerate", str(self.fps), "-i", str(self._frames_dir / "f%05d.png")]

    @staticmethod
    def _scale(width: int | None) -> str:
        return f"scale={width}:-2:flags=lanczos" if width else "null"

    def _encode_webp(self) -> None:
        dst = self.out.with_suffix(".webp")
        vf = f"fps={self.webp_fps},{self._scale(self.webp_width)}"
        self._run(["ffmpeg", "-y", *self._frames_input(), "-vf", vf,
                   "-c:v", "libwebp_anim", "-lossless", "0", "-quality", str(self.webp_quality),
                   "-compression_level", "6", "-loop", "0", str(dst)], "WebP encode")
        self._log(f"WebP: {dst} ({_size(dst)})")

    def _encode_av1(self) -> None:
        dst = (self.av1_out or self.out).with_suffix(".av1.mp4")
        dst.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-y", *self._frames_input(), "-vf", self._scale(self.av1_width),
               "-c:v", self.av1_encoder, "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        if self.av1_encoder == "libsvtav1":
            cmd += ["-crf", str(self.av1_crf), "-preset", str(self.av1_preset)]
        elif self.av1_encoder == "av1_nvenc":
            cmd += ["-cq", str(self.av1_crf), "-preset", "p5"]
        else:
            cmd += ["-crf", str(self.av1_crf)]
        cmd += [str(dst)]
        self._run(cmd, "AV1 encode")
        self._log(f"AV1: {dst} ({_size(dst)})")

    def _encode_gif(self) -> None:
        dst = self.out.with_suffix(".gif")
        # gifski reads the PNGs itself; every (fps/gif_fps)-th frame keeps the pace.
        frames = sorted(self._frames_dir.glob("f*.png"))[::max(1, round(self.fps / self.gif_fps))]
        cmd = ["gifski", "-r", str(self.gif_fps), "-Q", str(self.gif_quality), "-o", str(dst)]
        if self.gif_width:
            cmd += ["--width", str(self.gif_width)]
        self._run(cmd + [str(f) for f in frames], "gifski")
        self._log(f"GIF: {dst} ({_size(dst)}, {len(frames)} frames @ {self.gif_fps}fps)")

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
