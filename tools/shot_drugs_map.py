#!/usr/bin/env python
# /// script
# requires-python = ">=3.9"
# dependencies = ["playwright>=1.40"]
# ///
"""Render the drugs map README pictures (screenshot.<lang>.png + one per preset).

Loads ``drugs-map.html`` with a fixed view in its URL hash (the map's own ``dm*``
keys, see docs/RUNNING.md), unfolds the Legend and "Axis meaning" boxes, hides
everything else (page header, control boxes, footnote, plot buttons, watermark),
then screenshots the map body, once per UI language (README.md shows the English
picture, README.fr.md the French one). Then it clicks every preset button
(js/drug-map/presets.js, read off the page so a new preset needs no edit here),
saves ``presets/<id>.<lang>.png`` and rewrites each README's block between the
``<!-- presets:start -->`` / ``<!-- presets:end -->`` markers: a PRESET_COLUMNS-wide
table, one cell per preset holding its picture (linking the live map on that
preset's view, the URL hash the click produced) over the button's own label. The
``default`` preset is skipped: the map as it first opens needs no picture of its own. Rerun it
whenever the map's UI or the presets change so the README pictures stay current::

    uv run tools/shot_drugs_map.py                  # -> public/drugs-map/screenshot.{en,fr}.png + presets/
    uv run tools/shot_drugs_map.py --no-presets --lang fr --hash "#dmcat=ssri" --out-dir /tmp

The pictures live next to the READMEs (not in docs/images/) so the relative links
work both on GitHub and on the copy the site serves. It reuses ``tools/shot.py``'s
throwaway dev server; the map is SVG, so no WebGL flags are needed.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot import REPO_ROOT, dev_server  # noqa: E402

DEFAULT_OUT_DIR = REPO_ROOT / "public" / "drugs-map"
LANGS = ("en", "fr")
README = {"en": "README.md", "fr": "README.fr.md"}
LIVE_URL = "https://drugsmap.olicorne.org/"
PRESETS_START, PRESETS_END = "<!-- presets:start -->", "<!-- presets:end -->"
# Pictures per README table row: two keep each picture legible on a GitHub page.
PRESET_COLUMNS = 2
# Presets with no picture of their own (the default view is just the map as it opens).
SKIP_PRESETS = {"default"}

# The README's view: the two antipsychotic classes, withdrawn drugs included, on
# the dopamine / cholinergic / histamine targets only, so the PCA axes read as
# "D2-family blockade vs anticholinergic / antihistaminic load".
DEFAULT_HASH = (
    "#dmcat=antipsychotic_atypical,antipsychotic_conventional&dmmkt=0"
    "&dmtgt=aadc,comt,d1,d2,d3,d4,d5,dat,mao_b,vmat2,ache,bche,m1,m2,m3,m4,m5,"
    "nachr_a4b2,nachr_a7,h1,h2,h3,h4"
)

# Keep the plot and the Legend box (colour keys + axis meaning; its nested Extra details
# fold stays shut, UNFOLD_BELOW_PLOT only opens the body's own children), hide the rest.
# The map body's first children are the control boxes (js/drug-map/controls.js), then
# the plot, the Legend and a footnote (js/drug-map/view.js).
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


def open_map(page, base: str, view_hash: str, lang: str) -> None:
    """Load the map in ``lang`` on ``view_hash`` and wait for its first dots."""
    # i18n.js reads the stored choice (its STORAGE_KEY) before anything renders.
    page.add_init_script(f"try {{ localStorage.setItem('neurarium:lang', '{lang}'); }} catch (e) {{}}")
    page.goto(f"{base}drugs-map.html{view_hash}")
    page.wait_for_selector("#drugmap-body circle", timeout=30000)


def snap(page, out: Path) -> None:
    """Screenshot the plot + Legend + Axis meaning of the map on screen to ``out``."""
    page.evaluate(UNFOLD_BELOW_PLOT)
    page.add_style_tag(content=HIDE_CSS)
    # Hiding the header resizes the plot, which re-renders it behind the busy
    # spinner: wait for that render to finish, then for the dots to slide home.
    page.wait_for_timeout(300)
    page.wait_for_selector(".dm-busy", state="hidden", timeout=30000)
    page.wait_for_timeout(1500)
    out.parent.mkdir(parents=True, exist_ok=True)
    page.locator("#drugmap-body").screenshot(path=str(out))


def capture(page, base: str, view_hash: str, lang: str, out: Path) -> None:
    """Load the map in ``lang`` on ``view_hash`` and screenshot its plot + boxes to ``out``."""
    open_map(page, base, view_hash, lang)
    snap(page, out)


def capture_presets(new_page, base: str, lang: str, out_dir: Path) -> list[dict]:
    """Click every preset button, one fresh page each, and screenshot what it loads.

    Returns ``[{id, label, hash, img}]`` in button order, ``img`` relative to
    ``out_dir`` (where the READMEs live).
    """
    page = new_page()
    open_map(page, base, "", lang)
    buttons = page.eval_on_selector_all(
        "[data-preset]", "bs => bs.map(b => ({id: b.dataset.preset, label: b.textContent}))")
    page.close()
    shots = []
    for b in (b for b in buttons if b["id"] not in SKIP_PRESETS):
        page = new_page()
        open_map(page, base, "", lang)
        page.click(f"[data-preset='{b['id']}']")
        page.wait_for_timeout(300)
        # The click writes the view into the hash (js/url-state.js): that is the live link.
        view_hash = page.evaluate("location.hash")
        img = f"presets/{b['id']}.{lang}.png"
        snap(page, out_dir / img)
        page.close()
        shots.append({**b, "hash": view_hash, "img": img})
        print(f"wrote {out_dir / img}")
    return shots


def write_presets_block(readme: Path, shots: list[dict]) -> None:
    """Replace the README's presets block with a table of preset pictures, PRESET_COLUMNS wide.

    Each cell is the picture (linking the live map on that view) with its label under it;
    a last short row is padded with empty cells so the table stays rectangular.
    """
    cells = [f"[![{s['label']}]({s['img']})]({LIVE_URL}{s['hash']})<br>**{s['label']}**" for s in shots]
    cells += [""] * (-len(cells) % PRESET_COLUMNS)
    rows = [cells[i:i + PRESET_COLUMNS] for i in range(0, len(cells), PRESET_COLUMNS)]
    # GitHub needs a header row: an empty one keeps the pictures as the whole table.
    items = "\n".join(["|" + " |" * PRESET_COLUMNS, "|" + " --- |" * PRESET_COLUMNS]
                       + ["| " + " | ".join(r) + " |" for r in rows])
    text = readme.read_text(encoding="utf-8")
    block = re.compile(re.escape(PRESETS_START) + ".*?" + re.escape(PRESETS_END), re.S)
    if not block.search(text):
        raise SystemExit(f"{readme}: no {PRESETS_START} ... {PRESETS_END} markers")
    readme.write_text(block.sub(lambda _: f"{PRESETS_START}\n{items}\n{PRESETS_END}", text),
                      encoding="utf-8")
    print(f"updated {readme}")


def main() -> int:
    """Parse the CLI, capture one picture per language, return a process exit code."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hash", default=DEFAULT_HASH, help="the map view, as a URL hash")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                    help="where screenshot.<lang>.png is written")
    ap.add_argument("--width", type=int, default=1000, help="viewport width, CSS px")
    ap.add_argument("--lang", choices=LANGS, action="append",
                    help="UI language to render (repeatable; default: every one)")
    ap.add_argument("--no-presets", action="store_true",
                    help="skip the preset pictures and the READMEs' presets block")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    errors: list[str] = []
    with dev_server() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        for lang in args.lang or LANGS:
            # A fresh page per language: the init script that picks it is per page.
            def new_page(lang=lang):
                page = browser.new_page(viewport={"width": args.width, "height": 900}, device_scale_factor=2)
                page.on("pageerror", lambda e: errors.append(f"{lang}: {e}"))
                return page

            page = new_page()
            out = args.out_dir / f"screenshot.{lang}.png"
            capture(page, base, args.hash, lang, out)
            page.close()
            print(f"wrote {out}")
            if not args.no_presets:
                shots = capture_presets(new_page, base, lang, args.out_dir)
                write_presets_block(args.out_dir / README[lang], shots)
        browser.close()
    if errors:
        print("page errors:", *errors, sep="\n  ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
