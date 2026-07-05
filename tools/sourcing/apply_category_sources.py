#!/usr/bin/env python
"""Apply drug-class (category) source quotes to ``tools/data/drugs_data.jsonl``.

A drug's **class classification** ("this drug is an SSRI / TCA / atypical
antipsychotic / ...") is its own graded node (kind ``drug_categories``), one per
drug, defaulting to ``llm``. Stahl's Prescriber's Guide states each drug's class
verbatim in the bullet(s) under its "## Class" heading (e.g. "Tricyclic
antidepressant (TCA)", "Atypical antipsychotic (...)", "Benzodiazepine
(hypnotic)"). This tool sources that node against those verbatim lines.

Unlike ``apply_nbn_sources.py`` (a pure verbatim-substring gate on a single fixed
field), mapping Stahl's free-text class line onto our coarse ``categories``
taxonomy needs a judgement step, so the accepted quotes come from an
extract-then-judge pass (Haiku extracts each drug's verbatim Class-section
descriptor line; Sonnet judges whether it supports our category IDs and picks the
line(s) to cite; a genuine contradiction is flagged, not sourced). That pass'
output is a results file ``[{id, quotes:[...]}]``; this tool then, for each drug:

* re-searches the drug's Stahl page range (from ``data_sources/books/stahl/INDEX.md``)
  for each accepted (normalized) quote, so the *page is found locally* rather than
  trusted from the agent;
* only when a quote is genuinely present does it write
  ``{corpus: stahl, page, quote, provenance: verified}`` onto ``category_sources``.

This is the local twin of ``check_data.py``'s source-quote gate (which then
re-confirms every stored quote is on its cited page). A quote the agent
paraphrased or mislocated simply fails to match and is skipped, so nothing
untrustworthy is written. Idempotent: a drug already carrying ``category_sources``
is left untouched. Stdlib only; authoring helper, not served.

Usage:
    python tools/sourcing/apply_category_sources.py RESULTS.json [--dry-run]

Built with the help of Claude Code.
"""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent   # repo root (script in tools/sourcing/)
sys.path.insert(0, str(ROOT / "tools"))                # reach the shared drugs_io module
import drugs_io  # noqa: E402
DRUGS_JSON = drugs_io.DRUGS_PATH
PAGES = ROOT / "data_sources" / "books" / "stahl" / "pages"
INDEX = ROOT / "data_sources" / "books" / "stahl" / "INDEX.md"

# Reuse the exact normalization the checker uses, so "accepted here" == "passes
# check_data" by construction (no second, drifting implementation).
_spec = importlib.util.spec_from_file_location("cd", ROOT / "tools" / "check_data.py")
_cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cd)
normalize_for_match = _cd.normalize_for_match

_ROW = re.compile(r"^\|\s*\d+\s*\|\s*(.+?)\s*\|\s*\[(\d+)-(\d+)\]")


def _norm(name):
    """Lowercase + alphanumerics only (matches build_source_worklist._norm), so a
    drug name reconciles with its INDEX heading despite punctuation differences."""
    return "".join(c for c in name.lower() if c.isalnum())


def page_ranges():
    out = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if m:
            out[_norm(m.group(1))] = (int(m.group(2)), int(m.group(3)))
    return out


def find_page(start, end, quote):
    """Return the page in [start, end] whose text contains the normalized quote,
    or None. Searches the whole range so the located page is authoritative."""
    needle = normalize_for_match(quote)
    if not needle:
        return None
    for p in range(start, end + 1):
        f = PAGES / f"{p}.md"
        if not f.exists():
            continue
        if needle in normalize_for_match(f.read_text(encoding="utf-8")):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", help="JSON: [{id, quotes:[...]}]")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    drugs = drugs_io.load_drugs()
    by_id = {d["id"]: d for d in drugs}
    ranges = page_ranges()

    applied = skipped = no_range = 0
    misses = []
    for r in results:
        did = r["id"]
        d = by_id.get(did)
        if d is None:
            misses.append(f"{did}: no such drug in drugs_data.jsonl")
            continue
        if d.get("category_sources"):
            skipped += 1
            continue
        rng = ranges.get(_norm(d["name"]))
        if not rng:
            no_range += 1
            misses.append(f"{did}: no page range in INDEX.md")
            continue
        sources = []
        for quote in r.get("quotes", []):
            page = find_page(rng[0], rng[1], quote)
            if page is None:
                misses.append(f"{did}: quote not found in pp.{rng[0]}-{rng[1]}: {quote!r}")
                continue
            sources.append({"corpus": "stahl", "page": page,
                            "quote": quote, "provenance": "verified"})
        if sources:
            d["category_sources"] = sources
            applied += 1

    print(f"applied {applied}, skipped {skipped} (already sourced), "
          f"no-range {no_range}, misses {len(misses)}")
    for line in misses[:60]:
        print(f"  [miss] {line}")
    if len(misses) > 60:
        print(f"  ... and {len(misses) - 60} more")

    if args.dry_run:
        print("dry-run: drugs_data.jsonl not written")
        return
    if applied:
        drugs_io.save_drugs(drugs)
        print(f"wrote {DRUGS_JSON}")


if __name__ == "__main__":
    main()
