#!/usr/bin/env python
"""Source each drug's NbN (Neuroscience-based Nomenclature) line from Stahl.

Unlike a binding's free-prose claim, the NbN is a structured field: Stahl prints a
verbatim ``Neuroscience-based Nomenclature: <value>`` line on each drug's first
page. So this needs no extraction agent and no LLM judge. For every drug that has
an ``nbn`` but no ``nbn_sources`` yet, it:

* searches the drug's Stahl page range (from ``data_sources/books/stahl/INDEX.md``) for that line;
* captures the line **verbatim** from the page as the quote;
* confirms the dataset's own ``nbn`` value is a substring of that line (after the
  same normalization ``check_data.py`` uses), so the quote provably states *this
  drug's* NbN, a programmatic claim-support check that is strictly stronger than an
  LLM judge for this field;
* writes ``{corpus: stahl, page, quote, provenance: verified}`` onto ``nbn_sources``.

**Class-line fallback.** A few newer drugs (e.g. brexpiprazole, buprenorphine,
lumateperone) have no ``Neuroscience-based Nomenclature:`` line in Stahl at all; the
book gives only a drug-**Class** descriptor. For those the same verbatim-substring
gate is applied to the **Class** line instead, and the drug is marked
``nbn_nonstandard: true`` so the viewer can show the value honestly as a class
descriptor rather than a formal NbN. The fallback fires only when the formal NbN
line is truly absent, so a real drift on a drug that *does* have an NbN line still
reports as a mismatch rather than being papered over by its Class line.

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

import drugs_io

ROOT = Path(__file__).resolve().parent.parent
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
# The NbN line, tolerant of the markdown bullet / optional bold markers Stahl's
# PDF->Markdown pipeline emits. The captured group (the line from "Neuroscience"
# onward) is stored verbatim, so whatever raw characters it holds still pass the
# verbatim check (which reads the same page file).
_NBN = re.compile(r"(Neuroscience-based Nomenclature:.*?)\s*$", re.IGNORECASE)
# The drug-Class heading (Stahl's PDF->Markdown emits it as a bold heading), used as
# the fallback source for a drug that has no NbN line. The value is the first
# non-empty content line under the heading (a "- <descriptor>" bullet).
_CLASS_HEAD = re.compile(r"^#+\s*\*\*Class\*\*", re.IGNORECASE)


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


def find_class_line(start, end):
    """Return (page, verbatim_class_descriptor) for the first drug-Class line in
    [start, end], or (None, None). Used only as the fallback for a drug with no NbN
    line. The descriptor is the first non-empty content line under the "Class"
    heading, stripped of its list bullet + emphasis markers but still a contiguous
    span of the page text (so the verbatim check passes)."""
    for p in range(start, end + 1):
        f = PAGES / f"{p}.md"
        if not f.exists():
            continue
        lines = f.read_text(encoding="utf-8").splitlines()
        for i, ln in enumerate(lines):
            if _CLASS_HEAD.match(ln):
                for nxt in lines[i + 1:i + 8]:
                    body = nxt.strip().lstrip("-").strip().strip("*").strip()
                    if body:
                        return p, body
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    drugs = drugs_io.load_drugs()
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
        nonstandard = False
        if page is None:
            # No formal NbN line: fall back to Stahl's drug-Class descriptor and
            # flag the entry non-standard (see module docstring).
            page, quote = find_class_line(rng[0], rng[1])
            nonstandard = True
        if page is None:
            no_line += 1
            misses.append(f"{d['id']}: no NbN or Class line in pp.{rng[0]}-{rng[1]}")
            continue
        # The dataset's NbN value must appear in the captured line, else the line
        # does not actually back this drug's stored NbN (author drift / wrong line).
        nbn_en = nbn.get("en") if isinstance(nbn, dict) else nbn
        if normalize_for_match(nbn_en) not in normalize_for_match(quote):
            mismatch += 1
            src = "Class" if nonstandard else "NbN"
            misses.append(f"{d['id']}: nbn {nbn_en!r} not in {src} line {quote!r}")
            continue
        d["nbn_sources"] = [{"corpus": "stahl", "page": page,
                             "quote": quote, "provenance": "verified"}]
        if nonstandard:
            d["nbn_nonstandard"] = True
        applied += 1

    print(f"applied {applied}, skipped {skipped} (already sourced), "
          f"no-line {no_line}, mismatch {mismatch}, no-range {no_range}")
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
