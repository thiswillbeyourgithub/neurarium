#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "beautifulsoup4>=4.12",
# ]
# ///
"""Fetch each drug's French Wikipedia article and build a brand-name worklist.

The North-American brands are sourced from Stahl (see apply_brand_sources.py). The
European / French brands are NOT in a structured field: the FR Wikipedia *infobox*
carries only chemistry, so the trade names live in the article *prose*, e.g.

    "La quétiapine, commercialisée sous les noms Xeroquel, Seroquel, Sequase,
     Ketipinor est un antipsychotique..."
    "Doliprane, Efferalgan, Dafalgan, Tylenol... sont des marques commerciales
     du paracétamol."

So this pass is the fetch + candidate-extraction half of an LLM-extract / quote-gate
/ judge pipeline (corpus #9's FR sibling, `wikipedia_fr`). For every drug that has a
Wikipedia URL it:

* resolves the FR article via the EN article's langlinks (the accented FR title,
  e.g. Fluoxétine, is not guessable), skipping a drug with no FR article;
* fetches the FR article and stores it (raw_fr/<slug>.html + pages_fr/<slug>.md) as
  the quote-gate page, exactly like corpus #9's EN store;
* deterministically pulls the candidate trade-name *sentences* (the lead paragraph
  plus every sentence naming a commercial name) into a worklist.

The worklist (``tools/generated_cache/brand_worklist.json``) then goes to an LLM that
reads only those short sentences and returns each drug's ordered trade-name list; the
applier (apply_brand_names.py) quote-gates every returned name verbatim on the stored
FR page (the hallucination backstop) before writing it. EN is used ONLY for the
langlink here: the EN pages are NOT re-fetched or overwritten, so no existing Ki
quote-gate (corpus #9) can drift.

Region tags order brands per locale (fr -> eu -> na in French, na -> eu -> fr in
English) and are never shown. The FR prose lists a drug's brands roughly by
prominence, so the applier takes the first non-na name as ``fr`` (the primary French
brand) and the rest as ``eu``.

Author-side (network + the gitignored data_sources/wikipedia tree). Stdlib + bs4.

Usage (from the repo root):
    uv run tools/fetch/fetch_brand_names.py                 # all drugs
    uv run tools/fetch/fetch_brand_names.py --only fluoxetine paroxetine
    uv run tools/fetch/fetch_brand_names.py --limit 5       # first 5 (smoke test)
    uv run tools/fetch/fetch_brand_names.py --no-fetch      # rebuild worklist from stored pages
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse

from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)                       # sibling fetch_wikipedia_pharmacology.py
sys.path.insert(0, os.path.join(REPO, "tools"))  # drugs_io
import fetch_wikipedia_pharmacology as wp  # noqa: E402  (reuse fetch_page/store_page/etc.)
import drugs_io  # noqa: E402

DATA_DIR = wp.DATA_DIR                                    # data_sources/wikipedia
PAGES_FR = os.path.join(DATA_DIR, "pages_fr")
RAW_FR = os.path.join(DATA_DIR, "raw_fr")
WORKLIST = os.path.join(REPO, "tools", "generated_cache", "brand_worklist.json")

# A sentence that states one or more commercial names. Deliberately broad on the
# recall side (the applier's quote gate + the LLM judge trim false positives).
CUE_RE = re.compile(
    r"commercialis|sous (?:le|les) noms?|marque[s]? commerciale|"
    r"nom[s]? de marque|vendu[e]?s? sous|conditionn|dénomination commerciale",
    re.IGNORECASE)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ«])")
MAX_SENTENCES = 8


def en_title_from_url(url):
    """'https://en.wikipedia.org/wiki/Fluoxetine' -> 'Fluoxetine' (unquoted)."""
    if not url or "/wiki/" not in url:
        return None
    return urllib.parse.unquote(url.rsplit("/wiki/", 1)[1]).replace("_", " ")


def fr_title_of(en_page):
    """The French article title from an EN page's langlinks, else None."""
    for ll in en_page.get("langlinks", []):
        if ll.get("lang") == "fr":
            return ll.get("title")
    return None


def candidate_sentences(page_text):
    """The lead paragraph + every commercial-name sentence, from the FR page text.

    page_text is render_page_text output (headings '#...', list items '- ...', plain
    paragraphs). Brands sit in prose, so scan paragraph lines only; keep the first
    (the lead, where brands are often parenthetical) plus any sentence hitting CUE_RE.
    """
    out = []
    seen = set()
    lead_taken = False
    for line in page_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-") or "|" in line:
            continue  # heading, list item, or a flattened table row
        for sent in SENT_SPLIT.split(line):
            sent = sent.strip()
            if len(sent) < 12 or len(sent) > 400:
                continue
            take = CUE_RE.search(sent) or (not lead_taken)
            lead_taken = True
            if take and sent not in seen:
                seen.add(sent)
                out.append(sent)
            if len(out) >= MAX_SENTENCES:
                return out
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="restrict to these drug ids")
    ap.add_argument("--limit", type=int, help="only the first N drugs (smoke test)")
    ap.add_argument("--no-fetch", action="store_true",
                    help="rebuild the worklist from already-stored FR pages (no network)")
    ap.add_argument("--sleep", type=float, default=0.4, help="polite delay between fetches")
    args = ap.parse_args()

    drugs = drugs_io.load_drugs()
    if args.only:
        want = set(args.only)
        drugs = [d for d in drugs if d["id"] in want]
    if args.limit:
        drugs = drugs[: args.limit]

    os.makedirs(PAGES_FR, exist_ok=True)
    os.makedirs(RAW_FR, exist_ok=True)
    os.makedirs(os.path.dirname(WORKLIST), exist_ok=True)

    worklist = {}
    no_fr = []
    for i, d in enumerate(drugs, 1):
        en_title = en_title_from_url(d.get("wikipedia"))
        if not en_title:
            no_fr.append(f"{d['id']}: no EN wikipedia url")
            continue
        fr_slug = None
        fr_title = None
        try:
            if args.no_fetch:
                # Rebuild from a prior full run: that run's worklist names the FR slug,
                # so re-read the already-stored FR page (no network).
                prev = _prev_worklist().get(d["id"])
                if not prev:
                    continue
                fr_title, fr_slug = prev["fr_title"], prev["fr_slug"]
                page_text = open(os.path.join(PAGES_FR, f"{fr_slug}.md"), encoding="utf-8").read()
            else:
                en_page = wp.fetch_page(en_title, "en")
                fr_title = fr_title_of(en_page)
                if not fr_title:
                    no_fr.append(f"{d['id']}: no FR article ({en_title})")
                    time.sleep(args.sleep)
                    continue
                fr_page = wp.fetch_page(fr_title, "fr")
                page_text = wp.render_page_text(BeautifulSoup(fr_page["html"], "html.parser"))
                wp.store_page(fr_page, page_text, pages_dir=PAGES_FR, raw_dir=RAW_FR)
                fr_slug = wp.slugify(fr_page["title"])
                time.sleep(args.sleep)
        except Exception as e:  # noqa: BLE001  (best-effort author-side fetch)
            no_fr.append(f"{d['id']}: fetch error {e!r}")
            continue

        sents = candidate_sentences(page_text)
        worklist[d["id"]] = {
            "name": d["name"],
            "fr_title": fr_title,
            "fr_slug": fr_slug,
            "sentences": sents,
        }
        print(f"[{i}/{len(drugs)}] {d['id']:<22} FR={fr_title!r:<28} sentences={len(sents)}")

    with open(WORKLIST, "w", encoding="utf-8") as f:
        json.dump(worklist, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"\nwrote {os.path.relpath(WORKLIST, REPO)} ({len(worklist)} drugs)")
    if no_fr:
        print(f"{len(no_fr)} skipped:")
        for line in no_fr[:40]:
            print("  ", line)


def _prev_worklist():
    if os.path.exists(WORKLIST):
        with open(WORKLIST, encoding="utf-8") as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    main()
