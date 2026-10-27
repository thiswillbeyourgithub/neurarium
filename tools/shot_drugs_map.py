#!/usr/bin/env python
# /// script
# requires-python = ">=3.9"
# dependencies = ["playwright>=1.40"]
# ///
"""Render the drugs map README picture (public/drugs-map/screenshot.png).

Loads ``drugs-map.html`` with a fixed view in its URL hash (the map's own ``dm*``
keys, see docs/RUNNING.md), unfolds the Legend and "Axis meaning" boxes, hides
everything else (page header, control boxes, footnote, plot buttons, watermark),
then screenshots the map body. Rerun it whenever the map's UI changes so the README
picture stays current::

    uv run tools/shot_drugs_map.py                       # -> public/drugs-map/screenshot.png
    uv run tools/shot_drugs_map.py --hash "#dmcat=ssri" --out /tmp/ssri.png

The picture lives next to the README (not in docs/images/) so the relative link
works both on GitHub and on the copy the site serves. It reuses ``tools/shot.py``'s
throwaway dev server; the map is SVG, so no WebGL flags are needed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot import REPO_ROOT, dev_server  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "public" / "drugs-map" / "screenshot.png"

# The README's view: the two antipsychotic classes, withdrawn drugs included, on
# the dopamine / cholinergic / histamine targets only, so the PCA axes read as
# "D2-family blockade vs anticholinergic / antihistaminic load".
DEFAULT_HASH = (
    "#dmcat=antipsychotic_atypical,antipsychotic_conventional&dmmkt=0"
    "&dmtgt=aadc,comt,d1,d2,d3,d4,d5,dat,mao_b,vmat2,ache,bche,m1,m2,m3,m4,m5,"
    "nachr_a4b2,nachr_a7,h1,h2,h3,h4"
)

# Keep the plot, the Legend and the "Axis meaning" boxes, hide the rest. The map
# body's first children are the control boxes (js/drug-map/controls.js), then the
# plot, the two boxes below it and a footnote (js/drug-map/view.js).
HIDE_CSS = """
.dmp-header, #drugmap-body > .dm-box:not(.dm-keep), .dm-note,
.dm-plot-btn, .dm-watermark { display: none !important; }
"""

UNFOLD_BELOW_PLOT = """() => {
  const body = document.getElementById("drugmap-body");
  const plot = body.querySelector(".dm-plot-wrap");
  let el = plot.nextElementSibling;
  while (el) {
    if (el.tagName === "DETAILS") { el.open = true; el.classList.add("dm-keep"); }
    el = el.nextElementSibling;
  }
}"""


def main() -> int:
    """Parse the CLI, capture the picture, return a process exit code."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hash", default=DEFAULT_HASH, help="the map view, as a URL hash")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="PNG to write")
    ap.add_argument("--width", type=int, default=1000, help="viewport width, CSS px")
    ap.add_argument("--lang", choices=("en", "fr"), default="en")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    with dev_server() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": args.width, "height": 900}, device_scale_factor=2)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(f"try {{ localStorage.setItem('neurarium:lang', '{args.lang}'); }} catch (e) {{}}")
        page.goto(f"{base}drugs-map.html{args.hash}")
        page.wait_for_selector("#drugmap-body circle", timeout=30000)
        page.evaluate(UNFOLD_BELOW_PLOT)
        page.add_style_tag(content=HIDE_CSS)
        # Hiding the header resizes the plot, which re-renders it behind the busy
        # spinner: wait for that render to finish, then for the dots to slide home.
        page.wait_for_timeout(300)
        page.wait_for_selector(".dm-busy", state="hidden", timeout=30000)
        page.wait_for_timeout(1500)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        page.locator("#drugmap-body").screenshot(path=str(args.out))
        browser.close()
    if errors:
        print("page errors:", *errors, sep="\n  ", file=sys.stderr)
        return 1
    print(f"wrote {args.out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
