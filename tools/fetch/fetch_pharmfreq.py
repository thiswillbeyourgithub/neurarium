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
extraction -> gate -> neurarium). No network either. The input is the "Metabolizer
status tool" export downloaded by hand from https://pharmfreq.com, an untracked
`Metabolism.zip` at the repo root (a per-gene TSV of Subgroup / Gene / Phenotype /
Frequency), because the site offers no bulk endpoint to crawl politely.

Writes two things, mirroring every other corpus here:

* `data_sources/pharmfreq/pages/<GENE>.md`, the author-side quote-gate page
  (`page` on a source is the **gene symbol**, e.g. `CYP2D6`), gitignored with the rest
  of `data_sources/`;
* `tools/generated_cache/enzyme_variability.json`, committed, merged into `ENZYMES` by
  `generate_data.py`.

Usage:
    python tools/fetch/fetch_pharmfreq.py [--zip Metabolism.zip] [--dry-run]

Stdlib only; author-side, not served. Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = os.path.join(ROOT, "data_sources", "pharmfreq", "pages")
CACHE = os.path.join(ROOT, "tools", "generated_cache", "enzyme_variability.json")

sys.path.insert(0, os.path.join(ROOT, "tools"))
from data_generators.drugs import (  # noqa: E402
    ENZYMES, METABOLIZER_GROUPS, METABOLIZER_PHENOTYPES)

# PharmFreq's subgroup strings -> our slugs. Spelled out rather than slugified on the
# fly so an upstream rename is a loud KeyError here instead of a silently new group the
# viewer has no label for.
GROUP_SLUGS = {
    "European": "european",
    "Sub-Saharan African": "sub_saharan_african",
    "Middle East & North Africa": "middle_east_north_africa",
    "Central/South Asian": "central_south_asian",
    "East Asian": "east_asian",
    "Oceanian": "oceanian",
    "North American": "north_american",
    "South American": "south_american",
}

# PharmFreq gene symbol -> our ENZYMES key. Only where the two name the *same* enzyme:
# UGT1A1 is deliberately absent because we model the glucuronidation family as `ugt`
# plus four other isoforms, and hanging UGT1A1's frequencies off any of them would
# publish one isoform's genetics as another's.
GENE_ENZYMES = {
    "CYP2B6": "cyp2b6",
    "CYP2C9": "cyp2c9",
    "CYP2C19": "cyp2c19",
    "CYP2D6": "cyp2d6",
    "CYP3A5": "cyp3a5",
}


def _pct(f: float) -> str:
    """A frequency as the percentage the quote and the panel both show."""
    return f"{f * 100:.1f}%"


def _read_export(path: str) -> dict[str, dict[str, dict[str, float]]]:
    """``gene -> group slug -> phenotype -> frequency``, from the downloaded zip."""
    out: dict[str, dict[str, dict[str, float]]] = {}
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".txt")]
        if not names:
            raise SystemExit(f"{path}: no .txt export inside (is this the right zip?)")
        for name in sorted(names):
            with zf.open(name) as fh:
                lines = fh.read().decode("utf-8").splitlines()
            for line in lines[1:]:  # the header row names the four columns
                if not line.strip():
                    continue
                group, gene, phenotype, freq = line.split("\t")
                if phenotype not in METABOLIZER_PHENOTYPES:
                    raise SystemExit(f"{name}: unknown phenotype {phenotype!r} "
                                     f"(extend METABOLIZER_PHENOTYPES)")
                slug = GROUP_SLUGS.get(group)
                if not slug:
                    raise SystemExit(f"{name}: unknown subgroup {group!r} "
                                     f"(extend GROUP_SLUGS + METABOLIZER_GROUPS)")
                out.setdefault(gene, {}).setdefault(slug, {})[phenotype] = float(freq)
    return out


def _quote(gene: str, profile: dict[str, dict[str, float]]) -> str:
    """The one verbatim line that carries the whole profile (see the module docstring)."""
    parts = []
    for slug in METABOLIZER_GROUPS:
        row = profile.get(slug)
        if not row:
            continue
        got = ", ".join(f"{ph} {_pct(row[ph])}"
                        for ph in METABOLIZER_PHENOTYPES if ph in row)
        parts.append(f"{METABOLIZER_GROUPS[slug]['en']} {got}")
    return (f"{gene} metabolizer phenotype frequencies by population group "
            f"(PharmFreq): " + "; ".join(parts))


def _page(gene: str, profile: dict[str, dict[str, float]], quote: str) -> str:
    """The author-side page the quote gate checks against.

    The summary line the node actually quotes comes first, then the same numbers one
    group per line, so a human opening the page can read it without unpacking the
    summary. Both are generated from the same dict, so they cannot drift.
    """
    rows = []
    for slug in METABOLIZER_GROUPS:
        row = profile.get(slug)
        if not row:
            continue
        cells = " | ".join(f"{ph} {_pct(row[ph])}"
                           for ph in METABOLIZER_PHENOTYPES if ph in row)
        rows.append(f"{gene} | {METABOLIZER_GROUPS[slug]['en']} | {cells}")
    return "\n".join([f"# {gene} metabolizer status (PharmFreq)", "", quote, ""] + rows) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", default=os.path.join(ROOT, "Metabolism.zip"),
                    help="the PharmFreq 'Metabolizer status tool' export")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    if not os.path.exists(args.zip):
        raise SystemExit(f"{args.zip}: not found. Download the Metabolizer status tool "
                         f"export from https://pharmfreq.com and leave it there.")

    data = _read_export(args.zip)
    enzymes: dict[str, dict] = {}
    for gene in sorted(data):
        enzyme = GENE_ENZYMES.get(gene)
        if not enzyme:
            print(f"  skipped {gene}: no enzyme in ENZYMES names exactly this isoform")
            continue
        if enzyme not in ENZYMES:
            raise SystemExit(f"{gene} maps to unknown enzyme {enzyme!r} (see ENZYMES)")
        profile = data[gene]
        quote = _quote(gene, profile)
        enzymes[enzyme] = {
            "gene": gene,
            "profile": {slug: profile[slug] for slug in METABOLIZER_GROUPS
                        if slug in profile},
            "sources": [{"corpus": "pharmfreq", "page": gene, "quote": quote,
                         "provenance": "verified", "extraction": "code"}],
        }
        if not args.dry_run:
            os.makedirs(PAGES, exist_ok=True)
            with open(os.path.join(PAGES, f"{gene}.md"), "w", encoding="utf-8") as fh:
                fh.write(_page(gene, profile, quote))

    missing = sorted(set(GENE_ENZYMES.values()) - set(enzymes))
    if not args.dry_run:
        with open(CACHE, "w", encoding="utf-8") as fh:
            json.dump({"enzymes": enzymes}, fh, ensure_ascii=False, indent=1,
                      sort_keys=True)
    print(f"{len(enzymes)} enzyme(s) profiled across "
          f"{len({g for e in enzymes.values() for g in e['profile']})} population groups"
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
