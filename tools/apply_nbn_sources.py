#!/usr/bin/env python
"""Source each drug's NbN (Neuroscience-based Nomenclature) line from Stahl.

Unlike a binding's free-prose claim, the NbN is a structured field: Stahl prints a
verbatim ``Neuroscience-based Nomenclature: <value>`` line on each drug's first
page. So this needs no extraction agent and no LLM judge. For every drug that has
an ``nbn`` but no ``nbn_sources`` yet, it:

* searches the drug's Stahl page range (from ``stahl/INDEX.md``) for that line;
* captures the line **verbatim** from the page as the quote;
* confirms the dataset's own ``nbn`` value is a substring of that line (after the
  same normalization ``check_data.py`` uses), so the quote provably states *this
  drug's* NbN, a programmatic claim-support check that is strictly stronger than an
  LLM judge for this field;
* writes ``{corpus: stahl, page, quote, provenance: verified}`` onto ``nbn_sources``.

This is the local twin of ``check_data.py``'s source-quote gate (which then
re-confirms the stored quote is on the page). Idempotent: a drug already carrying
``nbn_sources`` is left untouched. Stdlib only; authoring helper, not served.

Usage:
    python tools/apply_nbn_sources.py [--dry-run]

Built with the help of Claude Code.
"""
import argparse
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRUGS_JSON = ROOT / "tools" / "drugs_data.json"
PAGES = ROOT / "stahl" / "pages"
INDEX = ROOT / "stahl" / "INDEX.md"

# Reuse the exact normalization the checker uses, so "accepted here" == "passes
# check_data" by construction (no second, drifting implementation).
_spec = importlib.util.spec_from_file_location("cd", ROOT / "tools" / "check_data.py")
_cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cd)
normalize_for_match = _cd.normalize_for_match

_ROW = re.compile(r"^\|\s*\d+\s*\|\s*(.+?)\s*\|\s*\[(\d+)-(\d+)\]")
# The NbN line, tolerant of the markdown bullet / optional bold markers Stahl's
# PDF->Markdown pipeline emits. The captured group (the line from "Neuroscience"
# onward) is stored verbatim, so whatever raw characters it holds still pass the
# verbatim check (which reads the same page file).
_NBN = re.compile(r"(Neuroscience-based Nomenclature:.*?)\s*$", re.IGNORECASE)


def _norm(name):
    """Lowercase + alphanumerics only (matches build_source_worklist._norm)."""
    return "".join(c for c in name.lower() if c.isalnum())


def page_ranges():
    out = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if m:
            out[_norm(m.group(1))] = (int(m.group(2)), int(m.group(3)))
    return out


def find_nbn_line(start, end):
    """Return (page, verbatim_line) for the first NbN line in [start, end], or
    (None, None). The line is stripped of surrounding markdown emphasis markers so
    the stored quote reads cleanly, but stays a contiguous span of the page text."""
    for p in range(start, end + 1):
        f = PAGES / f"{p}.md"
        if not f.exists():
            continue
        for raw in f.read_text(encoding="utf-8").splitlines():
            m = _NBN.search(raw)
            if m:
                quote = m.group(1).strip().strip("*").strip()
                return p, quote
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    drugs = json.loads(DRUGS_JSON.read_text(encoding="utf-8"))
    ranges = page_ranges()

    applied = skipped = no_line = mismatch = no_range = 0
    misses = []
    for d in drugs:
        nbn = d.get("nbn")
        if not nbn:
            continue
        if d.get("nbn_sources"):
            skipped += 1
            continue
        rng = ranges.get(_norm(d["name"]))
        if not rng:
            no_range += 1
            misses.append(f"{d['id']}: no page range")
            continue
        page, quote = find_nbn_line(rng[0], rng[1])
        if page is None:
            no_line += 1
            misses.append(f"{d['id']}: no 'Neuroscience-based Nomenclature' line in pp.{rng[0]}-{rng[1]}")
            continue
        # The dataset's NbN value must appear in the captured line, else the line
        # does not actually back this drug's stored NbN (author drift / wrong line).
        nbn_en = nbn.get("en") if isinstance(nbn, dict) else nbn
        if normalize_for_match(nbn_en) not in normalize_for_match(quote):
            mismatch += 1
            misses.append(f"{d['id']}: nbn {nbn_en!r} not in line {quote!r}")
            continue
        d["nbn_sources"] = [{"corpus": "stahl", "page": page,
                             "quote": quote, "provenance": "verified"}]
        applied += 1

    print(f"applied {applied}, skipped {skipped} (already sourced), "
          f"no-line {no_line}, mismatch {mismatch}, no-range {no_range}")
    for line in misses[:60]:
        print(f"  [miss] {line}")
    if len(misses) > 60:
        print(f"  ... and {len(misses) - 60} more")

    if args.dry_run:
        print("dry-run: drugs_data.json not written")
        return
    if applied:
        DRUGS_JSON.write_text(
            json.dumps(drugs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {DRUGS_JSON}")


if __name__ == "__main__":
    main()
