#!/usr/bin/env python
# /// script
# requires-python = ">=3.9"
# dependencies = ["playwright>=1.40", "pillow>=10"]
# ///
"""Render one structure from several angles into a labeled contact sheet.

This is the eye of the geometry_refinements refine loop (see
``geometry_refinements/CLAUDE.md``): author/adjust a structure's SDF spec,
regenerate the data, then run this to *see* the result from front / right / top /
iso at once and critique it against the reference images.

Two review modes:

* ``--mode only`` (default): isolate the structure (everything else hidden) and
  frame it tight, for judging silhouette and proportions.
* ``--mode context``: keep the whole brain visible but render only the target
  solidly while its neighbours are ghosted to a faint translucency, for judging
  fit / interpenetration. (Drives the viewer's ``solo=`` view param.)

It serves the repo and drives headless Chromium exactly like ``tools/shot.py``
(whose ``dev_server`` / ``capture`` it reuses, so there is one capture path), then
composes the frames with Pillow. It writes both the combined contact sheet and
the individual full-resolution frames, so a single angle can be inspected at full
detail without re-rendering.

    python tools/sculpt_shot.py putamen_R
    python tools/sculpt_shot.py putamen_R --mode context --explode 0.3
    uv run tools/sculpt_shot.py hippocampus_R --out /tmp/hippo.png

Headless WebGL needs the SwiftShader flags (baked into shot.GL_ARGS). In a
sandboxed shell the GL device can be blocked; run the command with the sandbox
disabled if the frames come back blank.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# tools/ is on sys.path[0] when run as a script, so the sibling shot module
# (serve + capture + GL flags, kept in one place to avoid a second copy) imports
# directly.
import shot

REPO_ROOT = Path(__file__).resolve().parent.parent
# Renders are scratch: geometry_refinements/renders/ is gitignored.
DEFAULT_RENDER_DIR = REPO_ROOT / "geometry_refinements" / "renders"
ANGLES = ("front", "right", "top", "iso")


def _params(structure_id: str, angle: str, mode: str, explode: float,
            ghost: float) -> str:
    """Build the viewer query string for one angle of one structure."""
    common = f"view={angle}&ui=0&explode={explode}"
    if mode == "context":
        return f"solo={structure_id}&ghost={ghost}&{common}"
    return f"only={structure_id}&{common}"


def _load_font(size: int):
    from PIL import ImageFont
    try:  # Pillow >= 10.1 sizes the bundled bitmap font
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _compose(frames: list[tuple[str, Path]], out: Path, title: str,
             cell: int) -> None:
    """Lay the captured frames out as a labeled grid and save to ``out``.

    ``frames`` is a list of ``(label, png_path)``; each is fitted (preserving
    aspect) into a ``cell``-sized square, captioned with its angle, and tiled into
    the smallest square-ish grid. A title bar runs across the top.
    """
    from PIL import Image, ImageDraw

    pad = 16
    cap_h = 34
    title_h = 44
    bg = (17, 19, 24)
    fg = (228, 230, 236)
    cols = 2 if len(frames) > 1 else 1
    rows = (len(frames) + cols - 1) // cols

    sheet_w = pad + cols * (cell + pad)
    sheet_h = title_h + pad + rows * (cell + cap_h + pad)
    sheet = Image.new("RGB", (sheet_w, sheet_h), bg)
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, title_h // 2), title, fill=fg, font=_load_font(26), anchor="lm")

    for i, (label, path) in enumerate(frames):
        r, c = divmod(i, cols)
        cx = pad + c * (cell + pad)
        cy = title_h + pad + r * (cell + cap_h + pad)
        try:
            img = Image.open(path).convert("RGB")
        except Exception:
            draw.rectangle([cx, cy, cx + cell, cy + cell], outline=(90, 40, 40))
            draw.text((cx + cell // 2, cy + cell // 2), "(no frame)",
                      fill=(200, 120, 120), font=_load_font(22), anchor="mm")
            continue
        img.thumbnail((cell, cell), Image.LANCZOS)
        ox = cx + (cell - img.width) // 2
        oy = cy + (cell - img.height) // 2
        sheet.paste(img, (ox, oy))
        draw.text((cx + cell // 2, cy + cell + cap_h // 2), label,
                  fill=fg, font=_load_font(24), anchor="mm")

    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("structure_id", help="structure id to render, e.g. putamen_R")
    parser.add_argument("--mode", choices=("only", "context"), default="only",
                        help="only: isolated (default); context: solid over a ghosted brain")
    parser.add_argument("--angles", default=",".join(ANGLES),
                        help=f"comma list of views (default {','.join(ANGLES)})")
    parser.add_argument("--explode", type=float, default=0.0,
                        help="blow-out amount 0..1 (default 0; pins intro off)")
    parser.add_argument("--ghost", type=float, default=0.06,
                        help="context-mode opacity for the non-target meshes (default 0.06)")
    parser.add_argument("--out", default=None,
                        help="contact sheet path (default geometry_refinements/renders/<id>/contact.png)")
    parser.add_argument("--cell", type=int, default=760, help="grid cell px (default 760)")
    parser.add_argument("--width", type=int, default=1000, help="capture viewport width")
    parser.add_argument("--height", type=int, default=1000, help="capture viewport height")
    parser.add_argument("--scale", type=float, default=2.0, help="device scale factor")
    parser.add_argument("--wait", type=int, default=4500,
                        help="ms to let the scene mesh + render per angle (default 4500)")
    parser.add_argument("--headed", action="store_true", help="real window (uses the GPU)")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is required: `pip install playwright` (or `uv run`), then "
              "`playwright install chromium` once.", file=sys.stderr)
        return 2

    angles = [a.strip() for a in args.angles.split(",") if a.strip()]
    sid = args.structure_id
    out = Path(args.out) if args.out else DEFAULT_RENDER_DIR / sid / "contact.png"
    frame_dir = out.parent

    frames: list[tuple[str, Path]] = []
    try:
        with shot.dev_server() as base:
            with sync_playwright() as playwright:
                launch_args = [] if args.headed else shot.GL_ARGS
                try:
                    browser = playwright.chromium.launch(
                        headless=not args.headed, args=launch_args)
                except Exception as exc:
                    print(f"Could not launch Chromium ({exc}). Run "
                          "`playwright install chromium` once.", file=sys.stderr)
                    return 2
                page = browser.new_page(
                    viewport={"width": args.width, "height": args.height},
                    device_scale_factor=args.scale,
                )
                for angle in angles:
                    params = _params(sid, angle, args.mode, args.explode, args.ghost)
                    frame = frame_dir / f"{angle}.png"
                    shot.capture(page, f"{base}?{params}", frame, args.wait)
                    frames.append((angle, frame))
                browser.close()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    title = f"{sid}   [{args.mode}]   explode={args.explode}"
    _compose(frames, out, title, args.cell)
    print(f"wrote {out}  ({len(frames)} angles: {', '.join(angles)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
