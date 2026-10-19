#!/usr/bin/env python
"""Pull ClinPGx's clinical annotations for this dataset's receptor and target genes (corpus #20).

ClinPGx (formerly PharmGKB) curates, per gene variant, what the literature associates
with it under a drug: "Patients with the GG genotype may have an increased risk of
nausea when treated with ...". This pass keeps the annotations whose gene encodes a
modeled receptor or target (`genes.GENE_OWNERS`, receptor first) at evidence levels
1A-3 (`clinpgx.VARIANT_LEVELS`), and writes them as one committed export the generator
reads and `check_data.py` re-derives.

**Deterministic, no judge.** Every field is a TSV column copied verbatim; the only
mapping is an upstream drug name to our drug id (the CPIC fetcher's `roster()`, so the
two corpora cannot disagree on a name), kept parallel to the upstream names so an
unmatched class ("opioids") still reaches the panel. A citation from here is therefore
`extraction: "code"` on a `machine` corpus.

Licence: ClinPGx data is CC BY-SA 4.0. The licence text is committed beside the export
and the corpus citation names ClinPGx; ShareAlike covers the shipped subset.

Writes:
* `tools/data/clinpgx/clinical_annotations.json` (+ `LICENSE.txt`), the kept rows;
* `tools/generated_cache/clinpgx_variants.json`, the export's sha256 pin.

The downloaded zip stays author-side under `data_sources/clinpgx/` (gitignored).

Usage:
    python tools/fetch/fetch_clinpgx.py [--refresh] [--dry-run]

Stdlib only; author-side. Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
import urllib.request
import zipfile
from collections import Counter
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ZIP = os.path.join(ROOT, "data_sources", "clinpgx", "clinicalAnnotations.zip")

sys.path.insert(0, os.path.join(ROOT, "tools"))
from lib.io_atomic import atomic_write_json, atomic_write_text  # noqa: E402
from lib import cache_io  # noqa: E402
from lib import polite_http  # noqa: E402 (the one polite GET + User-Agent)
from data_generators.clinpgx import (  # noqa: E402
    DOWNLOAD_URL, EXPORT_NAME, PIN_CACHE, VARIANT_LEVELS, export_path, owners_of,
    read_export, sha256)
from fetch.fetch_cpic import roster  # noqa: E402

TIMEOUT = 120
# Upstream names the roster spells differently. A plain INN names the racemate, so
# "methylphenidate" is our (D,L) entry and "dextroamphetamine" our (D) one; no other
# enantiomer is ever aliased (see tools/chirality.py).
NAME_ALIASES = {
    "methylphenidate": "methylphenidate_dl",
    "amphetamine": "amphetamine_dl",
    "dextroamphetamine": "amphetamine_d",
    "valproic acid": "valproate",
    "3,4-methylenedioxymethamphetamine": "mdma",
}
LICENCE = ("ClinPGx (PharmGKB) clinical annotations, CC BY-SA 4.0; "
           "cite per https://www.pharmgkb.org/page/citingPharmgkb")


def download(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    req = polite_http.request(DOWNLOAD_URL)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        blob = resp.read()
    with open(path, "wb") as fh:
        fh.write(blob)


def split(cell: str) -> list[str]:
    return [p.strip() for p in (cell or "").split(";") if p.strip()]


def tsv(zf: zipfile.ZipFile, name: str) -> list[dict]:
    with zf.open(name) as fh:
        return list(csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8"), delimiter="\t"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true", help="re-download the zip")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    if args.refresh or not os.path.exists(ZIP):
        download(ZIP)
    with zipfile.ZipFile(ZIP) as zf:
        created = next((m.group(1) for n in zf.namelist()
                        if (m := re.match(r"CREATED_(\d{4}-\d{2}-\d{2})\.txt$", n))), "")
        licence_text = zf.read("LICENSE.txt").decode("utf-8")
        anns = tsv(zf, "clinical_annotations.tsv")
        alleles = tsv(zf, "clinical_ann_alleles.tsv")

    by_ann: dict[str, list[dict]] = {}
    for a in alleles:
        by_ann.setdefault(a["Clinical Annotation ID"], []).append(
            {"genotype": a["Genotype/Allele"].strip(),
             "text": " ".join(a["Annotation Text"].split()),
             "function": a["Allele Function"].strip()})
    names = {**roster(), **NAME_ALIASES}
    rows, unmatched = [], Counter()
    for r in anns:
        genes = split(r["Gene"])
        if r["Level of Evidence"] not in VARIANT_LEVELS or not owners_of(genes):
            continue
        drugs = split(r["Drug(s)"])
        ids = [names.get(d.lower()) for d in drugs]
        unmatched.update(d for d, i in zip(drugs, ids) if not i)
        rows.append({
            "id": r["Clinical Annotation ID"], "variant": r["Variant/Haplotypes"].strip(),
            "genes": genes, "level": r["Level of Evidence"],
            "categories": split(r["Phenotype Category"]),
            "drugs": drugs, "drug_ids": ids, "phenotypes": split(r["Phenotype(s)"]),
            "population": r["Specialty Population"].strip(),
            "pmids": int(r["PMID Count"] or 0),
            "genotypes": by_ann.get(r["Clinical Annotation ID"], []),
        })
    rows.sort(key=lambda x: x["id"])

    export = {"fetched": date.today().isoformat(), "created": created,
              "url": DOWNLOAD_URL, "licence": LICENCE, "rows": rows}
    path = export_path(ROOT)
    if not args.dry_run:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_write_json(path, export, trailing_newline=False, indent=1, sort_keys=True)
        atomic_write_text(os.path.join(os.path.dirname(path), "LICENSE.txt"), licence_text)
        read_export(path)  # shape-check what was just written
        cache_io.write(PIN_CACHE, {"export_sha256": {EXPORT_NAME: sha256(path)}})

    levels = Counter(r["level"] for r in rows)
    genes = Counter(g for r in rows for g in r["genes"] if owners_of([g]))
    print(f"{len(rows)} annotation(s) at levels {'/'.join(VARIANT_LEVELS)} "
          f"(export created {created})" + (" (dry run, nothing written)" if args.dry_run else ""))
    print("  by level: " + ", ".join(f"{k} {levels[k]}" for k in VARIANT_LEVELS))
    print("  by gene: " + ", ".join(f"{g} {n}" for g, n in genes.most_common()))
    print(f"  {len(unmatched)} upstream drug name(s) match no roster drug "
          f"(kept as names): {', '.join(n for n, _ in unmatched.most_common(12))} ...")


if __name__ == "__main__":
    main()
