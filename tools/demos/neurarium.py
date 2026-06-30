# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.40"]
# ///
"""Record a showcase demo of neurarium (built with the help of Claude Code).

Serves the local site with `tools/serve.py`, drives a short scripted tour with a
visible cursor, and writes `neurarium_demo.av1.mp4` + `neurarium_demo.gif`.

    uv run tools/demos/neurarium.py
    # or, if playwright is on your PATH already:
    python tools/demos/neurarium.py [--out NAME] [--gif-fps 30] [--headless]

The tour relies only on stable hooks (toolbar buttons, the search box, and the
documented single-key shortcuts), so it stays robust as the dataset grows.
Selecting a drug/receptor from search auto-spreads the brain and plays the
flow overlay, which is the part worth showing.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recorder import Demo  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
PORT = 8123  # uncommon port so it does not clash with a dev server on 8000


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"server did not come up on :{port}")


def search(d: Demo, term: str, *, watch: int) -> None:
    """Open search, replace any remembered query, run `term`, take the top hit."""
    d.click("#search-toggle")
    d.wait(450)
    d.click("#search-input")
    d.key("Control+a")
    d.type("#search-input", term, click_first=False, delay=70)
    d.wait(900)
    d.key("Enter")          # activates the pre-highlighted first result
    d.wait(watch)           # let the dots + flow overlay play


def run_tour(out: str, gif_fps: int, headless: bool) -> None:
    with Demo(
        f"http://localhost:{PORT}/",
        out=out,
        headless=headless,
        gif_fps=gif_fps,
        gif_width=720,
        gif_quality=80,
        av1_crf=30,
        cursor_speed=2000,
        max_glide_ms=820,
    ) as d:
        d.wait_for("#explode")                # controls are in the page
        # Gate on the loading overlay being REMOVED from the DOM. That only happens
        # inside done() (500ms after meshing hits 100%); `hidden` can fire on a
        # transient mid-mesh. After this the scene is ready and the intro is playing.
        d.page.wait_for_selector("#loading", state="detached", timeout=60000)
        d.wait(400)                           # let the overlay's fade fully finish
        d.begin()                             # clean start: the startup load is all before this
        d.wait(1500)                          # the assemble intro (2.2s) finishes; regions settle

        d.slider("#explode", 1.0, dur=2200)   # blow the brain apart -> deep nuclei revealed
        d.wait(1100)
        d.slider("#explode", 0.0, dur=2000)   # the regions glide back into a whole brain
        d.wait(900)

        # Searching a drug auto-spreads the brain and plays its effect; end on it
        # (the auto-spread fights a manual reassemble, so this is the finale).
        search(d, "fluoxetine", watch=5000)   # SSRI: serotonergic gem dots + flow fan + sourced molecule panel


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO_ROOT / "docs" / "demo"),
                    help="output basename (default: docs/demo, the README asset)")
    ap.add_argument("--gif-fps", type=int, default=25, help="GIF framerate (smoothness)")
    # Record headless by default: it renders on the real GPU (via the recorder's
    # ANGLE flags) AND avoids Chromium's headed-mode video letterboxing (grey bar).
    # --headed shows a window but the headed video capture is unreliable here.
    ap.add_argument("--headed", action="store_true", help="show a visible window (headed video may letterbox)")
    args = ap.parse_args()

    server = subprocess.Popen(
        [sys.executable, "tools/serve.py", "--port", str(PORT)],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(PORT)
        run_tour(args.out, args.gif_fps, headless=not args.headed)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
