#!/usr/bin/env python
"""Apply the LLM-extracted French / European drug brand names (region eu/fr).

The North-American brands come from Stahl (apply_brand_sources.py). This is the
second half of the FR brand pipeline started by tools/fetch/fetch_brand_names.py:
that pass fetched each drug's FR Wikipedia article, stored it as the quote-gate page
(``data_sources/wikipedia/pages_fr/<slug>.md``), and wrote a worklist of candidate
trade-name sentences; an LLM then read those sentences and wrote each drug's ordered
trade-name list to ``brand_judged.json``. This applier, for each judged drug:

* drops any name that duplicates a brand the drug already carries (na from Stahl, or a
  prior eu/fr run) under check_data's normalization, so nothing is double-counted;
* **quote-gates** every remaining name: it must appear verbatim on the stored FR page
  (the same normalization check_data re-runs), so a hallucinated name is dropped here;
* assigns regions from the FR prose order: the first surviving name is the primary
  French brand (``fr``), the rest are other European ones (``eu``);
* writes ``{name, region, sources: [{corpus: wikipedia_fr, page: <fr_slug>,
  quote: <name>, provenance: verified}]}`` onto the drug's ``brands`` list.

Region only orders brands per locale (fr -> eu -> na in French, na -> eu -> fr in
English); it is never shown. Idempotent: a name already present (any region) is
skipped, so a re-run adds nothing. Stdlib only; author-side (needs the gitignored
data_sources/wikipedia/pages_fr tree the fetch pass wrote).

Usage (from the repo root): python tools/sourcing/apply_brand_names.py [--dry-run]
"""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
sys.path.insert(0, str(ROOT / "tools"))
import drugs_io  # noqa: E402

PAGES_FR = ROOT / "data_sources" / "wikipedia" / "pages_fr"
WORKLIST = ROOT / "tools" / "generated_cache" / "brand_worklist.json"
JUDGED = ROOT / "tools" / "generated_cache" / "brand_judged.json"

# Reuse the checker's normalization so "accepted here" == "passes check_data".
_spec = importlib.util.spec_from_file_location("cd", ROOT / "tools" / "check_data.py")
_cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cd)
normalize_for_match = _cd.normalize_for_match


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not JUDGED.exists() or not WORKLIST.exists():
        print(f"missing {JUDGED} or {WORKLIST}; run fetch_brand_names.py + the LLM judge first.")
        return
    if not PAGES_FR.exists():
        print(f"{PAGES_FR} absent; this is author-side, nothing to do on a clone.")
        return

    worklist = load_json(WORKLIST)
    judged = load_json(JUDGED)
    drugs = drugs_io.load_drugs()
    by_id = {d["id"]: d for d in drugs}

    applied = added = skipped_present = gated_out = no_page = 0
    misses = []
    page_cache = {}
    for did, names in judged.items():
        d = by_id.get(did)
        wl = worklist.get(did)
        if not d or not wl or not names:
            continue
        fr_slug = wl["fr_slug"]
        page_path = PAGES_FR / f"{fr_slug}.md"
        if not page_path.exists():
            no_page += 1
            continue
        if fr_slug not in page_cache:
            page_cache[fr_slug] = normalize_for_match(page_path.read_text(encoding="utf-8"))
        page_norm = page_cache[fr_slug]

        existing = d.setdefault("brands", [])
        seen = {normalize_for_match(b["name"]) for b in existing}
        new_here = 0
        for name in names:
            name = (name or "").strip()
            key = normalize_for_match(name)
            if not key or key in seen:
                if key:
                    skipped_present += 1
                continue
            if key not in page_norm:
                gated_out += 1
                misses.append(f"{did}: {name!r} not verbatim on FR page {fr_slug}")
                continue
            seen.add(key)
            # First surviving name = the primary French brand; the rest, other European.
            region = "fr" if new_here == 0 else "eu"
            existing.append({
                "name": name,
                "region": region,
                "sources": [{
                    "corpus": "wikipedia_fr",
                    "page": fr_slug,
                    "quote": name,
                    "provenance": "verified",
                }],
            })
            new_here += 1
            added += 1
        if new_here:
            applied += 1

    print(f"applied {applied} drugs (+{added} eu/fr brand nodes); "
          f"skipped-present {skipped_present}, gated-out {gated_out}, no-page {no_page}")
    for line in misses[:40]:
        print("  [gated out]", line)
    if len(misses) > 40:
        print(f"  ... and {len(misses) - 40} more")

    if args.dry_run:
        print("dry-run: drugs_data.jsonl not written")
        return
    if added:
        drugs_io.save_drugs(drugs)
        print(f"wrote {drugs_io.DRUGS_PATH}")


if __name__ == "__main__":
    main()
