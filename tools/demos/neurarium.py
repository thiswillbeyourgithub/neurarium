# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.40"]
# ///
"""Record the showcase demos of neurarium (built with the help of Claude Code).

Serves the local site with `tools/serve.py`, drives a short scripted story with a
visible cursor, and writes `docs/images/<name>.webp` (shown in the README) +
`docs/videos/<name>.av1.mp4`.

    uv run tools/demos/neurarium.py                   # every story
    uv run tools/demos/neurarium.py --story compare   # one story
    # or, if playwright is on your PATH already:
    python tools/demos/neurarium.py [--story NAME] [--fps 60] [--headed]

Stories (STORIES below, name -> output basename):

- drug (`preview`, the README hero): the whole brain turning, blown apart, then
  olanzapine searched (gem dots + effect flow), ending on its graded binding list.
- anatomy (`demo-anatomy`): explode + reassemble, the hippocampus isolated, the
  Papez circuit pulsing, then fluoxetine's serotonergic flow.
- compare (`demo-compare`): haloperidol's narrow D2 profile, then clozapine's broad one.
- drugsmap (`demo-drugsmap`): the drugs map page, its antipsychotic presets, then
  a few drugs hovered.
- receptor (`demo-receptor`): 5-HT2A's expression regions, the drugs that bind it,
  then LSD picked from that list.

They rely only on stable hooks (the explode slider, the search box, the detail
pane's guided-tour `data-tour-*` anchors, the drugs map's `data-preset` buttons and
`data-drug` dots), so they stay robust as the dataset grows.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Callable, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recorder import Demo  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
PANE = "#details-pane"

# A recorded visit is not a first visit: skip the coach-mark tour and the
# "What's new" popup (any version string above the current one marks it read).
SEEN_SCRIPT = ("localStorage.setItem('neurarium:tourSeen', '1');"
               "localStorage.setItem('neurarium.changelogSeen', '999.0.0');")


def section(tour_sec: str) -> str:
    """A detail-pane section's folded header, by its guided-tour anchor (the fold
    keeps the hook on the <details> itself or on the block inside its body)."""
    return (f'{PANE} details[data-tour-sec="{tour_sec}"] > summary,'
            f' {PANE} summary:has(+ .panel-sec-body [data-tour-sec="{tour_sec}"])')


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


def boot(d: Demo, *, zoom: int = 3) -> None:
    """Load the atlas off camera, then start capturing on the whole brain."""
    d.page.set_default_timeout(120000)
    # The overlay ends on a "Start exploring" button whose click starts the
    # assemble intro; the overlay then removes itself.
    d.wait_for("#loading-start", timeout=180000)
    d.page.evaluate("document.getElementById('loading-start').click()")
    d.wait_gone("#loading", timeout=60000)
    d.wait(2600)                          # let the assemble intro finish
    d.zoom(zoom)                          # dolly in so the brain fills the frame
    d.wait(400)
    d.page.set_default_timeout(8000)
    d.begin()                             # capture starts on the whole brain, auto-rotating


def search(d: Demo, term: str, *, watch: int) -> None:
    """Open search, run `term`, take the top hit."""
    if not d.page.locator("#search-input").is_visible():
        # The toolbar button sits in the Settings pane, hidden while a detail tab
        # is open; Ctrl+F opens the same search box from anywhere.
        if d.page.locator("#search-toggle").is_visible():
            d.click("#search-toggle")
        else:
            d.key("Control+f")
        d.wait(400)
    d.click("#search-input")
    d.key("Control+a")                    # replace a previous query
    d.type("#search-input", term, click_first=False, delay=70)
    d.wait(700)
    d.key("Enter")                        # activates the pre-highlighted first result
    d.wait(watch)


def open_and_scroll(d: Demo, tour_sec: str, *, by: int = 300) -> None:
    """Bring a folded panel section into view, open it, scroll through it."""
    d.scroll(section(tour_sec), within=PANE, dur=1000)
    d.click(section(tour_sec), settle=700)
    d.move((900, 640))                    # park the cursor off the rows (no grade tooltip)
    d.scroll(within=PANE, by=by, dur=1800)


def story_drug(d: Demo) -> None:
    boot(d)
    d.wait(2200)
    d.slider("#explode", 1.0, dur=2200)   # blow the brain apart -> deep nuclei revealed
    d.wait(900)
    search(d, "olanzapine", watch=1600)   # gem dots on its targets' regions + effect flow
    d.zoom(4, at=(820, 360))              # the focus frames from afar: close in on the flow
    d.wait(4000)
    open_and_scroll(d, "bindings")        # the sourced, graded binding rows
    d.wait(2400)


def story_anatomy(d: Demo) -> None:
    boot(d)
    d.wait(1200)
    d.slider("#explode", 1.0, dur=1800)
    d.wait(500)
    d.slider("#explode", 0.0, dur=1600)
    d.wait(500)
    search(d, "hippocampus", watch=1800)  # isolated, haloed, its panel + picture
    d.zoom(4, at=(820, 360), delta=240)   # the focus frames it from inside: pull back
    d.wait(1400)
    search(d, "Papez", watch=4500)        # the circuit isolated, beads pulsing along it
    search(d, "fluoxetine", watch=1500)
    d.zoom(4, at=(820, 360))
    d.wait(3500)


def story_compare(d: Demo) -> None:
    boot(d)
    d.wait(1000)
    d.slider("#explode", 1.0, dur=1600)
    d.wait(400)
    search(d, "haloperidol", watch=1200)  # narrow: dopamine D2 blockade
    d.zoom(4, at=(820, 360))
    d.wait(3500)
    open_and_scroll(d, "bindings", by=200)
    d.wait(1200)
    search(d, "clozapine", watch=1200)    # broad: dozens of receptors light up
    d.zoom(4, at=(820, 360))
    d.wait(3300)
    open_and_scroll(d, "bindings", by=420)
    d.wait(2000)


def story_drugsmap(d: Demo) -> None:
    d.page.set_default_timeout(120000)
    d.wait_for("[data-preset='ap_side']", timeout=120000)
    d.wait_for("circle.dm-point", timeout=120000)
    d.wait(1500)
    d.page.set_default_timeout(8000)
    d.begin()
    d.wait(1500)
    dot = "circle.dm-point[data-drug='{}']".format
    d.hover(dot("clozapine"), hold=1300)                  # every drug by its whole binding profile
    d.click("[data-preset='ap_d2_5ht2a']", settle=2200)   # D2 against 5-HT2A, the atypicality plot
    for drug in ("haloperidol", "aripiprazole"):
        d.hover(dot(drug), hold=1300)
    d.click("[data-preset='ap_side']", settle=2200)       # side-effect receptors
    for drug in ("clozapine", "olanzapine"):
        d.hover(dot(drug), hold=1300)
    d.wait(800)


def story_receptor(d: Demo) -> None:
    boot(d)
    d.wait(1000)
    d.slider("#explode", 1.0, dur=1600)
    d.wait(400)
    search(d, "5-HT2A", watch=1200)       # gem dots on the regions expressing it
    d.zoom(4, at=(820, 360))
    d.wait(3000)
    open_and_scroll(d, "drugs", by=200)   # every drug that binds it, by affinity
    d.wait(800)
    lsd = f'{PANE} [data-tour-id="ixdrug:lsd"]'
    d.scroll(lsd, within=PANE, dur=900)
    d.click(lsd, settle=1200)             # jump to LSD: its own flow
    d.zoom(4, at=(820, 360))
    d.wait(4000)


class Story(NamedTuple):
    run: Callable[[Demo], None]
    base: str                 # output basename under docs/images + docs/videos
    path: str = ""            # start page
    height: int = 720         # viewport height (the drugs map needs its whole chart)
    webp_width: int = 1280    # the dense flow of `compare` would weigh ~12 MB at 1280


STORIES = {
    "drug": Story(story_drug, "preview"),
    "anatomy": Story(story_anatomy, "demo-anatomy"),
    "compare": Story(story_compare, "demo-compare", webp_width=960),
    "drugsmap": Story(story_drugsmap, "demo-drugsmap", "drugs-map.html", height=1240),
    "receptor": Story(story_receptor, "demo-receptor"),
}


def record(port: int, name: str, args: argparse.Namespace) -> None:
    story = STORIES[name]
    out_dir = Path(args.out_dir) if args.out_dir else None
    with Demo(
        f"http://localhost:{port}/{story.path}",
        out=str((out_dir or REPO_ROOT / "docs" / "images") / story.base),
        av1_out=str((out_dir or REPO_ROOT / "docs" / "videos") / story.base),
        height=story.height,
        webp_width=story.webp_width,
        fps=args.fps,
        headless=not args.headed,
        init_scripts=(SEEN_SCRIPT,),
        cursor_speed=1800,
        max_glide_ms=900,
        keep_frames=args.keep_frames,
    ) as d:
        story.run(d)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--story", choices=[*STORIES, "all"], default="all")
    ap.add_argument("--out-dir", help="write every output here instead of docs/images + docs/videos")
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
        for name in (STORIES if args.story == "all" else [args.story]):
            print(f"[neurarium] story: {name}", flush=True)
            record(port, name, args)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
