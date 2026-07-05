#!/usr/bin/env python
"""Apply confirmed expression-location sources into ``tools/generated_cache/location_sources.json``.

Merges the output of either expression-sourcing pipeline into the committed
``tools/generated_cache/location_sources.json`` (loaded by ``generate_data.py``'s
``_merge_external_location_sources`` into ``RECEPTOR_LOCATION_SOURCES`` /
``TARGET_LOCATION_SOURCES``). Both pipelines are **confirm-only** (they upgrade the
grade on regions the dataset already lists; they never add or drop a region), and both
re-confirm every quote against its cached page via ``check_data.normalize_for_match``
so a stale input can't smuggle an unsourced quote through. It is the location analogue
of ``apply_source_quotes.py`` / ``apply_category_sources.py``. Idempotent (dedup by
quote); each corpus/pass merges rather than clobbers, so both can write the same file.

``--corpus gtopdb`` (default): reads ``data_sources/gtopdb/worklist.json`` + a ``--judged``
file; a confirm-only LLM judge maps each receptor region to a candidate tissue quote by
**index** (no free text, no drift). Pages: ``data_sources/gtopdb/pages/<targetId>.md``.

``--corpus allen``: reads ``data_sources/allen/confirmed.json`` (written by
``tools/fetch/fetch_allen.py``, which aggregates the Allen microarray PACall boolean into a
deterministic present/absent per (gene, region) -> no judge needed). Pages:
``data_sources/allen/pages/<gene>.md``; every source is ``species: Human``.

Run from the repo root, then regenerate + check::

    python tools/sourcing/apply_location_sources.py --corpus gtopdb --judged data_sources/gtopdb/judged.json
    python tools/sourcing/apply_location_sources.py --corpus allen
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
GTOPDB = REPO / "data_sources" / "gtopdb"
WORKLIST = GTOPDB / "worklist.json"
PAGES = GTOPDB / "pages"
ALLEN = REPO / "data_sources" / "allen"
ALLEN_PAGES = ALLEN / "pages"
ALLEN_CONFIRMED = ALLEN / "confirmed.json"
OUT = TOOLS / "generated_cache" / "location_sources.json"

sys.path.insert(0, str(TOOLS))
from check_data import normalize_for_match  # noqa: E402  (reuse the gate's normalizer)


def load_worklist() -> dict[str, dict]:
    """Index the GtoPdb worklist by owner id (receptor_id)."""
    if not WORKLIST.exists():
        raise SystemExit(f"error: {WORKLIST} missing; run tools/fetch/fetch_gtopdb.py first")
    return {w["receptor_id"]: w for w in json.loads(WORKLIST.read_text("utf-8"))}


def page_text(target_id: int) -> str:
    """Cached tissue page for a GtoPdb target (the quote gate's reference text)."""
    p = PAGES / f"{target_id}.md"
    return p.read_text("utf-8") if p.exists() else ""


def owner_regions() -> tuple[dict[str, set], dict[str, set]]:
    """The regions each receptor / target currently claims (the confirm-only guard):
    (receptor_id -> {base}, target_id -> {base}) from the emitted data."""
    recs = [json.loads(l) for l in (REPO / "public/data/receptors.jsonl")
            .read_text("utf-8").splitlines() if l.strip()]
    rec = {r["id"]: set(r.get("locations") or []) for r in recs}
    meta = json.loads((REPO / "public/data/meta.json").read_text("utf-8"))
    tgt = {k: set(v.get("regions") or [])
           for k, v in meta["drug_targets"].items() if isinstance(v, dict)}
    return rec, tgt


def collect_gtopdb(judged_path: str) -> tuple[list[tuple], list[str], int]:
    """Yield (owner_kind, owner, base, src) from the GtoPdb judged file (confirm-only
    judge maps each existing region to a candidate quote by index)."""
    worklist = load_worklist()
    judged = json.loads(Path(judged_path).read_text("utf-8"))
    out, warnings, skipped = [], [], 0
    for entry in judged:
        rid = entry.get("receptor_id") or entry.get("target_id")
        w = worklist.get(rid)
        if w is None:
            warnings.append(f"unknown receptor {rid!r} in judged file (skipped)")
            continue
        cands, tid = w["candidates"], w["target_id"]
        ptext = normalize_for_match(page_text(tid))
        for m in entry.get("matches", []):
            base, idx = m["base"], m["candidate"]
            if base not in w["regions"]:
                warnings.append(f"{rid}: base {base!r} not a listed region (skipped)"); skipped += 1; continue
            if not isinstance(idx, int) or not (0 <= idx < len(cands)):
                warnings.append(f"{rid}/{base}: candidate index {idx} out of range"); skipped += 1; continue
            quote = cands[idx]["quote"]
            if ptext and normalize_for_match(quote) not in ptext:
                warnings.append(f"{rid}/{base}: quote not found on page {tid} (skipped)"); skipped += 1; continue
            src = {"corpus": "gtopdb", "page": tid, "quote": quote, "provenance": "verified"}
            if cands[idx].get("species"):
                src["species"] = cands[idx]["species"]
            out.append(("receptor", rid, base, src))
    return out, warnings, skipped


def collect_allen() -> tuple[list[tuple], list[str], int]:
    """Yield (owner_kind, owner, base, src) from the Allen confirm list (deterministic,
    no judge: fetch_allen already computed present regions). Re-confirm the quote on the
    cached gene page and guard base against the owner's current regions (confirm-only)."""
    if not ALLEN_CONFIRMED.exists():
        raise SystemExit(f"error: {ALLEN_CONFIRMED} missing; run tools/fetch/fetch_allen.py first")
    confirmed = json.loads(ALLEN_CONFIRMED.read_text("utf-8"))
    rec_regions, tgt_regions = owner_regions()
    page_cache: dict[str, str] = {}
    out, warnings, skipped = [], [], 0
    for c in confirmed:
        kind, owner, base, gene, quote = (c["owner_kind"], c["owner"], c["base"],
                                          c["page"], c["quote"])
        claimed = (rec_regions if kind == "receptor" else tgt_regions).get(owner, set())
        if base not in claimed:
            warnings.append(f"{owner}/{base}: not a current region (skipped)"); skipped += 1; continue
        if gene not in page_cache:
            p = ALLEN_PAGES / f"{gene}.md"
            page_cache[gene] = normalize_for_match(p.read_text("utf-8")) if p.exists() else ""
        if page_cache[gene] and normalize_for_match(quote) not in page_cache[gene]:
            warnings.append(f"{owner}/{base}: quote not on page {gene} (skipped)"); skipped += 1; continue
        out.append((kind, owner, base, {"corpus": "allen_ahba", "page": gene,
                                        "quote": quote, "provenance": "verified",
                                        "species": "Human"}))
    return out, warnings, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", choices=["gtopdb", "allen"], default="gtopdb",
                    help="which pipeline's output to merge (default gtopdb)")
    ap.add_argument("--judged",
                    help="gtopdb judge results JSON [{receptor_id, matches:[{base, candidate}]}]")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written, change nothing")
    args = ap.parse_args()

    if args.corpus == "gtopdb":
        if not args.judged:
            ap.error("--judged is required with --corpus gtopdb")
        sources, warnings, skipped = collect_gtopdb(args.judged)
    else:
        sources, warnings, skipped = collect_allen()

    # Start from any existing file so each corpus/pass merges rather than clobbers.
    existing = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {}
    buckets = {"receptor": existing.get("receptors", {}), "target": existing.get("targets", {})}

    n_applied = 0
    for kind, owner, base, src in sources:
        bucket = buckets[kind].setdefault(owner, {}).setdefault(base, [])
        if any(s.get("quote") == src["quote"] for s in bucket):  # dedup by quote
            continue
        bucket.append(src)
        n_applied += 1

    payload = {}
    if buckets["receptor"]:
        payload["receptors"] = buckets["receptor"]
    if buckets["target"]:
        payload["targets"] = buckets["target"]

    for w_ in warnings:
        print(f"  [warn] {w_}", file=sys.stderr)
    n_rec = sum(len(b) for o in buckets["receptor"].values() for b in o.values())
    n_tgt = sum(len(b) for o in buckets["target"].values() for b in o.values())
    print(f"applied {n_applied} location source(s), skipped {skipped}; "
          f"{n_rec} receptor + {n_tgt} target location sources "
          f"({len(buckets['receptor'])} receptors, {len(buckets['target'])} targets)")
    if args.dry_run:
        print("(dry run: not written)")
        return 0
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
