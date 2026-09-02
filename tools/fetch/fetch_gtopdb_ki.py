#!/usr/bin/env python
"""Fetch the IUPHAR/BPS Guide to Pharmacology **ligand-interaction** table (corpus
#11 ``gtopdb_ki``) and turn it into per-binding affinity + direction proposals.

This is GtoPdb's *other* half. Corpus #7 (``tools/fetch/fetch_gtopdb.py``) uses its
tissue-distribution API for expression regions; here we use the hand-curated
ligand-target interaction table, which carries a measured affinity, a curated
direction (agonist / antagonist / inhibitor / allosteric modulator) and a PubMed id
per row. It complements PDSP Ki (corpus #5) in the two places a radioligand
displacement panel structurally cannot reach:

* **targets PDSP does not assay** (the GABA-A benzodiazepine site, MAO-A/B,
  acetylcholinesterase, orexin, melatonin, SV2A, Nav, carbonic anhydrase, PDE5), and
* **direction for an ``affinity_only`` binding**, where PDSP told us only *that* a
  drug binds.

Source shape: one versioned bulk CSV (``DATA/interactions.csv``, ~7 MB), so nothing
here is scraped page by page. We store it author-side and flatten the rows of every
matched compound into a quote-gate page, exactly like corpus #9's Wikipedia tables:
each proposal's ``quote`` is one verbatim line of ``pages_ki/<slug>.md``, so
``check_data.py``'s normal verbatim-quote gate covers it with no special case.

Deterministic: no LLM anywhere in this path (the CSV row *is* the claim, like Allen's
PACall boolean). Outputs (author-side, under gitignored ``data_sources/gtopdb/``):

* ``interactions.csv``          the downloaded bulk file (cached; ``--refresh`` re-pulls)
* ``pages_ki/<slug>.md``        one line per interaction row of a matched compound

and, committed:

* ``tools/generated_cache/gtopdb_ki.json``   the per-(drug, target) proposals

Run from the repo root::

    python tools/fetch/fetch_gtopdb_ki.py            # download if missing, rebuild
    python tools/fetch/fetch_gtopdb_ki.py --refresh  # re-download the bulk CSV
    python tools/fetch/fetch_gtopdb_ki.py --only diazepam,selegiline

Then merge with ``python tools/sourcing/apply_gtopdb_ki.py``.

GtoPdb contents are CC BY-SA 4.0 and the database is ODbL; both are recorded in the
corpus registry entry.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import statistics
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "fetch"))

import drugs_io                                                    # noqa: E402
from fetch_allen import TARGET_GENES                               # noqa: E402
from fetch_gtopdb import RECEPTOR_GENES                            # noqa: E402

OUT = REPO / "data_sources" / "gtopdb"
CSV_PATH = OUT / "interactions.csv"
PAGES = OUT / "pages_ki"
CACHE = REPO / "tools" / "generated_cache" / "gtopdb_ki.json"
META = REPO / "public" / "data" / "meta.json"

URL = "https://www.guidetopharmacology.org/DATA/interactions.csv"
UA = "neurarium-source-tool/1.0 (https://github.com/; research use)"

# Our target id -> gene symbol(s). RECEPTOR_GENES (corpus #7) and TARGET_GENES
# (Allen, corpus #8) already cover most ids; TARGET_GENES additionally buckets a few
# ids together for the atlas ("muscarinic", "beta"), which is why it is filtered to
# real target ids below. EXTRA_TARGET_GENES is only what neither map knows.
EXTRA_TARGET_GENES: dict[str, list[str]] = {
    # The benzodiazepine site is curated per subunit, not per assembled pentamer.
    "gaba_a": ["GABRA1", "GABRA2", "GABRA3", "GABRA4", "GABRA5", "GABRA6",
               "GABRB1", "GABRB2", "GABRB3", "GABRG2", "GABRD"],
    "gaba_a_rho": ["GABRR1", "GABRR2"],
    "gaba_b": ["GABBR1", "GABBR2"],
    "nmda": ["GRIN1", "GRIN2A", "GRIN2B", "GRIN2C", "GRIN2D"],
    "ampa": ["GRIA1", "GRIA2", "GRIA3", "GRIA4"],
    "mglur6": ["GRM6"], "mglur7": ["GRM7"],
    "nachr_muscle": ["CHRNA1", "CHRNB1", "CHRND", "CHRNE"],
    "h4": ["HRH4"], "beta3": ["ADRB3"],
    # alpha2D is the rodent orthologue of the human alpha2A gene.
    "alpha2d": ["ADRA2A"],
    "mt1": ["MTNR1A"], "mt2": ["MTNR1B"],
}

# GtoPdb files INN spellings and markup-bearing names; map ours onto theirs. Both
# sides are folded through `norm` at import, so entries can be written readably.
# Deliberately NOT here: an alias onto a *different enantiomer or salt* (armodafinil
# -> modafinil, esketamine -> ketamine). PDSP has an explicit `mapped`/`measured_as`
# warning for a borrowed value; until this corpus grows one, a near-miss compound is
# left unmatched rather than published as a verified affinity for the wrong molecule.
_RAW_ALIASES: dict[str, str] = {
    "LSD": "lysergide",
    "Tetrahydrocannabinol": "delta9-tetrahydrocannabinol",
    "DMT": "dimethyltryptamine",
    "Amphetamine (D)": "dexamfetamine", "Amphetamine (D,L)": "amphetamine",
    "Methylphenidate (D)": "dexmethylphenidate",
    "Methylphenidate (D,L)": "methylphenidate",
    "Valproate": "valproic acid",
    "Dothiepin": "dosulepin", "Flupenthixol": "flupentixol",
    "Benztropine": "benzatropine", "Pipothiazine": "pipotiazine",
    "Norquetiapine": "N-desalkylquetiapine",
    "Meta-chlorophenylpiperazine": "mCPP",
    "Licarbazepine": "eslicarbazepine",
}

# Affinity parameters, most to least directly comparable to a Ki. pKi/pKd are true
# binding affinities; the rest are functional potencies kept as a labelled fallback.
PARAM_ORDER = ["pKi", "pKd", "pIC50", "pKB", "pA2", "pEC50"]
KI_PARAMS = {"pKi", "pKd"}

# GtoPdb (Type, Action) -> our DRUG_ACTIONS key. Target-aware: an "Inhibitor" of a
# transporter is a reuptake inhibitor, of an enzyme an enzyme inhibitor, of a channel
# a blocker, so the caller passes the target id.
TRANSPORTERS = {"sert", "net", "dat", "gat"}
ENZYMES = {"mao_a", "mao_b", "ache", "bche", "carbonic_anhydrase", "pde5"}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def norm(s: str) -> str:
    """Fold a GtoPdb or dataset compound name to a comparable key (its names carry
    HTML markup: ``<i>N</i>-desalkylquetiapine``, ``&Delta;<sup>9</sup>-...``)."""
    s = re.sub(r"<[^>]+>", "", s or "")
    s = html.unescape(s).replace("Δ", "delta").replace("α", "alpha").replace("β", "beta")
    return re.sub(r"[\s\-‐-―(),]+", "", s).lower()


def plain(s: str) -> str:
    """A GtoPdb display string with its markup stripped (for the page lines)."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


LIGAND_ALIASES = {norm(k): norm(v) for k, v in _RAW_ALIASES.items()}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", plain(name).lower()).strip("-")


def owner_genes(valid_targets: set[str]) -> dict[str, set[str]]:
    """Gene symbol (upper-cased) -> the set of our target ids it stands for.

    Upper-cased because the CSV follows each species' convention (human ``SCN2A``,
    rat ``Scn2a``); joining case-sensitively silently drops every rodent row.
    """
    per_owner: dict[str, list[str]] = {}
    for rid, gene in RECEPTOR_GENES.items():
        per_owner[rid] = [gene] if isinstance(gene, str) else list(gene)
    for tid, genes in TARGET_GENES.items():
        if tid in valid_targets:                 # skip the Allen-only bucket keys
            per_owner.setdefault(tid, list(genes))
    per_owner.update(EXTRA_TARGET_GENES)
    out: dict[str, set[str]] = defaultdict(set)
    for owner, genes in per_owner.items():
        if owner in valid_targets:
            for g in genes:
                out[g.upper()].add(owner)
    return out


def download(refresh: bool) -> str:
    """Fetch the bulk interactions CSV once; return its version header line."""
    if refresh or not CSV_PATH.exists():
        OUT.mkdir(parents=True, exist_ok=True)
        log(f"downloading {URL} ...")
        req = urllib.request.Request(URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=180) as r:
            CSV_PATH.write_bytes(r.read())
        log(f"  wrote {CSV_PATH} ({CSV_PATH.stat().st_size // 1024} KB)")
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        return f.readline().strip().strip('"')


def read_rows() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        f.readline()                              # the "# GtoPdb Version:" header
        return list(csv.DictReader(f))


def affinity_values(row: dict) -> list[float]:
    return [float(v) for v in (row.get("Affinity Median"), row.get("Affinity High"),
                               row.get("Affinity Low")) if v]


def pick_row(rows: list[dict], target: str) -> dict | None:
    """The most usable row for one (compound, target): a human assay first, then the
    most Ki-like affinity parameter, then the tightest affinity.

    A row with no number at all is still worth something when GtoPdb curated a
    *direction* on it (cannabidiol's negative allosteric modulation of CB1 is filed
    exactly that way: an action, no affinity reported), so those are the fallback when
    the target has no measured row: a claim with a citation and no number beats no
    claim. Human first there too."""
    scored = []
    directional = []
    for r in rows:
        vals = affinity_values(r)
        if not vals:
            if action_for(r, target):
                directional.append(((r.get("Target Species") != "Human",), r))
            continue
        param = r.get("Affinity Units") or ""
        scored.append(((r.get("Target Species") != "Human",
                        PARAM_ORDER.index(param) if param in PARAM_ORDER else 99,
                        -statistics.median(vals)), r))
    if not scored:
        if not directional:
            return None
        directional.sort(key=lambda x: x[0])
        return directional[0][1]
    scored.sort(key=lambda x: x[0])
    return scored[0][1]


def action_for(row: dict, target: str) -> str | None:
    """Map a row's curated (Type, Action) onto our DRUG_ACTIONS vocabulary."""
    act = (row.get("Action") or "").strip().lower()
    typ = (row.get("Type") or "").strip().lower()
    if typ == "inhibitor" or act == "inhibition":
        if target == "vmat2":
            return "vesicular_inhibitor"
        if target in TRANSPORTERS:
            return "reuptake_inhibitor"
        if target in ENZYMES:
            return "enzyme_inhibitor"
        return "blocker"
    if act == "partial agonist":
        return "partial_agonist"
    if act in ("full agonist", "agonist") or typ == "agonist":
        return "agonist"
    if act == "inverse agonist":
        return "inverse_agonist"
    if act == "antagonist" or typ == "antagonist":
        return "antagonist"
    if act == "positive":
        return "pam"
    if act == "negative":
        return "nam"
    if typ == "channel blocker" or "channel block" in act:
        return "blocker"
    return None


def row_line(row: dict) -> str:
    """One interaction row flattened to a single quotable line.

    This is both what lands in ``pages_ki/<slug>.md`` and what a proposal cites as its
    ``quote``, so the two match by construction and the verbatim gate is meaningful
    (it pins the target, the species, the direction, the number and the citation).
    """
    vals = affinity_values(row)
    param = row.get("Affinity Units") or "-"
    if len(vals) > 1:
        aff = f"{param} {min(vals):g}-{max(vals):g}"
    elif vals:
        aff = f"{param} {vals[0]:g}"
    else:
        aff = "no affinity reported"
    direction = " / ".join(x for x in (plain(row.get("Type")), plain(row.get("Action"))) if x)
    pmid = (row.get("PubMed ID") or "").split("|")[0]
    return (f"{plain(row.get('Ligand'))} at {plain(row.get('Target'))} "
            f"({row.get('Target Gene Symbol') or '?'}, {row.get('Target Species') or '?'}): "
            f"{direction or 'direction not stated'}, {aff}"
            f"{f' [PMID {pmid}]' if pmid else ''}")


def nm_from(row: dict) -> tuple[float, float, float] | None:
    """(median, min, max) in nM from a row's pX affinity, or None."""
    vals = affinity_values(row)
    if not vals:
        return None
    nm = sorted(10 ** (9 - v) for v in vals)
    return (statistics.median(nm), nm[0], nm[-1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-download the bulk CSV")
    ap.add_argument("--only", help="comma-separated drug ids to scope to")
    args = ap.parse_args()

    version = download(args.refresh)
    rows = read_rows()
    log(f"{len(rows)} interaction rows ({version})")

    meta = json.loads(META.read_text(encoding="utf-8"))
    valid_targets = set(meta["drug_targets"])
    gene_owner = owner_genes(valid_targets)
    log(f"gene map covers {len({o for os_ in gene_owner.values() for o in os_})} "
        f"of {len(valid_targets)} targets")

    by_ligand: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_ligand[norm(r.get("Ligand"))].append(r)

    drugs = drugs_io.load_drugs()
    only = {x.strip() for x in args.only.split(",")} if args.only else None

    PAGES.mkdir(parents=True, exist_ok=True)
    proposals: dict[str, dict[str, dict]] = {}
    stats = {"drugs": 0, "unmatched": 0, "ki": 0, "action": 0, "pages": 0}
    unmatched: list[str] = []

    for drug in drugs:
        if only and drug["id"] not in only:
            continue
        key = LIGAND_ALIASES.get(norm(drug["name"]), norm(drug["name"]))
        cands = by_ligand.get(key, [])
        if not cands:
            # A combination product has no single ligand record, which is expected.
            if " + " not in drug["name"] and "–" not in drug["name"]:
                unmatched.append(drug["name"])
                stats["unmatched"] += 1
            continue

        slug = slugify(cands[0].get("Ligand"))
        lines = sorted({row_line(r) for r in cands})
        (PAGES / f"{slug}.md").write_text(
            f"# GtoPdb interactions: {plain(cands[0].get('Ligand'))}\n"
            f"# source: {URL} ({version})\n\n" + "\n".join(lines) + "\n",
            encoding="utf-8")
        stats["pages"] += 1

        per_target: dict[str, list[dict]] = defaultdict(list)
        for r in cands:
            for owner in gene_owner.get((r.get("Target Gene Symbol") or "").upper(), ()):
                per_target[owner].append(r)

        found: dict[str, dict] = {}
        for target, trows in per_target.items():
            row = pick_row(trows, target)
            if row is None:
                continue
            entry: dict = {
                "source": {
                    "corpus": "gtopdb_ki",
                    "page": slug,
                    "quote": row_line(row),
                    "provenance": "verified",
                    "species": row.get("Target Species") or None,
                },
            }
            nm = nm_from(row)
            # Only a true binding affinity (pKi/pKd) becomes a Ki. A functional
            # potency (pIC50/pEC50/pKB/pA2) is a different measurement, so it rides
            # along as the direction's citation without pretending to be a Ki.
            if nm and (row.get("Affinity Units") in KI_PARAMS):
                entry["ki"] = {
                    "median": round(nm[0], 4), "min": round(nm[1], 4), "max": round(nm[2], 4),
                    "n_human": 1 if row.get("Target Species") == "Human" else 0,
                    "n_nonhuman": 0 if row.get("Target Species") == "Human" else 1,
                    "param": row.get("Affinity Units"),
                }
                stats["ki"] += 1
            action = action_for(row, target)
            if action:
                entry["action"] = action
                stats["action"] += 1
            entry["pmid"] = (row.get("PubMed ID") or "").split("|")[0] or None
            found[target] = entry

        if found:
            proposals[drug["id"]] = found
            stats["drugs"] += 1

    # A scoped run only ever *looked* at `only`, so its proposals cannot stand for the
    # whole corpus: merge them over the committed cache instead of replacing it (a plain
    # write would silently drop every other drug's proposals).
    if only and CACHE.exists():
        prior = json.loads(CACHE.read_text(encoding="utf-8")).get("drugs", {})
        for did in only:                       # a re-run that now finds nothing must clear
            prior.pop(did, None)
        prior.update(proposals)
        proposals = prior

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"version": version, "url": URL, "drugs": proposals},
                                indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                     encoding="utf-8")

    if unmatched:
        log(f"no GtoPdb ligand for {len(unmatched)}: {', '.join(sorted(unmatched))}")
    log(f"{stats['drugs']} drug(s) matched, {stats['pages']} page(s) written, "
        f"{stats['ki']} affinity + {stats['action']} direction proposal(s)")
    log(f"wrote {CACHE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
