#!/usr/bin/env python
"""Fetch IUPHAR/BPS Guide to Pharmacology (GtoPdb) tissue-distribution statements
for the dataset's receptors, to source their expression-region ("Found in") nodes.

Each receptor's expression regions are separately-graded nodes (kind
``receptor_locations``); today they are all ``llm``. GtoPdb publishes, per target, a
"Tissue Distribution" list: a verbatim tissue sentence + assay technique + **species**
+ a PubMed id. This tool caches that list author-side and emits a **worklist** pairing
each receptor's *existing* region list (confirm-only: we never add/drop regions) with
its candidate tissue quotes, for a downstream judge to match a region to a quote.

It is the GtoPdb analogue of ``build_source_worklist.py``: network, polite, idempotent
(re-run only refetches missing targets unless ``--refresh``). Nothing here writes into
``generate_data.py``; a separate apply step turns judged matches into
``RECEPTOR_LOCATION_SOURCES`` entries.

Outputs (author-side, under the gitignored ``sources/gtopdb/``):
- ``raw/<receptor_id>.json`` : the raw GtoPdb tissueDistribution response (reference).
- ``pages/<targetId>.md``    : the cleaned tissue strings, one per line. This is the
  corpus "page" the ``gtopdb`` SOURCE_CORPORA entry points at, so ``check_data.py``'s
  verbatim-quote gate confirms each stored quote is present here (a stored quote is
  one of these lines).
- ``worklist.json``          : ``[{receptor_id, gene, target_id, regions:[bases],
  candidates:[{quote, species, pmid, technique}]}]`` for the judge.

The GtoPdb contents are CC BY-SA 4.0 (the licence the project already attributes for
Wikipedia text/molecule images). Run from the repo root::

    python tools/fetch_gtopdb.py            # fetch all mapped receptors, write worklist
    python tools/fetch_gtopdb.py --only 5ht2a,d2
    python tools/fetch_gtopdb.py --refresh  # refetch even cached targets

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "sources" / "gtopdb"
RAW = OUT / "raw"
PAGES = OUT / "pages"
WORKLIST = OUT / "worklist.json"
RECEPTORS_JSONL = REPO / "public" / "data" / "receptors.jsonl"
BASE = "https://www.guidetopharmacology.org/services"
UA = "neurarium-source-tool/1.0 (github; contact via repo issues)"
DELAY_S = 0.5  # polite gap between requests

# receptor id (our ids) -> HGNC gene symbol, the key GtoPdb resolves via
# ?geneSymbol=. Only receptors that carry an explicit region list are here
# (ubiquitous receptors state "throughout the brain", a single ALL node, and the
# locs=0 stubs have nothing to source). A heteromer/subfamily is mapped to its
# representative principal subunit (nAChR alpha4beta2 -> CHRNA4, 5-HT3 -> HTR3A,
# kainate -> GRIK1); the tissue-distribution join is by that gene.
RECEPTOR_GENES: dict[str, str] = {
    # serotonin
    "5ht1a": "HTR1A", "5ht1b": "HTR1B", "5ht1d": "HTR1D", "5ht1e": "HTR1E",
    "5ht1f": "HTR1F", "5ht2a": "HTR2A", "5ht2b": "HTR2B", "5ht2c": "HTR2C",
    "5ht3": "HTR3A", "5ht4": "HTR4", "5ht5a": "HTR5A", "5ht6": "HTR6", "5ht7": "HTR7",
    # dopamine
    "d1": "DRD1", "d2": "DRD2", "d3": "DRD3", "d4": "DRD4", "d5": "DRD5",
    # adrenergic
    "alpha1a": "ADRA1A", "alpha1b": "ADRA1B", "alpha1d": "ADRA1D",
    "alpha2a": "ADRA2A", "alpha2b": "ADRA2B", "alpha2c": "ADRA2C",
    "beta1": "ADRB1", "beta2": "ADRB2",
    # muscarinic + nicotinic
    "m1": "CHRM1", "m2": "CHRM2", "m3": "CHRM3", "m4": "CHRM4", "m5": "CHRM5",
    "nachr_a4b2": "CHRNA4", "nachr_a7": "CHRNA7",
    # histamine
    "h1": "HRH1", "h2": "HRH2", "h3": "HRH3",
    # opioid
    "mu": "OPRM1", "delta": "OPRD1", "kappa": "OPRK1",
    # glutamate (metabotropic + kainate representative)
    "mglur1": "GRM1", "mglur2": "GRM2", "mglur3": "GRM3", "mglur4": "GRM4",
    "mglur5": "GRM5", "kainate": "GRIK1",
    # others
    "cb1": "CNR1", "a2a": "ADORA2A", "mt1": "MTNR1A", "mt2": "MTNR1B",
    "sigma1": "SIGMAR1", "glycine": "GLRA1",
}


def http_json(url: str, tries: int = 3):
    """GET a JSON URL politely, with a couple of retries. Returns parsed JSON."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                        "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            time.sleep(DELAY_S)
            return data
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:  # noqa: PERF203
            last = exc
            time.sleep(1.0 + attempt)
    raise SystemExit(f"error: failed to fetch {url}: {last}")


def clean(text: str) -> str:
    """Strip GtoPdb's inline HTML (<i>, <sub>, ...) + unescape entities + collapse
    whitespace, so the stored quote and the cached page line are the same plain text
    (and thus pass the verbatim-quote gate identically)."""
    text = re.sub(r"<[^>]+>", "", text or "")
    return " ".join(html.unescape(text).split())


def resolve_target(gene: str) -> dict | None:
    """Resolve an HGNC gene symbol to a GtoPdb target ({targetId, name}) or None."""
    hits = http_json(f"{BASE}/targets?geneSymbol={urllib.parse.quote(gene)}")
    if not hits:
        return None
    return {"target_id": hits[0]["targetId"], "name": clean(hits[0].get("name", ""))}


def load_receptor_regions() -> dict[str, list[str]]:
    """base region ids each receptor lists today (confirm-only works over these)."""
    out: dict[str, list[str]] = {}
    for line in RECEPTORS_JSONL.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        bases = sorted({re.sub(r"_(L|R)$", "", s) for s in rec.get("locations", [])})
        out[rec["id"]] = bases
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="comma-separated receptor ids to fetch (default all)")
    ap.add_argument("--refresh", action="store_true",
                    help="refetch targets even if their raw cache exists")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    PAGES.mkdir(parents=True, exist_ok=True)
    regions_by_receptor = load_receptor_regions()

    want = list(RECEPTOR_GENES)
    if args.only:
        want = [r.strip() for r in args.only.split(",") if r.strip()]
        unknown = [r for r in want if r not in RECEPTOR_GENES]
        if unknown:
            raise SystemExit(f"error: unmapped receptor ids: {unknown}")

    worklist = []
    n_no_data = 0
    for rid in want:
        gene = RECEPTOR_GENES[rid]
        raw_path = RAW / f"{rid}.json"
        if raw_path.exists() and not args.refresh:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
        else:
            tgt = resolve_target(gene)
            if tgt is None:
                print(f"  [miss] {rid} ({gene}): no GtoPdb target", file=sys.stderr)
                continue
            entries = http_json(
                f"{BASE}/targets/{tgt['target_id']}/tissueDistribution")
            payload = {"receptor_id": rid, "gene": gene,
                       "target_id": tgt["target_id"], "target_name": tgt["name"],
                       "entries": entries or []}
            raw_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        entries = payload.get("entries", [])
        # Write the corpus page: every cleaned tissue string on its own line, so a
        # stored quote (one such string) is a verbatim substring of pages/<id>.md.
        lines = [clean(e.get("tissue", "")) for e in entries if e.get("tissue")]
        page = PAGES / f"{payload['target_id']}.md"
        page.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        candidates = []
        for e in entries:
            tissue = clean(e.get("tissue", ""))
            if not tissue:
                continue
            pmid = None
            refs = e.get("refs") or []
            if refs:
                pmid = refs[0].get("pmid")
            candidates.append({
                "quote": tissue,
                "species": e.get("species"),
                "technique": clean(e.get("technique", "")),
                "pmid": pmid,
            })
        if not candidates:
            n_no_data += 1
        worklist.append({
            "receptor_id": rid,
            "gene": gene,
            "target_id": payload["target_id"],
            "regions": regions_by_receptor.get(rid, []),
            "candidates": candidates,
        })
        print(f"  [ok]   {rid:10s} ({gene:8s}) target {payload['target_id']}: "
              f"{len(candidates)} tissue entries, {len(regions_by_receptor.get(rid, []))} regions")

    WORKLIST.write_text(json.dumps(worklist, indent=2), encoding="utf-8")
    with_data = sum(1 for w in worklist if w["candidates"])
    print(f"\nwrote {WORKLIST.relative_to(REPO)}: {len(worklist)} receptors "
          f"({with_data} with tissue data, {n_no_data} empty)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
