#!/usr/bin/env python
"""Resolve the best illustration on each brain structure's Wikipedia article and
record its **URL** so the viewer can hot-link it at runtime.

Anatomy articles very often open with a rotating-brain GIF that highlights the
structure in colour (the Life Science Databases / Anatomography set), which is far
more legible than a static line drawing. Unlike the drug molecule SVGs (small, so
vendored same-origin by ``tools/fetch_molecules.py``), these animations are large
(several MB each), so they are **not** committed to the repo: the viewer embeds them
by hot-linking the Wikimedia URL directly (the site's CSP allows
``img-src https://upload.wikimedia.org``), with a spinner while it loads and a silent
hide on failure (see ``showStructure``). Only the URL lives in the data.

For every structure in ``public/data/structures.jsonl`` that has a ``wikipedia``
link, this resolves the best illustration via a **fallback chain** (so a structure
whose article carries no animation still gets a useful picture):

  1. the **first ``.gif``** used on the article (in page order, via the ``parse``
     API) -- the lead rotating-brain / coronal-sections animation;
  2. else the **first ``.svg``** (a vector diagram, often a labelled section);
  3. else the **infobox / lead image** of any type (gif/svg/png/jpg, via the
     ``pageimages`` API) -- the photo or plate at the top of the article.

The hit is keyed by the structure's **base** id so both hemispheres of a pair share
the one URL (like the WIKIPEDIA registry in ``generate_data.py``). The resolved
``{file, url, title, kind}`` per base (``kind`` = gif/svg/infobox, for provenance) is
written to ``tools/structure_images_sources.json``, which the offline
``generate_data.py`` then reads to emit each structure's ``structure_image`` (see
``_load_structure_image_urls``). A structure whose article has no usable image at all
is left without one; the run prints which ones were missed.

This is an *authoring* tool (it hits the network), kept separate from the offline,
stdlib-only ``generate_data.py``. It reuses the polite-fetch helpers from the sibling
``fetch_molecules.py`` (shared User-Agent, retry/backoff, the MediaWiki JSON call and
the article-title / chrome-name helpers) rather than duplicating them. It is
idempotent (skips bases already recorded unless ``--force``) and polite (descriptive
User-Agent + a small delay between requests). It downloads **no image bytes**, only
the JSON metadata needed to resolve each URL.

Usage::

    python tools/fetch_structure_images.py                 # resolve all missing
    python tools/fetch_structure_images.py --force          # re-resolve everything
    python tools/fetch_structure_images.py --only hippocampus,amygdala
    python tools/fetch_structure_images.py --limit 5        # first 5 (a smoke test)

Needs network access (Wikipedia API).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

# Reuse the polite-fetch plumbing from the molecule fetcher instead of copying it
# (same Wikimedia endpoint, User-Agent, retry/backoff and helpers). Both scripts
# live in tools/, so a plain import resolves when run as `python tools/<name>.py`.
from fetch_molecules import _is_chrome, article_title, http_json

REPO = Path(__file__).resolve().parent.parent
STRUCTURES_JSONL = REPO / "public" / "data" / "structures.jsonl"
SOURCES_JSON = Path(__file__).resolve().parent / "structure_images_sources.json"

# Extensions an <img> can actually render. The pageimages "page image" is sometimes
# a non-image file (e.g. a microscopy figure exported as a .pdf), which would load
# as a broken image, so the infobox fallback only accepts these.
RENDERABLE_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def base_id(structure_id: str) -> str:
    """Strip a trailing ``_R`` / ``_L`` hemisphere suffix to get the base id.

    Midline structures (cerebellum, raphe, ...) have no suffix and pass through.
    """
    return re.sub(r"_(R|L)$", "", structure_id)


def _file_url(file_title: str) -> str | None:
    """Resolve a ``File:<name>`` title to its full-resolution Wikimedia url."""
    info = http_json({
        "action": "query", "titles": file_title,
        "prop": "imageinfo", "iiprop": "url",
    })
    for page in info.get("query", {}).get("pages", {}).values():
        for ii in page.get("imageinfo", []):
            url = ii.get("url", "")
            if url:
                return url
    return None


def _lead_image(title: str) -> tuple[str, str] | None:
    """The article's infobox / lead image (any type) via the ``pageimages`` API.

    ``piprop=original`` gives the full-resolution source of the page's primary
    image, which on an anatomy article is the photo / plate / diagram at the top of
    the infobox. ``redirects=1`` follows a title redirect; chrome names are skipped.
    """
    data = http_json({
        "action": "query", "prop": "pageimages",
        "piprop": "original|name", "titles": title, "redirects": 1,
    })
    for page in data.get("query", {}).get("pages", {}).values():
        name = page.get("pageimage") or ""
        src = (page.get("original") or {}).get("source") or ""
        if src and not _is_chrome(name) \
                and src.lower().endswith(RENDERABLE_IMG_EXT):
            return (f"File:{name}", src)
    return None


def resolve_image(title: str) -> tuple[str, str, str] | None:
    """Best illustration for an article: ``(file_title, url, kind)`` or ``None``.

    Fallback chain (see the module docstring): first ``.gif`` in page order, else
    first ``.svg`` in page order, else the infobox/lead image of any type.
    ``action=parse&prop=images`` lists the files in order of appearance, so "first"
    is the lead one on a typical article. Chrome (UI/maintenance) names are skipped.
    """
    data = http_json({
        "action": "parse", "page": title, "prop": "images", "redirects": 1,
    })
    images = data.get("parse", {}).get("images", [])  # filenames, page order
    for ext, kind in ((".gif", "gif"), (".svg", "svg")):
        for fname in images:
            if not fname.lower().endswith(ext) or _is_chrome(fname):
                continue
            url = _file_url(f"File:{fname}")
            if url and url.lower().endswith(ext):
                return (f"File:{fname}", url, kind)
    lead = _lead_image(title)
    if lead:
        return (lead[0], lead[1], "infobox")
    return None


def load_structure_bases() -> list[tuple[str, str]]:
    """``(base_id, wikipedia_url)`` pairs, one per base, in first-seen order.

    The emitted structures.jsonl carries per-hemisphere records that share an
    article; collapsing to the base id avoids resolving the same GIF twice.
    """
    if not STRUCTURES_JSONL.exists():
        sys.exit(f"missing {STRUCTURES_JSONL}; run tools/generate_data.py first")
    seen: dict[str, str] = {}
    for line in STRUCTURES_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        wiki = rec.get("wikipedia")
        if not wiki:
            continue
        seen.setdefault(base_id(rec["id"]), wiki)
    return list(seen.items())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                    help="re-resolve even if the base is already recorded")
    ap.add_argument("--only", default="",
                    help="comma-separated structure base ids (default: all)")
    ap.add_argument("--limit", type=int, default=0,
                    help="only process the first N bases (smoke test)")
    ap.add_argument("--delay", type=float, default=0.2,
                    help="seconds to sleep between bases (politeness)")
    args = ap.parse_args()

    sources: dict[str, dict] = {}
    if SOURCES_JSON.exists():
        sources = json.loads(SOURCES_JSON.read_text(encoding="utf-8"))

    bases = load_structure_bases()
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    if only:
        bases = [b for b in bases if b[0] in only]
    if args.limit:
        bases = bases[:args.limit]

    resolved, skipped, missing, errors = [], [], [], []
    for i, (base, wiki) in enumerate(bases, 1):
        if base in sources and not args.force:
            skipped.append(base)
            continue
        title = article_title(wiki)
        if not title:
            missing.append((base, "no wikipedia title"))
            continue
        try:
            hit = resolve_image(title)
            if not hit:
                # Clear any stale entry (e.g. a --force re-resolve that now rejects
                # what it once accepted) so the sources JSON never keeps a dead url.
                sources.pop(base, None)
                missing.append((base, f"no image on '{title}'"))
                print(f"[{i}/{len(bases)}] {base}: MISSING (no image)")
                time.sleep(args.delay)
                continue
            file_title, url, kind = hit
            sources[base] = {"file": file_title, "url": url,
                             "title": title, "kind": kind}
            resolved.append(base)
            print(f"[{i}/{len(bases)}] {base}: [{kind}] {file_title}")
        except Exception as exc:  # noqa: BLE001 - report and keep going
            errors.append((base, str(exc)))
            print(f"[{i}/{len(bases)}] {base}: ERROR {exc}")
        time.sleep(args.delay)

    # Persist the resolved urls + provenance (sorted for a stable diff). This file
    # is read by generate_data.py to emit each structure's structure_image url.
    SOURCES_JSON.write_text(
        json.dumps(dict(sorted(sources.items())), ensure_ascii=False, indent=2)
        + "\n", encoding="utf-8")

    print("\n=== summary ===")
    print(f"resolved : {len(resolved)}")
    print(f"skipped  : {len(skipped)} (already recorded)")
    print(f"missing  : {len(missing)}")
    for base, why in missing:
        print(f"           - {base}: {why}")
    if errors:
        print(f"errors   : {len(errors)}")
        for base, why in errors:
            print(f"           - {base}: {why}")
    print(f"\nresolved urls -> {SOURCES_JSON}")


if __name__ == "__main__":
    main()
