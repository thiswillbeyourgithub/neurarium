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

Beyond that single hero it also gathers a **gallery** (``gather_gallery``): every
*other* gif/svg used on the base's **English and French** articles (deduped, hero +
chrome excluded, capped at ``MAX_GALLERY``), so the structure panel can offer a "show
more" of the region's labelled diagrams / extra animations.

The hit is keyed by the structure's **base** id so both hemispheres of a pair share
the one record (like the WIKIPEDIA registry in ``generate_data.py``). Each base's
``{file, url, title, kind, gallery:[{file,url,kind,lang}]}`` is written to
``tools/structure_images_sources.json``, which the offline ``generate_data.py`` then
reads to emit each structure's ``structure_image`` (hero) + ``structure_image_gallery``
(see ``_load_structure_images``). A structure whose article has no usable image at all
is left without one; the run prints which ones were missed.

The **same** resolver also runs over the **circuits** (``public/data/circuits.jsonl``,
those with a ``wikipedia`` link): each circuit's hero + gallery is resolved exactly
like a structure and written, keyed by circuit id, to ``tools/circuit_images_sources.json``
(its own file so the two key namespaces never mix), read by ``generate_data.py``'s
``_load_circuit_images`` to emit the circuit panel's ``structure_image`` /
``structure_image_gallery``. ``--target structures|circuits|all`` (default ``all``)
picks which pass to run.

This is an *authoring* tool (it hits the network), kept separate from the offline,
stdlib-only ``generate_data.py``. It reuses the polite-fetch helpers from the sibling
``fetch_molecules.py`` (shared User-Agent, retry/backoff, the MediaWiki JSON call and
the article-title / chrome-name helpers) rather than duplicating them. It is
idempotent (skips items already recorded unless ``--force``) and polite (descriptive
User-Agent + a small delay between requests). It downloads **no image bytes**, only
the JSON metadata needed to resolve each URL.

Usage::

    python tools/fetch_structure_images.py                 # structures + circuits, missing
    python tools/fetch_structure_images.py --force          # re-resolve everything
    python tools/fetch_structure_images.py --only hippocampus,amygdala
    python tools/fetch_structure_images.py --target circuits # only the circuit heroes
    python tools/fetch_structure_images.py --limit 5        # first 5 per target (smoke test)

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
from fetch_molecules import API as EN_API, _is_chrome, article_title, http_json

REPO = Path(__file__).resolve().parent.parent
STRUCTURES_JSONL = REPO / "public" / "data" / "structures.jsonl"
CIRCUITS_JSONL = REPO / "public" / "data" / "circuits.jsonl"
SOURCES_JSON = Path(__file__).resolve().parent / "structure_images_sources.json"
# Circuits get their own sources file (same schema), keyed by circuit id, so the two
# concerns never share a key namespace. Read by generate_data.py's _load_circuit_images.
CIRCUIT_SOURCES_JSON = Path(__file__).resolve().parent / "circuit_images_sources.json"

# The French Wikipedia MediaWiki endpoint (the gallery also scans the FR article,
# which often carries labelled diagrams the EN one does not). Same /w/api.php shape.
FR_API = "https://fr.wikipedia.org/w/api.php"

# The gallery collects only the renderable, illustration-grade vector/animation
# files (gif + svg); the hero already covers the infobox/lead photo case.
GALLERY_EXT = (".gif", ".svg")

# Article chrome/licence/UI icons that ride along on ``prop=images`` but are never
# illustrations. The molecule fetcher's ``_is_chrome`` (tuned for molecule pages)
# misses many that appear on anatomy articles: featured-article stars, edit pencils,
# journal / open-access / licence logos, info / sound / portal icons, decorative
# clip-art. These extra lowercase substrings filter them out of the gallery.
GALLERY_CHROME = (
    "cscr", "featured", "good_article", "journal", "open_access", "openaccess",
    "blue_pencil", "info_simple", "info-simple", "creative-tail", "halloween",
    "pencil", "barnstar", "spoken", "loudspeaker", "_logo", "logo_", "logo.",
    "_icon", "icon_", "icon.", "_button", "padlock", "pd-icon", "licen",
    "public_domain", "cc-by", "by-sa", "by_sa", "rss", "feed-icon", "crystal_clear",
    "nuvola", "translation", "merge", "wiktionary", "wikisource", "wikidata",
)


def _is_gallery_chrome(name: str) -> bool:
    """True for a file that is Wikipedia/Commons chrome, not an illustration
    (the molecule fetcher's ``_is_chrome`` plus the anatomy-article extras above)."""
    if _is_chrome(name):
        return True
    low = name.lower()
    return any(tok in low for tok in GALLERY_CHROME)

# Cap the per-structure gallery so a busy article (and the API calls to resolve it)
# stays bounded; the hero plus this many extras is plenty for the panel.
MAX_GALLERY = 10

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


def _file_url(file_title: str, api_url: str = EN_API) -> str | None:
    """Resolve a ``File:<name>`` title to its full-resolution Wikimedia url.

    Commons files resolve via any wiki; ``api_url`` lets a wiki-local file (rare,
    e.g. an image only on fr.wikipedia) resolve against that wiki.
    """
    info = http_json({
        "action": "query", "titles": file_title,
        "prop": "imageinfo", "iiprop": "url",
    }, api_url)
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
        if not src or _is_gallery_chrome(name):
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
            # Reject article chrome with the *stronger* gallery filter (licence /
            # logo / featured-star icons, e.g. PD-icon.svg, that the molecule-tuned
            # _is_chrome misses), so the hero is a real illustration, not a UI badge.
            if not fname.lower().endswith(ext) or _is_gallery_chrome(fname):
                continue
            url = _file_url(f"File:{fname}")
            if url and url.lower().endswith(ext):
                return (f"File:{fname}", url, kind)
    lead = _lead_image(title)
    if lead:
        return (lead[0], lead[1], "infobox")
    return None


def _article_image_files(title: str, api_url: str) -> list[str]:
    """File names used on an article, in page order (``parse&prop=images``)."""
    data = http_json({
        "action": "parse", "page": title, "prop": "images", "redirects": 1,
    }, api_url)
    return data.get("parse", {}).get("images", [])


def _fr_title(en_title: str) -> str | None:
    """The French article title for an English one via ``langlinks``, or None."""
    data = http_json({
        "action": "query", "prop": "langlinks", "titles": en_title,
        "lllang": "fr", "redirects": 1,
    })
    for page in data.get("query", {}).get("pages", {}).values():
        for ll in page.get("langlinks", []):
            fr = ll.get("*")
            if fr:
                return fr
    return None


def _norm_title(file_title: str) -> str:
    """Normalize a ``File:`` title for matching (the API returns spaces; the image
    list gives underscores)."""
    return file_title.lower().replace("_", " ")


def _file_urls(file_titles: list[str], api_url: str = EN_API) -> dict[str, str]:
    """Resolve many ``File:`` titles to urls in one ``imageinfo`` query (<=50 per
    call, so a whole gallery costs ~1 request, not one per image). Returns a map
    keyed by normalized title (see ``_norm_title``)."""
    out: dict[str, str] = {}
    for i in range(0, len(file_titles), 50):
        chunk = file_titles[i:i + 50]
        info = http_json({
            "action": "query", "titles": "|".join(chunk),
            "prop": "imageinfo", "iiprop": "url",
        }, api_url)
        for page in info.get("query", {}).get("pages", {}).values():
            title = page.get("title", "")
            for ii in page.get("imageinfo", []):
                url = ii.get("url", "")
                if url:
                    out[_norm_title(title)] = url
    return out


def gather_gallery(en_title: str, hero_file: str | None) -> list[dict]:
    """Every distinct gif/svg illustration on the EN + FR articles, hero excluded.

    Scans both articles' file lists (page order), skips chrome + the hero file, and
    batch-resolves the rest to Wikimedia urls, returning ``[{file,url,kind,lang}]``
    capped at ``MAX_GALLERY``. Used to build the structure panel's "show more" gallery
    (the hero stays the single resolved lead image). Best-effort: a failure on the FR
    side just yields fewer images.
    """
    out: list[dict] = []
    seen: set[str] = set()
    if hero_file:
        seen.add(_norm_title(hero_file))

    plan = [("en", en_title, EN_API)]
    try:
        fr = _fr_title(en_title)
    except Exception:  # noqa: BLE001 - FR is a bonus; never fail the base over it
        fr = None
    if fr:
        plan.append(("fr", fr, FR_API))

    for lang, title, api in plan:
        names: list[str] = []  # candidate File: titles, in page order, deduped
        for fname in _article_image_files(title, api):
            low = fname.lower()
            if not low.endswith(GALLERY_EXT) or _is_gallery_chrome(fname):
                continue
            ft = f"File:{fname}"
            nk = _norm_title(ft)
            if nk in seen:
                continue
            seen.add(nk)
            names.append(ft)
        urls = _file_urls(names, api) if names else {}
        for ft in names:
            url = urls.get(_norm_title(ft))
            if not url or not url.lower().endswith(GALLERY_EXT):
                continue
            kind = "gif" if ft.lower().endswith(".gif") else "svg"
            out.append({"file": ft, "url": url, "kind": kind, "lang": lang})
            if len(out) >= MAX_GALLERY:
                return out
    return out


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


def load_circuit_bases() -> list[tuple[str, str]]:
    """``(circuit_id, wikipedia_url)`` pairs, one per circuit that has a wikipedia
    link. Same shape as :func:`load_structure_bases` so the resolution loop is shared;
    a circuit id has no hemisphere suffix, so it is used verbatim as the key."""
    if not CIRCUITS_JSONL.exists():
        return []
    out: list[tuple[str, str]] = []
    for line in CIRCUITS_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        wiki = rec.get("wikipedia")
        if wiki:
            out.append((rec["id"], wiki))
    return out


def resolve_list(items: list[tuple[str, str]], sources: dict[str, dict],
                 overrides: dict[str, str], args) -> None:
    """Resolve the hero + gallery for each ``(key, wiki)`` in ``items`` into
    ``sources`` (mutated in place). Shared by the structure and circuit passes: the
    only per-pass difference is the input list, the sources dict and the override map
    (circuits have none), so the loop below never diverges between the two."""

    def add_gallery(entry: dict, wiki: str) -> None:
        """Populate ``entry['gallery']`` from the item's EN + FR articles (hero
        excluded). Best-effort: always leaves a list (empty on any failure)."""
        title = article_title(wiki)
        if not title:
            entry.setdefault("gallery", [])
            return
        try:
            entry["gallery"] = gather_gallery(title, entry.get("file"))
            if entry["gallery"]:
                print(f"        + gallery: {len(entry['gallery'])} image(s)")
        except Exception as exc:  # noqa: BLE001 - the hero already stands on its own
            entry.setdefault("gallery", [])
            print(f"        gallery error: {exc}")

    resolved, skipped, missing, errors = [], [], [], []
    for i, (base, wiki) in enumerate(items, 1):
        # A manual override wins over the auto-resolver and the recorded value, and
        # the hero needs no network, so it is applied first and even without --force
        # (so adding an override and re-running fixes a wrong pick immediately). The
        # gallery still comes from the article: reuse an already-gathered one unless
        # --force, else fetch it.
        if base in overrides:
            entry = _override_entry(overrides[base])
            prev = sources.get(base) or {}
            if "gallery" in prev and not args.force:
                entry["gallery"] = prev["gallery"]
            else:
                add_gallery(entry, wiki)
                time.sleep(args.delay)
            if prev == entry:
                skipped.append(base)
            else:
                sources[base] = entry
                resolved.append(base)
                print(f"[{i}/{len(items)}] {base}: [override] {entry['file']}")
            continue
        if base in sources and not args.force:
            # Already have the hero; backfill the gallery if this entry predates it.
            if "gallery" not in sources[base]:
                add_gallery(sources[base], wiki)
                time.sleep(args.delay)
                resolved.append(base)
            else:
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
                print(f"[{i}/{len(items)}] {base}: MISSING (no image)")
                time.sleep(args.delay)
                continue
            file_title, url, kind = hit
            entry = {"file": file_title, "url": url, "title": title, "kind": kind}
            print(f"[{i}/{len(items)}] {base}: [{kind}] {file_title}")
            add_gallery(entry, wiki)
            sources[base] = entry
            resolved.append(base)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            errors.append((base, str(exc)))
            print(f"[{i}/{len(items)}] {base}: ERROR {exc}")
        time.sleep(args.delay)

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


def _persist(sources: dict[str, dict], path: Path) -> None:
    """Write the resolved urls sorted (stable diff). Read by generate_data.py."""
    path.write_text(
        json.dumps(dict(sorted(sources.items())), ensure_ascii=False, indent=2)
        + "\n", encoding="utf-8")
    print(f"resolved urls -> {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                    help="re-resolve even if the base is already recorded")
    ap.add_argument("--only", default="",
                    help="comma-separated structure base / circuit ids (default: all)")
    ap.add_argument("--limit", type=int, default=0,
                    help="only process the first N items per target (smoke test)")
    ap.add_argument("--delay", type=float, default=0.2,
                    help="seconds to sleep between items (politeness)")
    ap.add_argument("--target", choices=("structures", "circuits", "all"),
                    default="all",
                    help="which node kind's images to resolve (default: all)")
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()}

    def filtered(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
        if only:
            items = [b for b in items if b[0] in only]
        return items[:args.limit] if args.limit else items

    if args.target in ("structures", "all"):
        sources: dict[str, dict] = {}
        if SOURCES_JSON.exists():
            sources = json.loads(SOURCES_JSON.read_text(encoding="utf-8"))
        print("--- structures ---")
        resolve_list(filtered(load_structure_bases()), sources, IMAGE_OVERRIDES, args)
        _persist(sources, SOURCES_JSON)

    if args.target in ("circuits", "all"):
        csources: dict[str, dict] = {}
        if CIRCUIT_SOURCES_JSON.exists():
            csources = json.loads(CIRCUIT_SOURCES_JSON.read_text(encoding="utf-8"))
        print("\n--- circuits ---")
        # Circuits carry no manual overrides (empty map); everything else is identical.
        resolve_list(filtered(load_circuit_bases()), csources, {}, args)
        _persist(csources, CIRCUIT_SOURCES_JSON)


if __name__ == "__main__":
    main()
