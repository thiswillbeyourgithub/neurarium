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

# Extensions an <img> can actually render directly. The pageimages "page image" is
# sometimes a non-image file (e.g. a microscopy figure uploaded as a .pdf), so the
# infobox fallback only embeds these as-is.
RENDERABLE_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")

# Document formats Wikimedia renders page-by-page to JPG: an <img> can't show the
# original .pdf/.djvu/.tif but CAN show its rendered first-page thumbnail (e.g.
# .../<file>.pdf/page1-330px-<file>.pdf.jpg), so a document lead is salvaged that way
# instead of being dropped. The width below is the rendered thumbnail's pixel width.
THUMBNAILABLE_DOC_EXT = (".pdf", ".djvu", ".tif", ".tiff")
DOC_THUMB_WIDTH = 330

# Manual per-base image overrides: when the auto-resolver's fallback chain picks the
# wrong illustration (a generic animation that does not single out this structure, an
# unhelpful diagram), pin the exact Wikimedia file URL here. An override wins over the
# chain and survives ``--force``, so the choice is durable and re-running the fetcher
# never reverts it. Keyed by structure base id, like the rest of this file.
IMAGE_OVERRIDES = {
    # The chain picked a generic spinning-brain GIF that does not highlight the
    # occipital lobe; pin the dedicated occipital-lobe animation instead.
    "occipital": (
        "https://upload.wikimedia.org/wikipedia/commons/8/8f/"
        "Occipital_lobe_animation_small.gif"
    ),
    # A clearer hypothalamus animation than the chain's pick.
    "hypothalamus": (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/0/05/"
        "Hypothalamus.gif/330px-Hypothalamus.gif"
    ),
}


def _override_entry(url: str) -> dict:
    """A sources-JSON entry for a manual override URL: derive the File: name + kind.

    The ``kind`` (gif/svg/infobox, provenance only) comes from the URL extension; the
    ``title`` marks it as hand-pinned so the provenance is honest. A Wikimedia *thumb*
    URL (``.../thumb/a/ab/<File>/<width>px-<File>``) carries the real file name as the
    path segment *before* the rendered thumbnail, so use that, not the trailing
    ``330px-...`` rendition name.
    """
    parts = url.rstrip("/").split("/")
    name = parts[-2] if "/thumb/" in url and len(parts) >= 2 else parts[-1]
    low = name.lower()
    kind = "gif" if low.endswith(".gif") else "svg" if low.endswith(".svg") else "infobox"
    return {"file": f"File:{name}", "url": url, "title": "(manual override)", "kind": kind}


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


def _doc_thumb(file_title: str, width: int = DOC_THUMB_WIDTH) -> str | None:
    """Rendered JPG thumbnail of a multi-page document file (PDF / DjVu / TIFF).

    Wikimedia renders such a file's first page to a thumbnail an ``<img>`` can show
    (the original cannot be embedded). ``imageinfo`` with ``iiurlwidth`` returns that
    rendered ``thumburl`` (e.g. ``.../<file>.pdf/page1-330px-<file>.pdf.jpg``).
    """
    info = http_json({
        "action": "query", "titles": file_title,
        "prop": "imageinfo", "iiprop": "url", "iiurlwidth": width,
    })
    for page in info.get("query", {}).get("pages", {}).values():
        for ii in page.get("imageinfo", []):
            thumb = ii.get("thumburl", "")
            if thumb:
                return thumb
    return None


def _lead_image(title: str) -> tuple[str, str] | None:
    """The article's infobox / lead image via the ``pageimages`` API.

    ``piprop=original`` gives the full-resolution source of the page's primary
    image, which on an anatomy article is the photo / plate / diagram at the top of
    the infobox. ``redirects=1`` follows a title redirect; chrome names are skipped.
    A directly renderable image is embedded as-is; a document lead (PDF / DjVu /
    TIFF) is salvaged via its rendered first-page thumbnail (see ``_doc_thumb``).
    """
    data = http_json({
        "action": "query", "prop": "pageimages",
        "piprop": "original|name", "titles": title, "redirects": 1,
    })
    for page in data.get("query", {}).get("pages", {}).values():
        name = page.get("pageimage") or ""
        src = (page.get("original") or {}).get("source") or ""
        if not src or _is_chrome(name):
            continue
        low = src.lower()
        if low.endswith(RENDERABLE_IMG_EXT):
            return (f"File:{name}", src)
        if low.endswith(THUMBNAILABLE_DOC_EXT):
            thumb = _doc_thumb(f"File:{name}")
            if thumb:
                return (f"File:{name}", thumb)
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
        # A manual override wins over the auto-resolver and the recorded value, and
        # needs no network, so it is applied first and even without --force (so adding
        # an override and re-running fixes a wrong pick immediately).
        if base in IMAGE_OVERRIDES:
            entry = _override_entry(IMAGE_OVERRIDES[base])
            if sources.get(base) == entry:
                skipped.append(base)
            else:
                sources[base] = entry
                resolved.append(base)
                print(f"[{i}/{len(bases)}] {base}: [override] {entry['file']}")
            continue
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
