#!/usr/bin/env python
"""Source a drug's commercial brand names (region ``na``) from Stahl.

Like the NbN line, a drug's brand names are a structured Stahl field, not a
free-prose claim: each monograph opens with a "Brands" section listing the drug's
trade names (e.g. Alprazolam -> Xanax, Xanax XR), and the same names appear
verbatim on the drug's first page. So this needs no extraction agent and no LLM
judge. For each drug that has no ``brands`` yet, it:

* reads the drug's brand list from the Stahl Q/A dump's "Brands?" answer
  (``data_sources/books/stahl/stahl_dump.jsonl``), preserving Stahl's order (the
  first brand is the most prominent, i.e. the most iconic North-American one);
* for each brand, searches the drug's Stahl page range (from ``INDEX.md``) for the
  page that states it and captures the brand **verbatim** as the page quote;
* confirms that quote is present on the page under the exact normalization
  ``check_data.py`` uses (a programmatic claim-support check, strictly stronger
  than an LLM judge for a proper-noun field);
* writes ``{name, region: "na", sources: [{corpus: stahl, page, quote,
  provenance: verified}]}`` onto the drug's ``brands`` list.

Region is always ``na`` here: Stahl is a US book, so its brands are the North
American ones. The European / French brands come from Wikipedia via a separate
pass (see the eu/fr enrichment). The ``region`` tag only orders brands per locale
(fr -> eu -> na in French, na -> eu -> fr in English); it is never shown.

A brand that the dump lists but that does not appear verbatim on any page in the
range (an OCR artifact) is reported as a miss and NOT written, so every emitted
``na`` brand is quote-verified (its local twin: check_data.py's source-quote gate
re-confirms the stored quote on the page). Idempotent: a drug already carrying
``brands`` is left untouched. Stdlib only; author-side (needs the gitignored Stahl
tree).

Usage (from the repo root): python tools/sourcing/apply_brand_sources.py [--dry-run]
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
STAHL = ROOT / "data_sources" / "books" / "stahl"
PAGES = STAHL / "pages"
INDEX = STAHL / "INDEX.md"
DUMP = STAHL / "stahl_dump.jsonl"

# Reuse the exact normalization the checker uses, so "accepted here" == "passes
# check_data" (no second, drifting implementation).
_spec = importlib.util.spec_from_file_location("cd", ROOT / "tools" / "check_data.py")
_cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cd)
normalize_for_match = _cd.normalize_for_match

_ROW = re.compile(r"^\|\s*\d+\s*\|\s*(.+?)\s*\|\s*\[(\d+)-(\d+)\]")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def _norm(name):
    """Lowercase alphanumerics only (matches apply_nbn_sources._norm)."""
    return "".join(c for c in name.lower() if c.isalnum())


def page_ranges():
    """Map _norm(drug name) -> (start_page, end_page) from INDEX.md."""
    out = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if m:
            out[_norm(m.group(1))] = (int(m.group(2)), int(m.group(3)))
    return out


def parse_brands(answer):
    """Split a Stahl 'Brands?' answer into an ordered brand-name list.

    The answer is a ``<br/>``-delimited list of bulleted names, e.g.
    ``<b>•</b><b> </b>Xanax<br/>• Xanax XR<br/>``; strip the HTML tags and bullets,
    collapse whitespace, drop empties. Order is preserved (Stahl lists the most
    prominent brand first).
    """
    brands = []
    for part in _BR.split(answer or ""):
        part = _TAG.sub("", part).replace("•", " ")
        part = re.sub(r"\s+", " ", part).strip()
        if part:
            brands.append(part)
    return brands


def load_dump_brands():
    """Stream the Stahl dump -> {_norm(drug name): [brand, ...]} from 'Brands?' Q/A."""
    out = {}
    with DUMP.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if (rec.get("Question", "") or "").strip().lower() != "brands?":
                continue
            names = parse_brands(rec.get("Answer", ""))
            if names:
                out[_norm(rec.get("Drug", ""))] = names
    return out


def find_brand_page(brand, start, end):
    """First page in [start, end] whose text states `brand` verbatim, else None.

    Verbatim under check_data's normalization (case- and punctuation-insensitive),
    so the stored quote provably appears on the cited page.
    """
    needle = normalize_for_match(brand)
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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not DUMP.exists() or not INDEX.exists():
        print(f"Stahl material not present ({DUMP} / {INDEX}); this is an author-side "
              "script, nothing to do on a clone without the gitignored book tree.")
        return

    drugs = drugs_io.load_drugs()
    ranges = page_ranges()
    dump = load_dump_brands()

    applied = brands_added = skipped = no_dump = no_range = 0
    misses = []
    for d in drugs:
        if d.get("brands"):
            skipped += 1
            continue
        names = dump.get(_norm(d["name"]))
        if not names:
            no_dump += 1
            continue
        rng = ranges.get(_norm(d["name"]))
        if not rng:
            no_range += 1
            misses.append(f"{d['id']}: brands listed but no page range")
            continue
        brands = []
        for name in names:
            page = find_brand_page(name, rng[0], rng[1])
            if page is None:
                misses.append(f"{d['id']}: brand {name!r} not verbatim in pp.{rng[0]}-{rng[1]}")
                continue
            brands.append({
                "name": name,
                "region": "na",
                "sources": [{
                    "corpus": "stahl",
                    "page": page,
                    "quote": name,
                    "provenance": "verified",
                }],
            })
        if brands:
            d["brands"] = brands
            applied += 1
            brands_added += len(brands)

    print(f"applied {applied} drugs ({brands_added} brand nodes), "
          f"skipped {skipped} (already have brands), no-dump-entry {no_dump}, "
          f"no-range {no_range}")
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
