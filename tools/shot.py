#!/usr/bin/env python
# /// script
# requires-python = ">=3.9"
# dependencies = ["playwright>=1.40"]
# ///
"""Render the Neurarium viewer to a PNG with a real (headless) browser.

One self-contained command: it serves the repo with ``tools/serve.py``, drives a
headless Chromium (Playwright) to load ``index.html`` with optional ``?view``
params, captures the canvas, then shuts the server back down. No X session and no
window grabbing: Playwright's own ``page.screenshot()`` captures the WebGL canvas
directly, as long as Chromium is told to use the SwiftShader GL backend (the
``GL_ARGS`` below) so headless WebGL actually renders instead of coming back
blank. (Same idea as simonw's ``shot-scraper``, just self-contained and aware of
this repo's no-cache dev server.)

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
from contextlib import closing
from pathlib import Path

# Repo root = parent of this tools/ directory; served as the web root.
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Screenshot the Neurarium viewer.")
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
            print("dev server did not come up", file=sys.stderr)
            return 1

        url = base + (f"?{args.params}" if args.params else "")
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)

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
            page.goto(url, wait_until="load")
            page.wait_for_timeout(args.wait)
            # eruda's on-screen debug button is irrelevant to a screenshot; hide
            # its host element so it never lands in the frame.
            page.evaluate(
                "document.querySelector('#eruda')"
                "?.style.setProperty('display', 'none', 'important')"
            )
            page.screenshot(path=str(out))
            browser.close()

        print(f"wrote {out} ({args.params or 'default view'})")
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
