#!/usr/bin/env python
"""Download each drug's molecular-structure SVG from Wikipedia into
``public/data/molecules/<id>.svg`` so the viewer can embed it same-origin (the
site's CSP is ``img-src 'self'``; hot-linking Wikimedia is blocked, so the assets
are vendored like three.js / eruda).

For every drug in ``public/data/drugs.jsonl`` that has a ``wikipedia`` link, the
article's lead infobox image is resolved via the MediaWiki ``pageimages`` API
(which, for a chemical article, is the skeletal-formula image). Only ``.svg`` lead
images are kept; if the lead image is not an SVG, the page's image list is scanned
for a structure-looking SVG as a fallback. A drug with no resolvable SVG is simply
left without one (the panel renders nothing for it, see ``_drug_record`` /
``showDrug``); the run prints which ones were missed.

This is an *authoring* tool (it hits the network), kept separate from the offline,
stdlib-only ``generate_data.py``. It is stdlib-only too (urllib), idempotent (skips
files already present unless ``--force``) and polite (descriptive User-Agent + a
small delay between requests). Provenance (the Commons file + source URL per drug)
is written to ``tools/generated_cache/molecules_sources.json`` for attribution.

Usage::

    python tools/fetch/fetch_molecules.py                 # fetch all missing
    python tools/fetch/fetch_molecules.py --force          # re-fetch everything
    python tools/fetch/fetch_molecules.py --only citalopram,fluoxetine
    python tools/fetch/fetch_molecules.py --limit 5        # first 5 (a smoke test)

Needs network access (Wikipedia + upload.wikimedia.org).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent   # tools/ (script lives in tools/fetch/)
REPO = TOOLS.parent
DRUGS_JSONL = REPO / "public" / "data" / "drugs.jsonl"
OUT_DIR = REPO / "public" / "data" / "molecules"
SOURCES_JSON = TOOLS / "generated_cache" / "molecules_sources.json"
API = "https://en.wikipedia.org/w/api.php"

# A descriptive User-Agent is required by the Wikimedia API policy; it should carry
# a contact. No personal address is hard-coded (privacy): set MOLECULE_FETCH_CONTACT
# to a real e-mail/URL before a large run, otherwise a TODO placeholder is sent.
CONTACT = os.environ.get("MOLECULE_FETCH_CONTACT", "TODO-set-MOLECULE_FETCH_CONTACT")
UA = (f"neurarium-molecule-fetch/1.0 (educational 3D brain visualizer; "
      f"contact {CONTACT})")

# Filenames that are MediaWiki/Commons chrome (logos, UI icons, maintenance
# badges), never a molecule, so the fallback image scan skips them.
CHROME_SVG = (
    "commons-logo", "oojs", "who rod", "who_rod", "yes check", "yes_check",
    "wikidata", "ambox", "gnome", "edit-", "padlock", "lock-", "question",
    "red x", "x_mark", "speaker", "sound", "disambig", "wiktionary",
    "wikisource", "wikiquote", "wikibooks", "portal", "symbol_", "emblem",
    "flag_", "increase", "decrease", "steady", "magnify", "wiki letter",
)
# Drugs whose article lead image is not the skeletal formula we want (a 3D
# ball-and-stick render, a photograph), mapped to the Commons file to take
# instead. Checked before the pageimages lookup.
FILE_OVERRIDES = {
    # The Ethanol article leads with a 1.5 MB ball-and-stick render; the flat
    # formula next to it is 1 KB and matches every other molecule in the panel.
    "ethanol": "File:Ethanol-2D-flat.svg",
    # Same story: the Domperidone lead is a 3D ball-and-stick PNG.
    "domperidone": "File:Domperidone 2D structure.svg",
}
# Tokens that mark a structure SVG, used to rank fallback candidates.
STRUCTURE_HINTS = (
    "structure", "skeletal", "chemical", "2d", "racemic", "acs", "_200",
    "molecule", "displayed", "formula", "ball-and-stick", "_structural",
)


def _open_with_retry(req: urllib.request.Request, timeout: int) -> bytes:
    """Open a request, retrying on 429/503 with backoff (respecting Retry-After).

    Wikimedia throttles bursts with HTTP 429; backing off and retrying (rather
    than failing the drug) lets a long run ride through a rate-limit window.
    """
    backoff = 5.0
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == 5:
                raise
            retry_after = exc.headers.get("Retry-After")
            wait = float(retry_after) if (retry_after or "").isdigit() else backoff
            print(f"    {exc.code}; backing off {wait:.0f}s "
                  f"(attempt {attempt + 1}/5)")
            time.sleep(wait)
            backoff = min(backoff * 2, 120)
    raise RuntimeError("unreachable")


def http_json(params: dict, api_url: str = API) -> dict:
    """GET a MediaWiki API with our User-Agent and return the parsed JSON.

    Defaults to the English Wikipedia endpoint; pass ``api_url`` (e.g. the French
    Wikipedia ``w/api.php``) to query another wiki without duplicating the polite
    retry/backoff plumbing.
    """
    query = urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(f"{api_url}?{query}", headers={"User-Agent": UA})
    return json.loads(_open_with_retry(req, timeout=30))


def http_bytes(url: str) -> bytes:
    """Download a binary resource (the SVG) with our User-Agent."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return _open_with_retry(req, timeout=60)


def article_title(wiki_url: str) -> str | None:
    """Extract the article title from an ``.../wiki/<Title>`` URL (URL-decoded)."""
    m = re.search(r"/wiki/([^?#]+)", wiki_url or "")
    if not m:
        return None
    return urllib.parse.unquote(m.group(1)).replace("_", " ")


def _is_chrome(name: str) -> bool:
    low = name.lower()
    return any(tok in low for tok in CHROME_SVG)


def _is_svg_url(url: str) -> bool:
    """True if the URL's *path* names an ``.svg``.

    The MediaWiki API started appending ``?utm_source=...`` tracking params to
    ``imageinfo``/``pageimages`` URLs, so a bare ``url.endswith(".svg")`` broke.
    """
    return urllib.parse.urlparse(url).path.lower().endswith(".svg")


def resolve_file(file_title: str) -> tuple[str, str] | None:
    """Resolve a Commons ``File:x.svg`` title to ``(file_title, url)``."""
    info = http_json({
        "action": "query", "prop": "imageinfo", "iiprop": "url",
        "titles": file_title,
    })
    for page in info.get("query", {}).get("pages", {}).values():
        for ii in page.get("imageinfo", []):
            url = ii.get("url", "")
            if _is_svg_url(url):
                return (file_title, url)
    return None


def resolve_svg(title: str) -> tuple[str, str] | None:
    """Resolve a Wikipedia article to its structure SVG ``(file_title, url)``.

    Primary: the ``pageimages`` lead/infobox image (the skeletal formula on a
    chemical article). Fallback: scan the page's images for a structure-looking
    ``.svg``, preferring filenames with a structure hint or a token of the drug
    name. Returns ``None`` if nothing SVG-ish is found.
    """
    # Primary: the lead image. piprop=original gives the full-resolution source
    # URL, name gives its File: title. redirects=1 follows a title redirect (many
    # drug articles live under a different spelling, e.g. Benztropine ->
    # Benzatropine, Flupenthixol -> Flupentixol) so its infobox image is found.
    data = http_json({
        "action": "query", "prop": "pageimages",
        "piprop": "original|name", "titles": title, "redirects": 1,
    })
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        name = page.get("pageimage") or ""
        src = (page.get("original") or {}).get("source") or ""
        if name.lower().endswith(".svg") and _is_svg_url(src) \
                and not _is_chrome(name):
            return (f"File:{name}", src)

    # Fallback: list every image on the page and pick a structure-looking SVG.
    data = http_json({
        "action": "query", "prop": "images", "imlimit": "500",
        "titles": title, "redirects": 1,
    })
    name_tokens = [t for t in re.split(r"\W+", title.lower()) if len(t) > 3]
    candidates: list[str] = []
    for page in data.get("query", {}).get("pages", {}).values():
        for img in page.get("images", []):
            ititle = img.get("title", "")  # e.g. "File:Citalopram racemic.svg"
            fname = ititle.split(":", 1)[-1]
            if not fname.lower().endswith(".svg") or _is_chrome(fname):
                continue
            candidates.append(ititle)
    if not candidates:
        return None

    def score(ititle: str) -> int:
        low = ititle.lower()
        s = 0
        if any(h in low for h in STRUCTURE_HINTS):
            s += 2
        if any(tok in low for tok in name_tokens):
            s += 3
        return s

    best = max(candidates, key=score)
    info = http_json({
        "action": "query", "prop": "imageinfo", "iiprop": "url", "titles": best,
    })
    for page in info.get("query", {}).get("pages", {}).values():
        for ii in page.get("imageinfo", []):
            url = ii.get("url", "")
            if _is_svg_url(url):
                return (best, url)
    return None


def _ensure_svg_size(text: str) -> str:
    """Give the ``<svg>`` an intrinsic ``width``/``height`` if it only has a viewBox.

    Many Commons structure SVGs declare a ``viewBox`` but no ``width``/``height``,
    so an ``<img>`` referencing them has no intrinsic size and collapses to 0x0
    under a ``max-width``/``max-height`` bound (Chromium reports ``naturalWidth``
    0). Deriving width/height from the viewBox extents gives every file a concrete
    intrinsic size, so the panel's CSS bounds them uniformly. Files that already
    declare both dimensions are left untouched.
    """
    m = re.search(r"<svg\b[^>]*>", text, re.IGNORECASE)
    if not m:
        return text
    tag = m.group(0)
    if re.search(r'\bwidth\s*=', tag) and re.search(r'\bheight\s*=', tag):
        return text
    vb = re.search(r'viewBox\s*=\s*["\']\s*[-\d.]+[ ,]+[-\d.]+[ ,]+'
                   r'([\d.]+)[ ,]+([\d.]+)', tag, re.IGNORECASE)
    if not vb:
        return text
    w, h = vb.group(1), vb.group(2)
    new_tag = tag[:-1] + f' width="{w}" height="{h}">'
    return text[:m.start()] + new_tag + text[m.end():]


def _strip_background(text: str) -> str:
    """Drop an opaque ``background-color`` from the root ``<svg>`` style.

    Some renderers bake an opaque white canvas into the SVG
    (``style="background-color: #ffffffff"``). The panel inverts the art for the
    dark theme, which would turn that white canvas into a solid black box framing
    the molecule, inconsistent with the (majority) transparent-background files.
    Removing the declaration leaves a transparent canvas, so every molecule reads
    as bare light strokes on the panel. (A transparent ``#ffffff00`` is harmless
    but stripped too for uniformity.)
    """
    return re.sub(r"\s*background-color\s*:\s*#?[0-9a-fA-F]{3,8}\s*;?", "",
                  text, flags=re.IGNORECASE)


# Ceiling for a committed molecule SVG. A skeletal structural formula is a few KB
# (the median here is ~6 KB); a file an order of magnitude past that is the article's
# 3D model, which is both the wrong illustration for the panel and a large asset to
# ship to a phone. Generous enough to keep the genuinely intricate formulas.
MAX_SVG_BYTES = 200_000


def sanitize_svg(raw: bytes) -> bytes:
    """Clean a fetched SVG: strip scripts + opaque background, ensure intrinsic size.

    Embedding via ``<img>`` already neuters scripts (browsers load img-referenced
    SVGs in a non-scripted, no-external-fetch mode), but removing them keeps the
    committed asset clean regardless of how it is later used. ``_strip_background``
    drops a baked-in white canvas (so the inverted art has no black box), and
    ``_ensure_svg_size`` guarantees width/height so the panel can size it reliably.
    All three passes are idempotent, so re-sanitizing a file is safe.
    """
    text = raw.decode("utf-8", "replace")
    text = re.sub(r"<script\b[^>]*>.*?</script\s*>", "", text,
                  flags=re.IGNORECASE | re.DOTALL)
    text = _strip_background(text)
    text = _ensure_svg_size(text)
    return text.encode("utf-8")


def load_drugs() -> list[dict]:
    if not DRUGS_JSONL.exists():
        sys.exit(f"missing {DRUGS_JSONL}; run tools/generate_data.py first")
    return [json.loads(line) for line in DRUGS_JSONL.read_text(
        encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                    help="re-download even if the SVG already exists")
    ap.add_argument("--only", default="",
                    help="comma-separated drug ids to fetch (default: all)")
    ap.add_argument("--limit", type=int, default=0,
                    help="only process the first N drugs (smoke test)")
    ap.add_argument("--delay", type=float, default=0.2,
                    help="seconds to sleep between drugs (politeness)")
    ap.add_argument("--allow-huge", action="store_true",
                    help=f"keep an SVG larger than {MAX_SVG_BYTES} bytes (by default "
                         "such a file is refused: it is a 3D render, not a formula)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sources: dict[str, dict] = {}
    if SOURCES_JSON.exists():
        sources = json.loads(SOURCES_JSON.read_text(encoding="utf-8"))

    drugs = load_drugs()
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    if only:
        drugs = [d for d in drugs if d["id"] in only]
    if args.limit:
        drugs = drugs[:args.limit]

    fetched, skipped, missing, errors, oversized = [], [], [], [], []
    for i, drug in enumerate(drugs, 1):
        did = drug["id"]
        out = OUT_DIR / f"{did}.svg"
        if out.exists() and not args.force:
            skipped.append(did)
            continue
        title = article_title(drug.get("wikipedia", ""))
        if not title:
            missing.append((did, "no wikipedia title"))
            continue
        try:
            override = FILE_OVERRIDES.get(did)
            resolved = resolve_file(override) if override else resolve_svg(title)
            if not resolved:
                missing.append((did, f"no SVG on '{title}'"))
                print(f"[{i}/{len(drugs)}] {did}: MISSING (no SVG)")
                time.sleep(args.delay)
                continue
            file_title, url = resolved
            svg = sanitize_svg(http_bytes(url))
            if len(svg) > MAX_SVG_BYTES and not args.allow_huge:
                # A skeletal formula is a few KB. Anything this size is the article's
                # 3D ball-and-stick or space-filling render, which resolves as the
                # lead image on some molecules (ethanol's is 1.5 MB, 250x the median
                # and bigger than the whole rest of the directory put together). It
                # is the wrong picture AND a heavy one, so it is refused rather than
                # committed; --allow-huge takes it anyway.
                oversized.append((did, len(svg), file_title))
                print(f"[{i}/{len(drugs)}] {did}: REFUSED {file_title} "
                      f"({len(svg)} bytes > {MAX_SVG_BYTES} limit)")
                time.sleep(args.delay)
                continue
            out.write_bytes(svg)
            sources[did] = {"file": file_title, "url": url, "title": title}
            fetched.append(did)
            print(f"[{i}/{len(drugs)}] {did}: {file_title} "
                  f"({out.stat().st_size} bytes)")
        except Exception as exc:  # noqa: BLE001 - report and keep going
            errors.append((did, str(exc)))
            print(f"[{i}/{len(drugs)}] {did}: ERROR {exc}")
        time.sleep(args.delay)

    # Persist provenance (sorted for a stable diff).
    SOURCES_JSON.write_text(
        json.dumps(dict(sorted(sources.items())), ensure_ascii=False, indent=2)
        + "\n", encoding="utf-8")

    print("\n=== summary ===")
    print(f"fetched : {len(fetched)}")
    print(f"skipped : {len(skipped)} (already present)")
    print(f"missing : {len(missing)}")
    for did, why in missing:
        print(f"          - {did}: {why}")
    if oversized:
        print(f"refused : {len(oversized)} (over {MAX_SVG_BYTES} bytes)")
        for did, size, file_title in oversized:
            print(f"          - {did}: {file_title} ({size} bytes)")
    if errors:
        print(f"errors  : {len(errors)}")
        for did, why in errors:
            print(f"          - {did}: {why}")
    print(f"\nprovenance -> {SOURCES_JSON}")


if __name__ == "__main__":
    main()
