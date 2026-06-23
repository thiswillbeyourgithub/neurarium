#!/usr/bin/env python
"""Apply extracted source quotes to ``tools/drugs_data.json``.

Takes the JSON returned by the source-extraction workflow,
``[{id, accepted:[{idx, page, quote}]}]``, and for each accepted binding:

* re-searches the drug's Stahl page range for the (normalized) quote, so the
  *page is found locally* rather than trusted from the agent;
* only when the quote is genuinely present does it write
  ``{corpus: stahl, page, quote, provenance: verified}`` onto that binding.

This is the local twin of ``check_data.py``'s source-quote gate: an extraction the
agent paraphrased or hallucinated simply fails to match and is rejected (left
un-sourced), so nothing untrustworthy is written. Idempotent: a binding that is
already sourced is left untouched. Stdlib only; authoring helper, not served.

Usage:
    python tools/apply_source_quotes.py RESULTS.json [--dry-run]

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
    if len(needle.replace(" ", "")) < 12:
        return None  # too short to trust (see check_data _MIN_QUOTE_CHARS)
    for p in range(start, end + 1):
        f = PAGES / f"{p}.md"
        if f.exists() and needle in normalize_for_match(f.read_text(encoding="utf-8")):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", help="workflow results JSON")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    drugs = json.loads(DRUGS_JSON.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in drugs}
    ranges = page_ranges()

    applied = rejected = skipped = 0
    rejects = []
    for r in results:
        d = by_id.get(r["id"])
        if not d:
            continue
        rng = ranges.get(_norm(d["name"]))
        for acc in r.get("accepted", []):
            idx = acc["idx"]
            if idx >= len(d["bindings"]):
                continue
            b = d["bindings"][idx]
            if b.get("sources"):
                skipped += 1
                continue
            page = find_page(rng[0], rng[1], acc["quote"]) if rng else None
            if page is None:
                rejected += 1
                rejects.append(f"{r['id']}[{idx}] {b['target']}: {acc['quote']!r}")
                continue
            b["sources"] = [{"corpus": "stahl", "page": page,
                             "quote": acc["quote"], "provenance": "verified"}]
            applied += 1

    print(f"applied {applied}, rejected {rejected} (quote not found verbatim), "
          f"skipped {skipped} (already sourced)")
    for line in rejects[:40]:
        print(f"  [reject] {line}")
    if len(rejects) > 40:
        print(f"  ... and {len(rejects) - 40} more")

    if args.dry_run:
        print("dry-run: drugs_data.json not written")
        return
    if applied:
        DRUGS_JSON.write_text(
            json.dumps(drugs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {DRUGS_JSON}")


if __name__ == "__main__":
    main()
