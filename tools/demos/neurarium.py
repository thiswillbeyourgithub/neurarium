# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.40"]
# ///
"""Record a showcase demo of neurarium (built with the help of Claude Code).

Serves the local site with `tools/serve.py`, drives a short scripted tour with a
visible cursor, and writes `docs/images/preview.webp` (the README hero) +
`docs/videos/preview.av1.mp4`.

    uv run tools/demos/neurarium.py
    # or, if playwright is on your PATH already:
    python tools/demos/neurarium.py [--out NAME] [--fps 60] [--headed]

The story ("a drug in action"): the whole brain turning, blown apart to show the
deep nuclei, then one drug searched, which dims the brain, lights the regions its
targets sit in and plays its effect flow; the clip ends scrolling that drug's
sourced panel (bindings with their grade pills, kinetics). It relies only on
stable hooks (the explode slider, the search box, the detail pane), so it stays
robust as the dataset grows.
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
DRUG = "olanzapine"
PANE = "#details-pane"
# The binding list's folded section header (the fold keeps the guided-tour hook,
# on the <details> itself or on the block inside its body).
BINDINGS = (f'{PANE} details[data-tour-sec="bindings"] > summary,'
            f' {PANE} summary:has(+ .panel-sec-body [data-tour-sec="bindings"])')

# A recorded visit is not a first visit: skip the coach-mark tour and the
# "What's new" popup (any version string above the current one marks it read).
SEEN_SCRIPT = ("localStorage.setItem('neurarium:tourSeen', '1');"
               "localStorage.setItem('neurarium.changelogSeen', '999.0.0');")


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"server did not come up on :{port}")


def search(d: Demo, term: str, *, watch: int) -> None:
    """Open search, run `term`, take the top hit."""
    d.click("#search-toggle")
    d.wait(400)
    d.click("#search-input")
    d.type("#search-input", term, click_first=False, delay=70)
    d.wait(700)
    d.key("Enter")          # activates the pre-highlighted first result
    d.wait(watch)           # let the dots + flow overlay play


def run_tour(port: int, args: argparse.Namespace) -> None:
    with Demo(
        f"http://localhost:{port}/",
        out=args.out,
        av1_out=args.video_out,
        fps=args.fps,
        headless=not args.headed,
        init_scripts=(SEEN_SCRIPT,),
        cursor_speed=1800,
        max_glide_ms=900,
        keep_frames=args.keep_frames,
    ) as d:
        d.page.set_default_timeout(120000)
        # Boot in real time: the overlay ends on a "Start exploring" button whose
        # click starts the assemble intro; the overlay then removes itself.
        d.wait_for("#loading-start", timeout=180000)
        d.page.evaluate("document.getElementById('loading-start').click()")
        d.wait_gone("#loading", timeout=60000)
        d.wait(2600)                          # let the assemble intro finish
        d.zoom(3)                             # dolly in so the brain fills the frame
        d.wait(400)
        d.page.set_default_timeout(8000)
        d.begin()                             # capture starts on the whole brain, auto-rotating

        d.wait(2200)
        d.slider("#explode", 1.0, dur=2200)   # blow the brain apart -> deep nuclei revealed
        d.wait(900)
        search(d, DRUG, watch=1600)           # gem dots on its targets' regions + effect flow
        d.zoom(4, at=(820, 360))              # the focus frames from afar: close in on the flow
        d.wait(4000)
        # The drug's panel: open its binding profile (sections start folded) and
        # scroll through the sourced, graded rows.
        d.scroll(BINDINGS, within=PANE, dur=1000)
        d.click(BINDINGS, settle=700)
        d.scroll(within=PANE, by=300, dur=1800)
        d.wait(2400)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO_ROOT / "docs" / "images" / "preview"),
                    help="WebP output basename (default: docs/images/preview, the README asset)")
    ap.add_argument("--video-out", default=str(REPO_ROOT / "docs" / "videos" / "preview"),
                    help="AV1 output basename (default: docs/videos/preview)")
    ap.add_argument("--fps", type=int, default=60, help="capture framerate (the AV1 keeps it)")
    ap.add_argument("--headed", action="store_true", help="show a visible window")
    ap.add_argument("--keep-frames", action="store_true", help="keep the PNG frames (to re-encode)")
    args = ap.parse_args()

    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, "tools/serve.py", "--port", str(port)],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)
        run_tour(port, args)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
