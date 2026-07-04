#!/usr/bin/env python
"""Apply judged expression-location matches into ``tools/location_sources.json``.

The expression-sourcing pipeline runs: ``fetch_gtopdb.py`` (cache tissue quotes +
emit ``sources/gtopdb/worklist.json``) -> an LLM judge maps each receptor's *existing*
region to a supporting tissue quote (confirm-only) -> **this tool** turns the judge's
accepted matches into quote-level ``location_sources`` and merges them into the
committed ``tools/location_sources.json`` (loaded by ``generate_data.py``'s
``_merge_external_location_sources`` into ``RECEPTOR_LOCATION_SOURCES`` /
``TARGET_LOCATION_SOURCES``). It is the location analogue of
``apply_source_quotes.py`` / ``apply_category_sources.py``.

The judge refers to each quote by its **index** into that receptor's ``candidates``
list (not free text), so there is no quote to re-find or drift: this tool reads the
verbatim quote + species straight from the worklist, so a stored quote is exactly a
line already cached under ``sources/gtopdb/pages/<targetId>.md`` and the
``check_data.py`` verbatim-quote gate passes by construction. It still re-confirms the
quote is present on that page (reusing ``check_data.normalize_for_match``) and refuses
a match that is not, so a stale worklist can't smuggle an unsourced quote through.

Idempotent: re-running rewrites the same file. Run from the repo root::

    python tools/apply_location_sources.py --judged sources/gtopdb/judged.json
    python tools/apply_location_sources.py --judged sources/gtopdb/judged.json --dry-run

``--judged`` is a JSON list ``[{receptor_id | target_id, matches: [{base, candidate,
species?}]}]``. Regenerate + check afterwards (``python tools/generate_data.py &&
python tools/check_data.py``).

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
GTOPDB = REPO / "sources" / "gtopdb"
WORKLIST = GTOPDB / "worklist.json"
PAGES = GTOPDB / "pages"
OUT = TOOLS / "location_sources.json"

sys.path.insert(0, str(TOOLS))
from check_data import normalize_for_match  # noqa: E402  (reuse the gate's normalizer)


def load_worklist() -> dict[str, dict]:
    """Index the GtoPdb worklist by owner id (receptor_id)."""
    if not WORKLIST.exists():
        raise SystemExit(f"error: {WORKLIST} missing; run tools/fetch_gtopdb.py first")
    return {w["receptor_id"]: w for w in json.loads(WORKLIST.read_text("utf-8"))}


def page_text(target_id: int) -> str:
    """Cached tissue page for a GtoPdb target (the quote gate's reference text)."""
    p = PAGES / f"{target_id}.md"
    return p.read_text("utf-8") if p.exists() else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--judged", required=True,
                    help="judge results JSON [{receptor_id, matches:[{base, candidate}]}]")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written, change nothing")
    args = ap.parse_args()

    worklist = load_worklist()
    judged = json.loads(Path(args.judged).read_text("utf-8"))

    # Start from any existing file so re-runs merge rather than clobber (a future
    # Allen pass writes into the same file under different corpora/owners).
    existing = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {}
    receptors = existing.get("receptors", {})

    n_applied = n_skipped = 0
    warnings: list[str] = []
    for entry in judged:
        rid = entry.get("receptor_id") or entry.get("target_id")
        w = worklist.get(rid)
        if w is None:
            warnings.append(f"unknown receptor {rid!r} in judged file (skipped)")
            continue
        cands = w["candidates"]
        tid = w["target_id"]
        ptext = normalize_for_match(page_text(tid))
        per_base = receptors.setdefault(rid, {})
        for m in entry.get("matches", []):
            base = m["base"]
            idx = m["candidate"]
            if base not in w["regions"]:
                warnings.append(f"{rid}: base {base!r} not a listed region (skipped)")
                n_skipped += 1
                continue
            if not isinstance(idx, int) or not (0 <= idx < len(cands)):
                warnings.append(f"{rid}/{base}: candidate index {idx} out of range")
                n_skipped += 1
                continue
            c = cands[idx]
            quote = c["quote"]
            if ptext and normalize_for_match(quote) not in ptext:
                warnings.append(f"{rid}/{base}: quote not found on page {tid} (skipped)")
                n_skipped += 1
                continue
            src = {"corpus": "gtopdb", "page": tid, "quote": quote,
                   "provenance": "verified"}
            if c.get("species"):
                src["species"] = c["species"]
            # Dedup: one source per (base) unless a genuinely different quote.
            bucket = per_base.setdefault(base, [])
            if any(s.get("quote") == quote for s in bucket):
                continue
            bucket.append(src)
            n_applied += 1

    payload = {"receptors": receptors}
    if existing.get("targets"):
        payload["targets"] = existing["targets"]

    for w_ in warnings:
        print(f"  [warn] {w_}", file=sys.stderr)
    print(f"applied {n_applied} location source(s), skipped {n_skipped}; "
          f"{sum(len(b) for r in receptors.values() for b in r.values())} total "
          f"receptor location sources across {len(receptors)} receptors")
    if args.dry_run:
        print("(dry run: not written)")
        return 0
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
