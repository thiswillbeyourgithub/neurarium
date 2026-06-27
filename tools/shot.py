#!/usr/bin/env python
# /// script
# requires-python = ">=3.9"
# dependencies = ["playwright>=1.40", "pillow>=10"]
# ///
"""Render the neurarium viewer to a PNG with a real (headless) browser.

One self-contained command: it serves the repo with ``tools/serve.py``, drives a
headless Chromium (Playwright) to load ``index.html`` with optional ``?view``
params, captures the canvas, then shuts the server back down. No X session and no
window grabbing: Playwright's own ``page.screenshot()`` captures the WebGL canvas
directly, as long as Chromium is told to use the SwiftShader GL backend (the
``GL_ARGS`` below) so headless WebGL actually renders instead of coming back
blank. (Same idea as simonw's ``shot-scraper``, just self-contained and aware of
this repo's no-cache dev server.) The capture is then auto-cropped to the
rendered content (everything that differs from the flat background), keeping a
small margin, so the subject fills the frame; pass ``--no-crop`` to keep the full
viewport.

Run it::

    python tools/shot.py                       # -> docs/screenshot.png (hero shot)
    python tools/shot.py --params "only=putamen_R&view=iso" --out /tmp/p.png
    uv run tools/shot.py                        # same, deps auto-installed by uv

The browser binary is needed once: ``playwright install chromium`` (or
``uv run --with playwright playwright install chromium``).

``--params`` is the URL query parsed by ``applyViewParams()`` in ``js/main.js``,
so the same keys also deep-link a view in a normal browser: ``only=``, ``view=``
(front|back|left|right|top|bottom|iso), ``explode=``, ``transparency=``,
``names=all``, ``autorotate=1``, ``ui=0``. See CLAUDE.md.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import closing, contextmanager
from pathlib import Path

# Repo root = parent of this tools/ directory. The web root is public/ (served
# by tools/serve.py's default --root); docs/screenshot.png stays under the repo
# root, so DEFAULT_OUT keeps using REPO_ROOT.
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "docs" / "screenshot.png"

# Hero-shot defaults: exploded enough to lift the cortex off the deep nuclei and
# reveal the projection arrows, framed isometric, with the UI panels hidden.
DEFAULT_PARAMS = "explode=0.45&view=iso&ui=0"

# Headless Chromium only renders WebGL when a software GL backend is wired up;
# these flags select SwiftShader via ANGLE. Without them index.html's canvas
# comes back blank (which is what the old --headed X11 grabbing worked around).
GL_ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--ignore-gpu-blocklist"]


def _free_port() -> int:
    """Pick an unused localhost TCP port for the throwaway dev server."""
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_up(url: str, timeout: float = 20.0) -> bool:
    """Poll ``url`` until it answers (the dev server has finished binding)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def _autocrop(path: Path, margin: int) -> None:
    """Crop ``path`` down to the rendered subject, then re-pad by ``margin`` px.

    The scene draws on a single flat background colour, so anything differing
    from the corner pixel is "content". We crop to the bounding box of that
    content and add ``margin`` pixels of breathing room on each side so the
    subject is not flush against the edge. No-op if the frame is all background.
    """
    from PIL import Image, ImageChops

    image = Image.open(path).convert("RGB")
    background = Image.new("RGB", image.size, image.getpixel((0, 0)))
    # Render background is perfectly flat, so a tiny threshold (ignore <=8/255
    # differences) cleanly separates content without clipping faint arrow glow.
    diff = ImageChops.difference(image, background).convert("L")
    box = diff.point(lambda level: 255 if level > 8 else 0).getbbox()
    if box is None:
        return
    left, top, right, bottom = box
    crop = (
        max(0, left - margin),
        max(0, top - margin),
        min(image.width, right + margin),
        min(image.height, bottom + margin),
    )
    image.crop(crop).save(path)


@contextmanager
def dev_server():
    """Serve the repo with tools/serve.py on a free port; yield its base URL.

    A context manager so the throwaway server is always torn down. Shared by
    this module's ``main()`` and ``tools/sculpt_shot.py`` (which captures many
    angles of one structure), so the serve/teardown lives in one place.
    """
    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "tools" / "serve.py"), "--port", str(port)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://localhost:{port}/"
        if not _wait_until_up(base):
            raise RuntimeError("dev server did not come up")
        yield base
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            server.kill()


def capture(page, url: str, out: Path, wait: int, crop: bool = True,
            margin: int = 40) -> Path:
    """Load ``url`` in ``page``, let it render ``wait`` ms, screenshot to ``out``.

    Hides eruda's debug button (irrelevant to a shot) and optionally auto-crops
    to the rendered subject. Returns ``out``. Shared capture step so the viewer
    quirks (load wait, eruda hide, crop) are handled identically everywhere.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    page.goto(url, wait_until="load")
    page.wait_for_timeout(wait)
    page.evaluate(
        "document.querySelector('#eruda')"
        "?.style.setProperty('display', 'none', 'important')"
    )
    page.screenshot(path=str(out))
    if crop:
        _autocrop(out, margin)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Screenshot the neurarium viewer.")
    parser.add_argument(
        "--out", default=str(DEFAULT_OUT),
        help=f"output PNG (default: {DEFAULT_OUT.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--params", default=DEFAULT_PARAMS,
        help="URL query for the viewer (applyViewParams keys); '' for none",
    )
    parser.add_argument("--width", type=int, default=1280, help="viewport width (default 1280)")
    parser.add_argument("--height", type=int, default=800, help="viewport height (default 800)")
    parser.add_argument(
        "--scale", type=float, default=2.0,
        help="device scale factor for a crisp PNG (default 2)",
    )
    parser.add_argument(
        "--wait", type=int, default=6000,
        help="ms to let the scene load + render before capture (default 6000)",
    )
    parser.add_argument(
        "--headed", action="store_true",
        help="open a real (visible) browser window instead of headless; needs a "
             "display, uses the real GPU rather than SwiftShader",
    )
    parser.add_argument(
        "--margin", type=int, default=40,
        help="px of breathing room kept around the content after auto-crop "
             "(default 40)",
    )
    parser.add_argument(
        "--no-crop", dest="crop", action="store_false",
        help="keep the full viewport instead of cropping to the rendered content",
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is required. Install it with `pip install playwright` "
            "(or just run `uv run tools/shot.py`), then `playwright install "
            "chromium` once for the browser binary.",
            file=sys.stderr,
        )
        return 2

    try:
        with dev_server() as base:
            url = base + (f"?{args.params}" if args.params else "")
            out = Path(args.out)

            with sync_playwright() as playwright:
                # Headless needs the SwiftShader flags or WebGL is blank; a real
                # headed window has a GPU and should not be forced onto software GL.
                launch_args = [] if args.headed else GL_ARGS
                try:
                    browser = playwright.chromium.launch(
                        headless=not args.headed, args=launch_args,
                    )
                except Exception as exc:  # missing browser binary, etc.
                    print(
                        f"Could not launch Chromium ({exc}).\n"
                        "Run `playwright install chromium` once to fetch it.",
                        file=sys.stderr,
                    )
                    return 2
                page = browser.new_page(
                    viewport={"width": args.width, "height": args.height},
                    device_scale_factor=args.scale,
                )
                capture(page, url, out, args.wait, crop=args.crop, margin=args.margin)
                browser.close()

            print(f"wrote {out} ({args.params or 'default view'})")
            return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
