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


def back_to_settings(d: Demo) -> None:
    """Esc closes the active detail tab, re-showing the Settings pane + its toolbar.

    Opening a detail hides the Settings pane (where the search/reset buttons live).
    Esc is global, so it works whether or not a detail tab is currently open.
    """
    d.key("Escape")
    d.wait(500)


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
        gif_quality=92,
        av1_crf=30,
    ) as d:
        d.wait(3800)                    # the regions assemble (intro animation)

        search(d, "fluoxetine", watch=5200)   # SSRI: serotonergic dots + flow fan
        back_to_settings(d)

        d.key("c")                      # See inside: reveal the deep nuclei
        d.wait(2200)
        d.key("c")
        d.wait(700)

        search(d, "D2", watch=4200)     # a dopamine receptor: expression cloud
        back_to_settings(d)

        d.click("#reset-view")          # recenter / reframe
        d.wait(1600)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="neurarium_demo", help="output basename")
    ap.add_argument("--gif-fps", type=int, default=30, help="GIF framerate (smoothness)")
    ap.add_argument("--headless", action="store_true", help="record without a visible window")
    args = ap.parse_args()

    server = subprocess.Popen(
        [sys.executable, "tools/serve.py", "--port", str(PORT)],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(PORT)
        run_tour(args.out, args.gif_fps, args.headless)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
