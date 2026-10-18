#!/usr/bin/env python
"""Pull CPIC's prescribing guidance for this roster's gene-drug pairs (corpus #15).

Corpus #13 (PharmFreq) says how common each clearance speed is; the enzyme nodes say
which isoform clears which drug. Neither says what either *means* for a prescription,
and that is the one thing a clinician reading a metabolizer frequency actually wants:
a CYP2D6 ultrarapid metabolizer on nortriptyline is not a curiosity, it is CPIC's
"increased probability of pharmacotherapy failure". This corpus is that third layer,
and only that: it adds no anatomy, no binding and no new drug.

**Scope, and why it is this narrow.** Only CPIC pairs whose gene has a metabolizer
frequency profile here (`pharmfreq.GENE_ENZYMES`: CYP2D6, CYP2C19, CYP2C9, CYP2B6,
CYP3A5), because a recommendation with no frequency beside it cannot answer "how likely
is this patient". That leaves out pairs this roster does carry and that matter a great
deal (HLA-B with carbamazepine and oxcarbazepine, HLA-A, SCN1A, the urea-cycle genes
with valproate): they are a gap in *this* corpus, recorded in docs/SOURCING_GAPS.md, not
a judgement that they are unimportant.

**Deterministic, no judge.** Every field is a structured column, copied verbatim; the
only mapping is CPIC's phenotype string to our slug, and the only filtering is written
down in `data_generators/cpic.py` (the `general` population, the five phenotypes a
frequency exists for, and the two-gene rows whose other gene is normal). So a quote from
here is `pipeline = machine`, `extraction: "code"`.

Licence: CPIC curated content is CC0 1.0, which asks for attribution rather than
requiring it; the citation in `SOURCE_CORPORA["cpic"]` names clinpgx.org as the primary
source, cites the guideline publication per row, and stamps the API version + date the
export was taken, which is what CPIC's data-use terms ask of an API consumer.

Writes two committed things:
* `tools/data/cpic/cpic_recommendations.json`, the rows verbatim (the evidence the quote
  gate checks against, pinned by sha256);
* `tools/generated_cache/cpic_guidance.json`, the shaped nodes `generate_data.py` merges.

Usage:
    python tools/fetch/fetch_cpic.py [--dry-run] [--only <drug id> ...]

Stdlib only (urllib); author-side, not served. Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "tools", "generated_cache", "cpic_guidance.json")
DRUGS = os.path.join(ROOT, "tools", "data", "drugs_data.jsonl")

sys.path.insert(0, os.path.join(ROOT, "tools"))
from lib.io_atomic import atomic_write_json  # noqa: E402
from lib import polite_http  # noqa: E402 (the one polite GET + User-Agent)
from data_generators.cpic import (  # noqa: E402
    ASSUMED, EXPORT_NAME, PHENOTYPE_SLUGS, POPULATIONS, export_path,
    guidance_for, read_export, sha256)
from data_generators.pharmfreq import GENE_ENZYMES  # noqa: E402

API = "https://api.cpicpgx.org/v1"
# Level A is "prescribing action recommended", B "could be considered". Both ship, with
# the level on the block, because a reader deciding whether to act on a 4.6% prior needs
# to know which of the two they are looking at.
LEVELS = ("A", "B")
TIMEOUT = 60


def get(table: str, **params) -> list[dict]:
    """One PostgREST GET, as JSON rows."""
    url = f"{API}/{table}?" + urllib.parse.urlencode(params)
    req = polite_http.request(url, {"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{url}\n  HTTP {exc.code}: {exc.read()[:400].decode()}")


def roster() -> dict[str, str]:
    """Every name a CPIC drug might arrive under -> our drug id."""
    names: dict[str, str] = {}
    with open(DRUGS, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            drug = json.loads(line)
            for name in [drug["id"], drug["id"].replace("_", " "),
                         drug.get("name", "")] + list(drug.get("aliases") or []):
                if name:
                    names.setdefault(name.lower(), drug["id"])
    return names


def isolate(phenotypes: dict[str, str], gene: str) -> tuple[bool, dict[str, str]]:
    """Can this row speak about `gene` alone, and under what assumption?

    A single-gene row speaks for itself. A two-gene row only isolates `gene` when the
    other gene sits at the phenotype the dosing guidance assumes, and then the
    assumption has to travel with the row.
    """
    others = {g: p for g, p in phenotypes.items() if g != gene}
    if not others:
        return True, {}
    if all(p == ASSUMED for p in others.values()):
        return True, {g: PHENOTYPE_SLUGS[ASSUMED] for g in others}
    return False, {}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", default=None, help="limit to these drug ids")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    names = roster()
    pairs = get("pair", select="genesymbol,drugid,guidelineid,cpiclevel,version,"
                               "citations,removed,drug!inner(name)",
                cpiclevel=f"in.({','.join(LEVELS)})", removed="is.false", limit="1000")

    wanted: dict[tuple[str, str], dict] = {}
    unmatched: list[str] = []
    pending: list[str] = []
    for pair in pairs:
        gene = pair["genesymbol"]
        name = (pair["drug"] or {}).get("name", "").lower()
        drug = names.get(name)
        if not drug:
            unmatched.append(f"{name} ({gene})")
            continue
        if gene not in GENE_ENZYMES:
            continue
        if args.only and drug not in args.only:
            continue
        # A pair can be levelled without a guideline behind it yet (CPIC rates the
        # evidence before it writes the dosing text). There is nothing to quote then,
        # so it is dropped rather than published as guidance.
        if not pair.get("guidelineid"):
            pending.append(f"{drug} / {gene}")
            continue
        wanted[(drug, gene)] = pair

    # One recommendation pull per guideline, not per pair: a guideline covers several
    # drugs (the tricyclics share one), so this is 4 requests rather than 29.
    guidelines: dict[str, dict] = {}
    recs: list[dict] = []
    for gid in sorted({str(p["guidelineid"]) for p in wanted.values()}):
        meta = get("guideline", select="id,name,url,clinpgxid,version", id=f"eq.{gid}")
        if not meta:
            raise SystemExit(f"guideline {gid}: no such row")
        guidelines[gid] = {"name": meta[0]["name"], "url": meta[0]["url"],
                           "clinpgxid": meta[0]["clinpgxid"],
                           "version": meta[0]["version"]}
        recs += get("recommendation",
                    select="guidelineid,drugid,phenotypes,implications,"
                           "drugrecommendation,classification,population,version,"
                           "drug!inner(name)",
                    guidelineid=f"eq.{gid}", limit="5000")

    # Which population each pair is read under, decided once per pair rather than per
    # row so one list cannot mix two kinds of patient. `POPULATIONS` is ordered by the
    # question this panel asks (an adult about to start the drug), and a population
    # outside it is dropped loudly below rather than silently averaged in.
    chosen: dict[tuple[str, str], str] = {}
    offered: dict[tuple[str, str], set[str]] = {}
    for rec in recs:
        drug = names.get((rec["drug"] or {}).get("name", "").lower())
        for gene in (rec["phenotypes"] or {}):
            if (drug, gene) in wanted:
                offered.setdefault((drug, gene), set()).add(rec["population"])
    for key, pops in offered.items():
        for pop in POPULATIONS:
            if pop in pops:
                chosen[key] = pop
                break

    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for rec in recs:
        name = (rec["drug"] or {}).get("name", "").lower()
        drug = names.get(name)
        phenotypes = rec["phenotypes"] or {}
        for gene, raw in phenotypes.items():
            if (drug, gene) not in wanted:
                continue
            if rec["population"] != chosen.get((drug, gene)):
                continue
            slug = PHENOTYPE_SLUGS.get(raw)
            if not slug:
                continue  # an uncertainty phenotype: no frequency to pair it with
            alone, assumes = isolate(phenotypes, gene)
            if not alone:
                continue
            key = (drug, gene, slug)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "drug": drug, "gene": gene, "phenotype": slug,
                "implication": (rec["implications"] or {}).get(gene, "").strip(),
                "recommendation": (rec["drugrecommendation"] or "").strip(),
                "classification": rec["classification"],
                "level": wanted[(drug, gene)]["cpiclevel"],
                "population": rec["population"],
                "guideline": rec["guidelineid"],
                "citations": wanted[(drug, gene)].get("citations") or [],
                **({"assumes": assumes} if assumes else {}),
                "version": rec["version"],
            })
    rows.sort(key=lambda r: (r["drug"], r["gene"],
                             list(PHENOTYPE_SLUGS.values()).index(r["phenotype"])))

    export = {"fetched": date.today().isoformat(), "api": API,
              "licence": "CPIC curated content, CC0 1.0 Universal; primary source "
                         "www.clinpgx.org",
              "guidelines": guidelines, "rows": rows}
    path = export_path(ROOT)
    if not args.dry_run:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_write_json(path, export, trailing_newline=False, indent=1, sort_keys=True)
        guidance = guidance_for(read_export(path))
        atomic_write_json(CACHE, {"export_sha256": {EXPORT_NAME: sha256(path)},
                                  "guidance": guidance},
                          trailing_newline=False, indent=1, sort_keys=True)

    drugs = {r["drug"] for r in rows}
    genes = {r["gene"] for r in rows}
    print(f"{len(rows)} recommendation row(s) over {len(drugs)} drug(s) and "
          f"{len(genes)} gene(s), from {len(guidelines)} guideline(s)"
          + (" (dry run, nothing written)" if args.dry_run else ""))
    for gene in sorted(genes):
        got = sorted({r["drug"] for r in rows if r["gene"] == gene})
        print(f"  {gene}: {len(got)} drug(s) - {', '.join(got)}")
    # A pair CPIC acts on that this dataset does not even model the route for is a hole
    # in our enzyme data, so say it every run rather than letting it pass as covered.
    if not args.only:
        print(f"  {len(unmatched)} CPIC pair(s) are for drugs outside this roster")
        # A pair whose guideline exists but whose rows are all filed under another
        # drug or an unreadable phenotype: nothing to publish, said out loud so it is
        # not mistaken for covered.
        empty = sorted(f"{d} / {g}" for (d, g) in wanted
                       if not any(r["drug"] == d and r["gene"] == g for r in rows))
        if empty:
            print(f"  guideline but no usable row: {', '.join(empty)}")
        skipped = sorted(f"{d} / {g} ({'/'.join(sorted(p))})"
                         for (d, g), p in offered.items() if (d, g) not in chosen)
        if skipped:
            print(f"  no population this panel can read: {', '.join(skipped)}")
        if pending:
            print(f"  levelled but no guideline text yet: {', '.join(sorted(pending))}")


if __name__ == "__main__":
    main()
