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

Usage (from the repo root): python tools/sourcing/apply_brand_names.py [--dry-run] [--bdpm]

``--bdpm`` instead adds the French brands corpus #16 (BDPM) reads off its product table:
a code read, gated on the product's stored page, no LLM in the loop (see ``apply_bdpm``).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
sys.path.insert(0, str(ROOT / "tools"))
import drugs_io  # noqa: E402
import worklist_io  # noqa: E402 (the one judged / worklist reader)
from data_generators.provenance import brand_regions  # noqa: E402
from text_fold import ascii_key, strip_accents  # noqa: E402

PAGES_FR = ROOT / "data_sources" / "wikipedia" / "pages_fr"
WORKLIST = ROOT / "tools" / "generated_cache" / "brand_worklist.json"
JUDGED = ROOT / "tools" / "generated_cache" / "brand_judged.json"

# Reuse the checker's normalization so "accepted here" == "passes check_data".
from lib.quote_match import normalize_for_match  # noqa: E402


BDPM_LABELS = ROOT / "tools" / "generated_cache" / "bdpm_labels.json"
BDPM_PAGES = ROOT / "data_sources" / "bdpm" / "pages"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def brand_key(name: str) -> str:
    """The duplicate key of a brand name: case-, accent- AND space/punctuation-folded.

    Not ``normalize_for_match``, which turns an accent into a word break
    ("Théralène" -> "the rale ne"), so the BDPM table's unaccented "THERALENE" would
    read as a second brand. Spaces go too: French Wikipedia writes Stahl's
    "Risperdal Consta" as "Risperdalconsta", and Stahl's "Tranxene" as "Tranxène".
    """
    return ascii_key(strip_accents(name))


def add_brand(existing: list, seen: set, name: str, region: str, source: dict) -> bool:
    """Append one brand node unless the drug already carries that name (any region,
    see ``brand_key``). Returns whether it was added."""
    key = brand_key(name)
    if not key or key in seen:
        return False
    seen.add(key)
    existing.append({"name": name, "region": region, "sources": [source]})
    return True


def merge_duplicate_brands(drugs: list[dict]) -> list[str]:
    """Fold every drug's same-``brand_key`` brands into the FIRST one, in place.

    The kept node keeps its spelling and position; it gains the later ones' sources
    (each still quoting its own page verbatim, e.g. "Risperdalconsta") and their regions
    (``region`` becomes a list when they differ, so the locale ordering each region
    earned survives). Returns ``"drug: kept <- dropped"`` lines, one per merge.
    """
    merged = []
    for d in drugs:
        kept: dict[str, dict] = {}
        out = []
        for b in d.get("brands") or []:
            first = kept.get(brand_key(b["name"]))
            if first is None:
                kept[brand_key(b["name"])] = b
                out.append(b)
                continue
            regions = brand_regions(first["region"])
            for r in brand_regions(b["region"]):
                if r not in regions:
                    regions.append(r)
            first["region"] = regions[0] if len(regions) == 1 else regions
            first["sources"] = [*(first.get("sources") or []),
                                *(s for s in b.get("sources") or []
                                  if s not in (first.get("sources") or []))]
            merged.append(f"{d['id']}: {first['name']!r} <- {b['name']!r}")
        if len(out) != len(d.get("brands") or []):
            d["brands"] = out
    return merged


def apply_bdpm(drugs: list[dict], labels: dict, pages: Path = BDPM_PAGES):
    """Add the French brands ``fetch_bdpm.py`` read off the BDPM product table.

    A code read, not a model's: the brand is the denomination's first word, already
    stripped of generics by ``lib.corpora.bdpm.brand_of``. Each is re-found on its product's
    stored header page (the denomination line), stamped ``extraction: "code"`` so no
    judge is needed, and tagged ``fr`` (every BDPM product is marketed in France).
    Returns ``(drugs touched, brands added, skipped-present, misses)``.
    """
    touched = added = present = 0
    misses = []
    for d in drugs:
        brands = (labels.get(d["id"]) or {}).get("brands") or []
        existing = d.get("brands") or []
        seen = {brand_key(b["name"]) for b in existing}
        new_here = 0
        for b in brands:
            if brand_key(b["name"]) in seen:
                present += 1
                continue
            path = pages / f"{b['cis']}.md"
            head = path.read_text(encoding="utf-8").split("\n", 1)[0] if path.exists() else ""
            if normalize_for_match(b["quote"]) not in normalize_for_match(head):
                misses.append(f"{d['id']}: {b['quote']!r} not on BDPM page {b['cis']} header")
                continue
            source = {"corpus": "bdpm", "page": b["cis"], "quote": b["quote"],
                      "provenance": "verified", "extraction": "code"}
            if add_brand(existing, seen, b["name"], "fr", source):
                new_here += 1
        if new_here:
            d["brands"] = existing
            touched += 1
            added += new_here
    return touched, added, present, misses


def report_merges(drugs: list[dict]) -> list[str]:
    """Run :func:`merge_duplicate_brands` and print what it folded (a pre-key-fix run's
    leftovers; a fresh run never adds a duplicate)."""
    merged = merge_duplicate_brands(drugs)
    for line in merged:
        print("  [merged duplicate]", line)
    return merged


def main_bdpm(dry_run: bool) -> None:
    if not BDPM_LABELS.exists() or not BDPM_PAGES.exists():
        print(f"missing {BDPM_LABELS} or {BDPM_PAGES}; run tools/fetch/fetch_bdpm.py first.")
        return
    drugs = drugs_io.load_drugs()
    touched, added, present, misses = apply_bdpm(drugs, load_json(BDPM_LABELS))
    merged = report_merges(drugs)
    print(f"applied {touched} drugs (+{added} fr brand nodes from BDPM); "
          f"skipped-present {present}, gated-out {len(misses)}")
    for line in misses:
        print("  [gated out]", line)
    if dry_run:
        print("dry-run: drugs_data.jsonl not written")
    elif added or merged:
        drugs_io.save_drugs(drugs)
        print(f"wrote {drugs_io.DRUGS_PATH}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bdpm", action="store_true",
                    help="add the French brands of corpus #16 (BDPM product table) "
                         "instead of the judged FR Wikipedia names")
    args = ap.parse_args()
    if args.bdpm:
        main_bdpm(args.dry_run)
        return

    if not JUDGED.exists() or not WORKLIST.exists():
        print(f"missing {JUDGED} or {WORKLIST}; run fetch_brand_names.py + the LLM judge first.")
        return
    if not PAGES_FR.exists():
        print(f"{PAGES_FR} absent; this is author-side, nothing to do on a clone.")
        return

    worklist = worklist_io.read(WORKLIST)
    judged = worklist_io.read(JUDGED)
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
        seen = {brand_key(b["name"]) for b in existing}
        new_here = 0
        for name in names:
            name = (name or "").strip()
            key = brand_key(name)
            if not key or key in seen:
                if key:
                    skipped_present += 1
                continue
            if normalize_for_match(name) not in page_norm:
                gated_out += 1
                misses.append(f"{did}: {name!r} not verbatim on FR page {fr_slug}")
                continue
            # First surviving name = the primary French brand; the rest, other European.
            region = "fr" if new_here == 0 else "eu"
            add_brand(existing, seen, name, region,
                      {"corpus": "wikipedia_fr", "page": fr_slug, "quote": name,
                       "provenance": "verified"})
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

    merged = report_merges(drugs)
    if args.dry_run:
        print("dry-run: drugs_data.jsonl not written")
        return
    if added or merged:
        drugs_io.save_drugs(drugs)
        print(f"wrote {drugs_io.DRUGS_PATH}")


if __name__ == "__main__":
    main()
