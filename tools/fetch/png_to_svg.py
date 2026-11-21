#!/usr/bin/env python
# /// script
# requires-python = ">=3.9"
# dependencies = ["pillow", "potracer"]
# ///
"""Vectorize a raster molecule drawing (black lines on white) into an SVG.

For a drug whose Wikipedia article draws its structure only as a PNG (tropatepine), so
``fetch_molecules.py`` (SVG-only) finds nothing. The PNG is thresholded to a bitmap and
traced with potrace (``potracer``, pure Python) into filled paths, the same kind of
outline the other molecule SVGs hold, so it scales and themes like them.

    uv run tools/fetch/png_to_svg.py --png in.png --out public/data/molecules/<id>.svg

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse

import potrace
from PIL import Image


def trace(png: str, threshold: int = 128, scale: int = 1) -> str:
    src = Image.open(png).convert("RGBA")  # a transparent background reads as white
    white = Image.new("RGBA", src.size, (255, 255, 255, 255))
    img = Image.alpha_composite(white, src).convert("L")
    if scale > 1:  # upsample first: smoother curves on a small drawing
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    w, h = img.size
    # potracer traces the dark pixels of the image it is given, i.e. the lines.
    bitmap = potrace.Bitmap(img.point(lambda p: 0 if p < threshold else 255))
    paths = bitmap.trace(turdsize=2, alphamax=1.0, opticurve=True)
    d = []
    for curve in paths:
        start = curve.start_point
        d.append(f"M{start.x:.1f},{start.y:.1f}")
        for seg in curve.segments:
            if seg.is_corner:
                d.append(f"L{seg.c.x:.1f},{seg.c.y:.1f}L{seg.end_point.x:.1f},{seg.end_point.y:.1f}")
            else:
                d.append(f"C{seg.c1.x:.1f},{seg.c1.y:.1f} {seg.c2.x:.1f},{seg.c2.y:.1f} "
                         f"{seg.end_point.x:.1f},{seg.end_point.y:.1f}")
        d.append("Z")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w // scale}" height="{h // scale}" '
            f'viewBox="0 0 {w} {h}"><path fill="#000" fill-rule="evenodd" '
            f'd="{"".join(d)}"/></svg>\n')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--png", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threshold", type=int, default=128)
    ap.add_argument("--scale", type=int, default=3)
    args = ap.parse_args()
    svg = trace(args.png, args.threshold, args.scale)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"[ok] {args.out}: {len(svg)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
