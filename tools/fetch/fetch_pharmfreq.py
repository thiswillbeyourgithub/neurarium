#!/usr/bin/env python
"""Turn PharmFreq's metabolizer-status export into the enzyme variability corpus (#13).

Every other thing this dataset says about an enzyme is a property of a *drug*: which
isoform clears it, which one it inhibits. This is the other half, and the half a reader
actually feels: the same dose of the same drug is cleared at very different speeds by
different people, and how common each speed is differs sharply between populations
(CYP2D6 ultrarapid metabolizers are 1.5% of East Asian cohorts and 11% of Middle East /
North African ones; CYP3A5 normal metabolizers are 0.4% of European cohorts and 19.8% of
Sub-Saharan African ones). That is a sourceable fact about the enzyme, so it is a node.

**One node per enzyme, not per population group.** The whole profile is a single
published aggregation ranking the groups against each other, exactly like an Allen
density profile ranks a receptor's regions, so tallying it per group would flood the
headline with ~40 uniformly-verified nodes and say nothing more (see CLAUDE.md,
Expression density). The whole profile is written **into the quote** for the same
reason it is there: the numbers are what a reader judges the claim by, so the verbatim
gate has to cover them and the pill tooltip has to show them.

Deterministic, no judge: PharmFreq publishes the aggregated frequency, this only
reshapes it, so a quote from here is `pipeline = machine` (raw data -> deterministic
extraction -> gate -> neurarium). No network either: the "Metabolizer status tool"
export is downloaded by hand from https://pharmfreq.com (the site offers no bulk
endpoint to crawl politely) and **committed**, one TSV per gene, under
`tools/data/pharmfreq/`. Unlike the book corpora these files are small and freely
redistributable, so shipping them is what lets the quote gate run on any clone.

Writes one thing: `tools/generated_cache/enzyme_variability.json`, committed, merged
into `ENZYMES` by `generate_data.py`. It carries an `export_sha256` block pinning every
source file it read, which is what `provenance.py` and `check_data.py` re-check: there
is no author-side page here, because a page generated out of the same numbers as the
quote could not gate anything (see `data_generators/pharmfreq.py`).

Usage:
    python tools/fetch/fetch_pharmfreq.py [--dir tools/data/pharmfreq] [--dry-run]

Stdlib only; author-side, not served. Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "tools", "generated_cache", "enzyme_variability.json")

sys.path.insert(0, os.path.join(ROOT, "tools"))
from data_generators.drugs import ENZYMES  # noqa: E402
from data_generators.pharmfreq import (  # noqa: E402
    EXPORT_DIR, GENE_ENZYMES, ExportError, export_files, ordered_profile, quote_for,
    read_export, sha256)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=os.path.join(ROOT, *EXPORT_DIR.split("/")),
                    help="the committed PharmFreq 'Metabolizer status tool' export")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        raise SystemExit(f"{args.dir}: not found. The export is committed with the "
                         f"repo; download a fresh one from https://pharmfreq.com only "
                         f"to refresh it.")
    try:
        data = read_export(args.dir)
    except ExportError as exc:
        raise SystemExit(str(exc))

    enzymes: dict[str, dict] = {}
    for gene in sorted(data):
        enzyme = GENE_ENZYMES.get(gene)
        if not enzyme:
            print(f"  skipped {gene}: no enzyme in ENZYMES names exactly this isoform")
            continue
        if enzyme not in ENZYMES:
            raise SystemExit(f"{gene} maps to unknown enzyme {enzyme!r} (see ENZYMES)")
        profile = ordered_profile(data[gene])
        enzymes[enzyme] = {
            "gene": gene,
            "profile": profile,
            "sources": [{"corpus": "pharmfreq", "page": gene,
                         "quote": quote_for(gene, profile),
                         "provenance": "verified", "extraction": "code"}],
        }

    # Every file that was read, pinned. The cache and the export are then one unit: a
    # hand-edited number in either is a loud failure at generation time rather than a
    # quote nobody can trace back to a measurement.
    pins = {name: sha256(os.path.join(args.dir, name))
            for name in export_files(args.dir)}

    missing = sorted(set(GENE_ENZYMES.values()) - set(enzymes))
    if not args.dry_run:
        with open(CACHE, "w", encoding="utf-8") as fh:
            json.dump({"export_sha256": pins, "enzymes": enzymes}, fh,
                      ensure_ascii=False, indent=1, sort_keys=True)
    print(f"{len(enzymes)} enzyme(s) profiled across "
          f"{len({g for e in enzymes.values() for g in e['profile']})} population groups"
          f" from {len(pins)} pinned file(s)"
          + (" (dry run, nothing written)" if args.dry_run else ""))
    if missing:
        print(f"  mapped but not found in the export: {', '.join(missing)}")
    # The two isoforms this dataset leans on hardest are the two PharmFreq's tool does
    # not cover, so say so every run rather than letting the gap read as "not variable".
    uncovered = [ENZYMES[e]["label"] for e in ("cyp3a4", "cyp1a2") if e not in enzymes]
    if uncovered:
        print(f"  no profile published for: {', '.join(uncovered)}")


if __name__ == "__main__":
    main()
