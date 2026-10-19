#!/usr/bin/env python
"""Fetch IUPHAR/BPS Guide to Pharmacology (GtoPdb) *classification* facts for the
dataset's receptors and non-receptor targets, to source their mechanism nodes.

This is GtoPdb's third slice, next to corpus #7 (``fetch_gtopdb.py``, the tissue API
behind the expression regions) and corpus #11 (``fetch_gtopdb_ki.py``, the bulk ligand
interactions behind the affinities). Here we read two structured fields per target:

- ``type`` (``gpcr`` / ``lgic`` / ``vgic`` / ``enzyme`` / ...), which is our
  ``receptor_class`` (metabotropic vs ionotropic) and a non-receptor target's ``type``.
- ``/transduction`` (``transducers`` + ``effectors``), which is what a receptor's
  ``sign`` (excitatory / inhibitory) is read off, GPCRs only. GtoPdb states the
  transduction, never a sign, so the mapping lives in the *applier* and is
  deliberately conservative (see ``apply_classification_sources.py``).

GtoPdb has **no pre/post-synaptic field**, so ``synaptic`` is out of reach here and
honestly stays ``llm``; that gap needs textbook prose, not this corpus.

Nothing here writes grades: this caches the facts author-side and emits a proposal
file for the apply step, exactly like the other fetchers. Outputs:

- ``data_sources/gtopdb/pages_class/<targetId>.md`` : the quote-gate page, one
  flattened fact per line. A stored quote is one of these lines, so
  ``check_data.py``'s verbatim-quote gate applies unchanged (author-side; skipped +
  warned on a clone lacking the tree, like every other ``pages*/``).
- ``tools/generated_cache/gtopdb_class.json`` : the committed proposals
  ``{owner_id: {kind, gene, target_id, target_name, type, family, type_quote,
  transduction: [...]}}``.

Contents CC BY-SA 4.0, database ODbL (attributed in the corpus registry). Run from
the repo root::

    python tools/fetch/fetch_gtopdb_class.py             # all receptors + targets
    python tools/fetch/fetch_gtopdb_class.py --only 5ht2a,d2,pde5
    python tools/fetch/fetch_gtopdb_class.py --refresh   # refetch cached targets

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_gtopdb import (  # noqa: E402  (path shim above)
    BASE,
    clean,
    file_date,
    http_json,
)
from lib.page_file import page_path  # noqa: E402 (refuses a path-like page)
from lib.io_atomic import atomic_write_json  # noqa: E402  (tools/ is on sys.path via fetch_gtopdb)
from lib.gene_maps import receptor_genes  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent   # script lives in tools/fetch/
OUT = REPO / "data_sources" / "gtopdb"
RAW = OUT / "raw_class"
PAGES = OUT / "pages_class"
CACHE = REPO / "tools" / "generated_cache" / "gtopdb_class.json"
RECEPTORS_JSONL = REPO / "public" / "data" / "receptors.jsonl"


# The non-receptor targets whose classification node is still unsourced. Each maps to
# the gene of the isoform our entry actually models.
TARGET_GENES: dict[str, str] = {
    "carbonic_anhydrase": "CA2",
    "pde5": "PDE5A",
    "cav_t": "CACNA1G",
    "melanocortin": "MC4R",
}


def target_record(gene: str) -> dict | None:
    """Resolve an HGNC gene symbol to GtoPdb's target record (type + family + name)."""
    hits = http_json(f"{BASE}/targets?geneSymbol={gene}")
    if not hits:
        return None
    hit = hits[0]
    return {
        "target_id": hit["targetId"],
        "target_name": clean(hit.get("name", "")),
        "type": (hit.get("type") or "").strip().lower(),
        "family": "; ".join(clean(f) for f in (hit.get("familyNames") or [])),
    }


def subject(rec: dict, gene: str) -> str:
    """The line prefix naming what a fact is about, so a quote reads on its own."""
    return f"{rec['target_name']} ({gene}), GtoPdb target {rec['target_id']}"


def fetch_one(owner: str, gene: str, kind: str, refresh: bool) -> dict | None:
    """Fetch (or reuse) one owner's classification facts and write its corpus page."""
    raw_path = RAW / f"{owner}.json"
    if raw_path.exists() and not refresh:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        rec = target_record(gene)
        if rec is None:
            print(f"  [miss] {owner} ({gene}): no GtoPdb target", file=sys.stderr)
            return None
        # Transduction is a GPCR-only table; other types return an empty list.
        entries = http_json(f"{BASE}/targets/{rec['target_id']}/transduction") or []
        payload = {"owner": owner, "kind": kind, "gene": gene, **rec,
                   "transduction_raw": entries, "fetched": time.strftime("%Y-%m-%d")}
        raw_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    subj = subject(payload, gene)
    # The header stamps the download date (data_generators/freshness.py reads it).
    lines: list[str] = [f"fetched: {payload.get('fetched') or file_date(raw_path)}"]
    type_quote = f"{subj} | type: {payload['type']}"
    if payload.get("family"):
        type_quote += f" | family: {payload['family']}"
    lines.append(type_quote)

    transduction = []
    for e in payload.get("transduction_raw", []):
        transducers = clean(e.get("transducers", ""))
        effectors = clean(e.get("effectors", ""))
        if not transducers and not effectors:
            continue
        quote = f"{subj} | transduction: {transducers or 'not stated'}"
        if effectors:
            quote += f" | effectors: {effectors}"
        if e.get("secondaryMechanism"):
            quote += " | secondary mechanism"
        lines.append(quote)
        transduction.append({
            "transducers": transducers,
            "effectors": effectors,
            "secondary": bool(e.get("secondaryMechanism")),
            "quote": quote,
        })

    page = page_path(PAGES, payload['target_id'])
    page.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "kind": kind,
        "gene": gene,
        "target_id": payload["target_id"],
        "target_name": payload["target_name"],
        "type": payload["type"],
        "family": payload.get("family", ""),
        "type_quote": type_quote,
        "transduction": transduction,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="comma-separated receptor/target ids (default all)")
    ap.add_argument("--refresh", action="store_true",
                    help="refetch even when the raw cache exists")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    PAGES.mkdir(parents=True, exist_ok=True)

    wanted: dict[str, tuple[str, str]] = {}   # owner -> (gene, kind)
    for rid, gene in receptor_genes().items():
        wanted[rid] = (gene, "receptor")
    for tid, gene in TARGET_GENES.items():
        wanted[tid] = (gene, "target")

    if args.only:
        keep = [o.strip() for o in args.only.split(",") if o.strip()]
        unknown = [o for o in keep if o not in wanted]
        if unknown:
            raise SystemExit(f"error: unmapped ids: {unknown}")
        wanted = {o: wanted[o] for o in keep}

    # A scoped run must not wipe the rest of the cache (the lesson of the --only bug
    # in fetch_ki.py): start from what is on disk and overwrite only what we fetch.
    cache: dict[str, dict] = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    n_trans = 0
    for owner, (gene, kind) in wanted.items():
        rec = fetch_one(owner, gene, kind, args.refresh)
        if rec is None:
            continue
        cache[owner] = rec
        n_trans += 1 if rec["transduction"] else 0
        print(f"  [ok]   {owner:14s} ({gene:8s}) target {rec['target_id']:5d} "
              f"type={rec['type']:14s} transduction={len(rec['transduction'])}")

    atomic_write_json(CACHE, cache, indent=2, sort_keys=True, ensure_ascii=True)
    print(f"\nwrote {CACHE.relative_to(REPO)}: {len(cache)} owners "
          f"({n_trans} with a transduction table this run)")
    print(f"pages under {PAGES.relative_to(REPO)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
