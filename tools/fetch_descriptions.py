#!/usr/bin/env python
"""Replace each drug's description with the lead section of its Wikipedia article.

The authored descriptions are LLM-synthesized mechanism one-liners (provenance
"llm"). This tool swaps them for the **lead summary** of the drug's Wikipedia
article, used verbatim (CC BY-SA), so the text is attributable to a real source and
graded "sourced". For every drug in ``tools/drugs_data.json`` with a ``wikipedia``
link it:

* resolves the English article title from the link and fetches its lead summary
  via the MediaWiki REST ``page/summary`` endpoint (the concise lead "card", not
  the full intro section);
* finds the French article via ``langlinks`` and fetches its lead summary too;
* only when **both** languages resolve to a non-empty lead does it replace the
  drug's ``description`` ``{en, fr}`` and set ``description_provenance: "sourced"``
  (so the provenance stays truthful per drug, not mixed across languages);
* records the per-language source (article title, URL, revision id, timestamp) in
  ``tools/descriptions_sources.json`` for attribution + reproducibility.

A drug whose French article is missing (or whose lead is empty / a disambiguation)
keeps its existing description at the "llm" grade; the run prints which were
skipped. This is an *authoring* tool (it hits the network), kept separate from the
offline, stdlib-only ``generate_data.py``. Stdlib only (urllib), idempotent (skips
drugs already graded "sourced" unless ``--force``) and polite (descriptive
User-Agent + a small delay between requests + 429 backoff).

Usage::

    python tools/fetch_descriptions.py                 # fetch all not-yet-sourced
    python tools/fetch_descriptions.py --force          # re-fetch everything
    python tools/fetch_descriptions.py --only citalopram,fluoxetine
    python tools/fetch_descriptions.py --limit 5        # first 5 (a smoke test)
    python tools/fetch_descriptions.py --dry-run        # report, write nothing

Needs network access (en.wikipedia.org + fr.wikipedia.org). CC BY-SA attribution
for the fetched text is carried by the panel's Wikipedia reference link and the
About note; this tool records the precise revisions in the sidecar.

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DRUGS_JSON = REPO / "tools" / "drugs_data.json"
SOURCES_JSON = Path(__file__).resolve().parent / "descriptions_sources.json"

# A descriptive User-Agent is required by the Wikimedia API policy; it should carry
# a contact. No personal address is hard-coded (privacy): set
# WIKIPEDIA_FETCH_CONTACT to a real e-mail/URL before a large run, else a TODO
# placeholder is sent.
CONTACT = os.environ.get("WIKIPEDIA_FETCH_CONTACT", "TODO-set-WIKIPEDIA_FETCH_CONTACT")
UA = (f"neurarium-description-fetch/1.0 (educational 3D brain visualizer; "
      f"contact {CONTACT})")

DELAY = 0.4  # polite pause between drugs


def _open_with_retry(req: urllib.request.Request, timeout: int) -> bytes | None:
    """Open a request, retrying on 429/503 with backoff (respecting Retry-After).
    Returns None on a 404 (article/langlink missing) so the caller can skip."""
    backoff = 5.0
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code not in (429, 503) or attempt == 5:
                raise
            retry_after = exc.headers.get("Retry-After")
            wait = float(retry_after) if (retry_after or "").isdigit() else backoff
            print(f"    {exc.code}; backing off {wait:.0f}s (attempt {attempt + 1}/5)")
            time.sleep(wait)
            backoff = min(backoff * 2, 120)
    raise RuntimeError("unreachable")


def _get_json(url: str, timeout: int = 30) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = _open_with_retry(req, timeout)
    return json.loads(raw) if raw is not None else None


def article_title(wiki_url: str) -> str | None:
    """Extract the article title from an ``.../wiki/<Title>`` URL (URL-decoded)."""
    m = re.search(r"/wiki/([^?#]+)", wiki_url or "")
    if not m:
        return None
    return urllib.parse.unquote(m.group(1)).replace("_", " ")


def fr_title(en_title: str) -> str | None:
    """The French article title for an English one, via langlinks (or None)."""
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "langlinks",
        "lllang": "fr", "redirects": "1", "titles": en_title,
    })
    data = _get_json(f"https://en.wikipedia.org/w/api.php?{q}")
    if not data:
        return None
    for page in data.get("query", {}).get("pages", {}).values():
        for ll in page.get("langlinks", []) or []:
            if ll.get("lang") == "fr":
                return ll.get("*")
    return None


def lead_summary(lang: str, title: str) -> dict | None:
    """Fetch a Wikipedia lead summary via the REST ``page/summary`` endpoint.

    Returns ``{extract, title, url, revision, timestamp}`` or None when the article
    is missing, a disambiguation page, or has no lead text."""
    path = urllib.parse.quote(title.replace(" ", "_"), safe="")
    data = _get_json(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{path}",
                     timeout=30)
    if not data:
        return None
    if data.get("type") == "disambiguation":
        return None
    extract = (data.get("extract") or "").strip()
    if not extract:
        return None
    url = ((data.get("content_urls") or {}).get("desktop") or {}).get("page", "")
    return {
        "extract": extract,
        "title": data.get("title") or title,
        "url": url,
        "revision": data.get("revision"),
        "timestamp": data.get("timestamp"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="re-fetch even drugs already graded 'sourced'")
    ap.add_argument("--only", default="", help="comma-separated drug ids")
    ap.add_argument("--limit", type=int, default=0, help="first N candidates only")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    drugs = json.loads(DRUGS_JSON.read_text(encoding="utf-8"))
    sources = {}
    if SOURCES_JSON.exists():
        sources = json.loads(SOURCES_JSON.read_text(encoding="utf-8"))

    if CONTACT.startswith("TODO"):
        print("note: set WIKIPEDIA_FETCH_CONTACT to a real contact for a big run\n")

    candidates = [d for d in drugs if d.get("wikipedia")
                  and (not only or d["id"] in only)
                  and (args.force or d.get("description_provenance") != "sourced")]
    if args.limit:
        candidates = candidates[:args.limit]
    print(f"{len(candidates)} candidate drug(s)")

    applied = 0
    skips = []
    for d in candidates:
        did = d["id"]
        en_t = article_title(d["wikipedia"])
        if not en_t:
            skips.append(f"{did}: cannot parse title from {d['wikipedia']!r}")
            continue
        en = lead_summary("en", en_t)
        if not en:
            skips.append(f"{did}: no English lead for {en_t!r}")
            time.sleep(DELAY)
            continue
        fr_t = fr_title(en_t)
        fr = lead_summary("fr", fr_t) if fr_t else None
        if not fr:
            skips.append(f"{did}: no French article/lead (en ok)")
            time.sleep(DELAY)
            continue
        d["description"] = {"en": en["extract"], "fr": fr["extract"]}
        d["description_provenance"] = "sourced"
        sources[did] = {
            "en": {k: en[k] for k in ("title", "url", "revision", "timestamp")},
            "fr": {k: fr[k] for k in ("title", "url", "revision", "timestamp")},
        }
        applied += 1
        print(f"  [ok] {did}: en {len(en['extract'])}c / fr {len(fr['extract'])}c")
        time.sleep(DELAY)

    print(f"\napplied {applied}, skipped {len(skips)}")
    for line in skips[:80]:
        print(f"  [skip] {line}")
    if len(skips) > 80:
        print(f"  ... and {len(skips) - 80} more")

    if args.dry_run:
        print("dry-run: nothing written")
        return
    if applied:
        DRUGS_JSON.write_text(
            json.dumps(drugs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        SOURCES_JSON.write_text(
            json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {DRUGS_JSON} and {SOURCES_JSON}")


if __name__ == "__main__":
    main()
