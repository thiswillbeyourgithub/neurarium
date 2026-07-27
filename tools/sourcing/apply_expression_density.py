#!/usr/bin/env python
"""Apply Allen expression-density profiles into ``tools/generated_cache/expression_density.json``.

The density sibling of ``apply_location_sources.py``. Where that one upgrades the grade on
"receptor R is expressed in region B", this one carries the *relative* profile across R's
regions ("and it is concentrated in these"), written by ``tools/fetch/fetch_allen.py``'s
density pass into ``data_sources/allen/density.json``.

Same guarantees as every other applier here: **confirm-only** (a profile is trimmed to the
regions the owner already claims; it never adds one), **re-gated** (each quote is
re-confirmed verbatim on ``data_sources/allen/pages/<gene>.md`` via
``check_data.normalize_for_match``, so a stale input cannot smuggle an unsourced profile
through), and **idempotent** (the output is rewritten from the input each run; this script
is its sole writer).

One profile is ONE node (kind ``receptor_density`` / ``target_density``), not one node per
region: it is a single measurement over the owner's regions, so tallying it per region
would inflate the coverage headline with ~1000 uniformly-verified nodes.

Run from the repo root, then regenerate + check::

    python tools/fetch/fetch_allen.py
    python tools/sourcing/apply_expression_density.py
    python tools/generate_data.py && python tools/check_data.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent   # tools/ (script lives in tools/sourcing/)
REPO = TOOLS.parent
ALLEN = REPO / "data_sources" / "allen"
ALLEN_PAGES = ALLEN / "pages"
ALLEN_DENSITY = ALLEN / "density.json"
OUT = TOOLS / "generated_cache" / "expression_density.json"

sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_data import normalize_for_match       # noqa: E402  (reuse the gate's normalizer)
from apply_location_sources import owner_regions  # noqa: E402  (same confirm-only guard)


def collect() -> tuple[dict[str, dict], list[str], int]:
    """Read the fetcher's density list -> ``{"receptors"/"targets": {owner: entry}}``."""
    if not ALLEN_DENSITY.exists():
        raise SystemExit(f"error: {ALLEN_DENSITY} missing; run tools/fetch/fetch_allen.py first")
    raw = json.loads(ALLEN_DENSITY.read_text("utf-8"))
    entries = raw["profiles"]
    rec_regions, tgt_regions = owner_regions()
    page_cache: dict[str, str] = {}
    buckets: dict[str, dict] = {"receptors": {}, "targets": {},
                                "min_reliability": raw["min_reliability"]}
    warnings, skipped = [], 0
    for e in entries:
        kind, owner, gene, quote = e["owner_kind"], e["owner"], e["page"], e["quote"]
        claimed = (rec_regions if kind == "receptor" else tgt_regions).get(owner, set())
        profile = {b: z for b, z in (e.get("profile") or {}).items() if b in claimed}
        dropped = sorted(set(e.get("profile") or {}) - claimed)
        if dropped:
            warnings.append(f"{owner}: profile region(s) {dropped} not claimed (trimmed)")
        if len(profile) < 2:
            warnings.append(f"{owner}: fewer than 2 claimed regions ranked (skipped)")
            skipped += 1
            continue
        if gene not in page_cache:
            p = ALLEN_PAGES / f"{gene}.md"
            page_cache[gene] = normalize_for_match(p.read_text("utf-8")) if p.exists() else ""
        if page_cache[gene] and normalize_for_match(quote) not in page_cache[gene]:
            warnings.append(f"{owner}: density quote not on page {gene} (skipped)")
            skipped += 1
            continue
        buckets["receptors" if kind == "receptor" else "targets"][owner] = {
            "reliability": e["reliability"],
            "donors": e["donors"],
            "profile": profile,
            "sources": [{"corpus": "allen_ahba", "page": gene, "quote": quote,
                         "provenance": "verified", "species": "Human"}],
        }
    return buckets, warnings, skipped


def _merged_over_cache(payload: dict) -> tuple[dict, int]:
    """Layer freshly applied profiles over the committed cache: (payload, carried).

    ``carried`` counts the profiles that were already there and are not in this run,
    i.e. exactly what a --replace would have discarded.
    """
    if not OUT.exists():
        return payload, 0
    cached = json.loads(OUT.read_text("utf-8"))
    carried = 0
    for bucket in ("receptors", "targets"):
        old = cached.get(bucket) or {}
        fresh = payload.get(bucket) or {}
        carried += len(set(old) - set(fresh))
        if old:
            payload[bucket] = {k: v for k, v in sorted({**old, **fresh}.items())}
    return payload, carried


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written, change nothing")
    ap.add_argument("--replace", action="store_true",
                    help="write ONLY the profiles in density.json, dropping any "
                         "already in the cache (use after a full fetch_allen.py run; "
                         "the default merges, so a scoped --only run is safe)")
    args = ap.parse_args()

    buckets, warnings, skipped = collect()
    for w_ in warnings:
        print(f"  [warn] {w_}", file=sys.stderr)
    payload = {k: v for k, v in buckets.items() if v}
    n_rec, n_tgt = len(buckets["receptors"]), len(buckets["targets"])
    print(f"applied {n_rec + n_tgt} density profile(s), skipped {skipped} "
          f"({n_rec} receptors, {n_tgt} targets)")
    # MERGE by default. ``fetch_allen.py --only <owner>`` rewrites density.json with
    # just that owner, so writing the fresh payload straight out would silently delete
    # every other profile from the committed cache (it did once, for 53 of them). A
    # full-corpus refresh that genuinely wants to drop a now-unreliable profile passes
    # --replace.
    if not args.replace:
        payload, carried = _merged_over_cache(payload)
        if carried:
            print(f"merged into the existing cache ({carried} profile(s) carried over; "
                  f"pass --replace to rebuild from scratch)")
    if args.dry_run:
        print("(dry run: not written)")
        return 0
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
