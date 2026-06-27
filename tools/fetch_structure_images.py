#!/usr/bin/env python
"""Resolve the first illustration ``.gif`` on each brain structure's Wikipedia
article and record its **URL** so the viewer can hot-link it at runtime.

Anatomy articles very often open with a rotating-brain GIF that highlights the
structure in colour (the Life Science Databases / Anatomography set), which is far
more legible than a static line drawing. Unlike the drug molecule SVGs (small, so
vendored same-origin by ``tools/fetch_molecules.py``), these animations are large
(several MB each), so they are **not** committed to the repo: the viewer embeds them
by hot-linking the Wikimedia URL directly (the site's CSP allows
``img-src https://upload.wikimedia.org``), with a spinner while it loads and a silent
hide on failure (see ``showStructure``). Only the URL lives in the data.

For every structure in ``public/data/structures.jsonl`` that has a ``wikipedia``
link, this resolves the **first** ``.gif`` used on the article (in page order, via
the ``parse`` API), keyed by the structure's **base** id so both hemispheres of a
pair share the one URL (like the WIKIPEDIA registry in ``generate_data.py``). The
resolved ``{file, url, title}`` per base is written to
``tools/structure_images_sources.json``, which the offline ``generate_data.py`` then
reads to emit each structure's ``structure_image`` (see
``_load_structure_image_urls``). A structure whose article uses no GIF is simply left
without one; the run prints which ones were missed.

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


def base_id(structure_id: str) -> str:
    """Strip a trailing ``_R`` / ``_L`` hemisphere suffix to get the base id.

    Midline structures (cerebellum, raphe, ...) have no suffix and pass through.
    """
    return re.sub(r"_(R|L)$", "", structure_id)


def first_gif(title: str) -> tuple[str, str] | None:
    """Resolve an article to its first ``.gif`` ``(file_title, url)`` in page order.

    ``action=parse&prop=images`` returns the files used on the page in order of
    appearance, so the first ``.gif`` is the lead/infobox animation on a typical
    anatomy article. Chrome (UI/maintenance) names are skipped. Returns ``None`` if
    the article uses no GIF.
    """
    data = http_json({
        "action": "parse", "page": title, "prop": "images", "redirects": 1,
    })
    images = data.get("parse", {}).get("images", [])  # filenames, page order
    for fname in images:
        if not fname.lower().endswith(".gif") or _is_chrome(fname):
            continue
        info = http_json({
            "action": "query", "titles": f"File:{fname}",
            "prop": "imageinfo", "iiprop": "url",
        })
        for page in info.get("query", {}).get("pages", {}).values():
            for ii in page.get("imageinfo", []):
                url = ii.get("url", "")
                if url.lower().endswith(".gif"):
                    return (f"File:{fname}", url)
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
            hit = first_gif(title)
            if not hit:
                missing.append((base, f"no GIF on '{title}'"))
                print(f"[{i}/{len(bases)}] {base}: MISSING (no GIF)")
                time.sleep(args.delay)
                continue
            file_title, url = hit
            sources[base] = {"file": file_title, "url": url, "title": title}
            resolved.append(base)
            print(f"[{i}/{len(bases)}] {base}: {file_title}")
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
