#!/usr/bin/env python
"""Apply extracted source quotes to ``tools/data/drugs_data.jsonl``.

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
    python tools/sourcing/apply_source_quotes.py RESULTS.json [--dry-run]

Built with the help of Claude Code.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent   # repo root (script in tools/sourcing/)
sys.path.insert(0, str(ROOT / "tools"))                # reach the shared drugs_io module
from lib import drugs_io  # noqa: E402
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
from lib.text_fold import alnum_key  # noqa: E402
from lib import stahl_index  # noqa: E402 (the one INDEX.md reader + span search)
DRUGS_JSON = drugs_io.DRUGS_PATH


_norm = alnum_key  # lowercase alphanumerics only (tools/text_fold.py)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", help="workflow results JSON")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    results = worklist_io.read(args.results)
    drugs = drugs_io.load_drugs()
    by_id = {d["id"]: d for d in drugs}
    ranges = stahl_index.ranges()

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
            page = stahl_index.find_page(rng[0], rng[1], acc["quote"], min_chars=12) if rng else None
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
        print("dry-run: drugs_data.jsonl not written")
        return
    if applied:
        drugs_io.save_drugs(drugs)
        print(f"wrote {DRUGS_JSON}")


if __name__ == "__main__":
    main()
