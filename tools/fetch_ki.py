#!/usr/bin/env python
"""Parse the PDSP Ki database CSV into per-drug, per-target binding affinities.

PROTOTYPE (2026-07): run against one drug (`--drug risperidone`) to eyeball the
shape before wiring anything into the dataset. It only reads + summarizes; it does
NOT yet write into `generate_data.py` / `drugs_data.json`.

Source of the data: the PDSP Ki Database CSV, a public-domain NIMH resource of
experimentally measured binding-affinity (Ki, in nM) values. The file lives at
`sources/books/pdsp_ki/KiDatabase.csv` (gitignored, author-side; see that dir's
README for provenance + licensing). It is one row PER ASSAY, so a single
drug/target pair appears many times across species, tissue and radioligand.

Provenance philosophy (per the project's verified-tier ethos): the source of a Ki
value is NOT "the PDSP database" in the abstract, it is the CONTENT OF ONE CSV
ROW: its species, preparation, radioligand and literature reference. We surface a
specific representative row for each target so a value measured in rat (not human)
is never silently presented as if it were human.

Usage:
    python tools/fetch_ki.py --drug risperidone            # preview our bound targets
    python tools/fetch_ki.py --drug risperidone --all      # + candidate extra targets
    python tools/fetch_ki.py --drug risperidone --json OUT  # write the preview JSON
"""

import argparse
import csv
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CSV_PATH = os.path.join(REPO, "sources", "books", "pdsp_ki", "KiDatabase.csv")
DATASET = os.path.join(REPO, "tools", "drugs_data.json")

# The CSV column names (note the leading space PDSP put on " Ligand Name").
COL_ID = "Number"
COL_NAME = "Name"
COL_GENE = "Unigene"
COL_LIGAND = " Ligand Name"
COL_SPECIES = "species"
COL_PREP = "source"
COL_RADIO = "Hotligand"
COL_NOTE = "ki Note"
COL_KI = "ki Val"
COL_REF = "Reference"

# --- mapping PDSP targets -> our target ids ---------------------------------
# Primary join key is PDSP's HGNC gene symbol (Unigene column), canonical and
# unambiguous. Each maps to our subtype-level target id.
GENE_TO_ID = {
    "HTR1A": "5ht1a", "HTR1B": "5ht1b", "HTR1D": "5ht1d", "HTR1E": "5ht1e",
    "HTR1F": "5ht1f", "HTR2A": "5ht2a", "HTR2B": "5ht2b", "HTR2C": "5ht2c",
    "HTR3A": "5ht3", "HTR4": "5ht4", "HTR5A": "5ht5a", "HTR6": "5ht6",
    "HTR7": "5ht7",
    "DRD1": "d1", "DRD2": "d2", "DRD3": "d3", "DRD4": "d4", "DRD5": "d5",
    "ADRA1A": "alpha1a", "ADRA1B": "alpha1b", "ADRA1D": "alpha1d",
    "ADRA2A": "alpha2a", "ADRA2B": "alpha2b", "ADRA2C": "alpha2c",
    "ADRB1": "beta1", "ADRB2": "beta2", "ADRB3": "beta3",
    "CHRM1": "m1", "CHRM2": "m2", "CHRM3": "m3", "CHRM4": "m4", "CHRM5": "m5",
    "HRH1": "h1", "HRH2": "h2", "HRH3": "h3", "HRH4": "h4",
    "OPRM1": "mu", "OPRD1": "delta", "OPRK1": "kappa",
    "SLC6A4": "sert", "SLC6A3": "dat", "SLC6A2": "net", "SLC18A2": "vmat2",
    "CNR1": "cb1", "ADORA2A": "a2a", "SIGMAR1": "sigma1",
    "CHRNA7": "nachr_a7", "MAOA": "mao_a", "MAOB": "mao_b",
}

# A coarse target in our dataset (e.g. `alpha1`) has no single gene; it collects
# its subtypes. Maps our coarse id -> the set of subtype ids that count as it.
COARSE_MEMBERS = {
    "alpha1": {"alpha1", "alpha1a", "alpha1b", "alpha1c", "alpha1d"},
    "alpha2": {"alpha2", "alpha2a", "alpha2b", "alpha2c", "alpha2d"},
    "beta": {"beta", "beta1", "beta2", "beta3"},
    "muscarinic": {"muscarinic", "m1", "m2", "m3", "m4", "m5"},
}

# Fallback for the ~25% of rows with a blank Unigene: normalize the free-text
# Name and match a pattern -> our subtype/coarse id. `norm` lowercases + drops
# every non-alphanumeric, so "adrenergic Alpha1A" -> "adrenergicalpha1a".
NAME_PATTERNS = [
    (re.compile(r"5ht2a"), "5ht2a"), (re.compile(r"5ht2c"), "5ht2c"),
    (re.compile(r"5ht2b"), "5ht2b"), (re.compile(r"5ht7"), "5ht7"),
    (re.compile(r"5ht6"), "5ht6"), (re.compile(r"5ht1a"), "5ht1a"),
    (re.compile(r"d2long|d2short|d2a\b|(^|[^0-9])d2($|[^0-9])"), "d2"),
    (re.compile(r"(^|[^0-9])d3($|[^0-9])"), "d3"),
    (re.compile(r"(^|[^0-9])d4($|[^0-9])"), "d4"),
    (re.compile(r"alpha1b"), "alpha1b"), (re.compile(r"alpha1a"), "alpha1a"),
    (re.compile(r"alpha1"), "alpha1"),
    (re.compile(r"alpha2c"), "alpha2c"), (re.compile(r"alpha2a"), "alpha2a"),
    (re.compile(r"alpha2"), "alpha2"),
    (re.compile(r"(^|[^0-9])h1($|[^0-9])|histamineh1"), "h1"),
    (re.compile(r"muscarinicm1"), "m1"),
]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def resolve_target(row):
    """Map one CSV row to our subtype-level target id, or None if unmapped."""
    gene = (row.get(COL_GENE) or "").strip().upper()
    if gene in GENE_TO_ID:
        return GENE_TO_ID[gene]
    n = norm(row.get(COL_NAME))
    for pat, tid in NAME_PATTERNS:
        if pat.search(n):
            return tid
    return None


def matches_our_target(subtype_id, our_target):
    """Does a resolved subtype id count toward one of our (possibly coarse) targets?"""
    if subtype_id == our_target:
        return True
    return our_target in COARSE_MEMBERS and subtype_id in COARSE_MEMBERS[our_target]


def parse_ki(val):
    """Return (float_nm, qualifier) where qualifier is '', '>' or '<'. None if unusable."""
    s = (val or "").strip()
    if not s:
        return None
    q = ""
    if s[0] in "<>~":
        q, s = s[0], s[1:].strip()
    try:
        return float(s), q
    except ValueError:
        return None


def load_rows(drug):
    want = norm(drug)
    out = []
    with open(CSV_PATH, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if norm(row.get(COL_LIGAND)) == want:
                out.append(row)
    return out


# PDSP records a Ki of 10000 nM (10 uM) as a ceiling meaning "tested, essentially
# inactive" rather than a real measured affinity, so values >= this are excluded
# from the affinity stats and counted as inactive instead.
SENTINEL_NM = 10000.0


def _is_human(r):
    return (r.get(COL_SPECIES) or "").strip().upper() == "HUMAN"


def _defined(r):
    """A row whose preparation + radioligand are both concrete (not UNDEFINED)."""
    prep = (r.get(COL_PREP) or "").strip().upper()
    radio = (r.get(COL_RADIO) or "").strip().upper()
    return prep not in ("", "UNDEFINED") and radio not in ("", "UNDEFINED")


def summarize_target(rows, our_target):
    """Aggregate the rows matching `our_target`. Splits assays into active vs the
    inactive (>=10 uM) ceiling, counts human vs non-human, prefers human for the
    reported stats, and cites one representative CSV row (verified-grade source)."""
    hits = [r for r in rows if matches_our_target(resolve_target(r) or "", our_target)]
    if not hits:
        return None

    active, inactive, qualified = [], 0, 0
    for r in hits:
        p = parse_ki(r.get(COL_KI))
        if p is None:
            continue
        val, q = p
        if val >= SENTINEL_NM:      # ceiling sentinel -> "inactive", not an affinity
            inactive += 1
        elif q:                     # a < / > qualified value below the ceiling
            qualified += 1
        else:
            active.append((val, r))

    n_human = sum(1 for v, r in active if _is_human(r))
    n_nonhuman = len(active) - n_human
    if not active:
        return {"target": our_target, "matched_rows": len(hits), "n_human": 0,
                "n_nonhuman": 0, "inactive": inactive, "qualified": qualified,
                "inactive_only": inactive > 0}

    # Report the human tier when there is one, else fall back to non-human (flagged).
    human_rows = [(v, r) for v, r in active if _is_human(r)]
    tier = human_rows if human_rows else active
    values = sorted(v for v, _ in tier)
    med = statistics.median(values)
    # Representative = closest to the median; ties prefer a row with concrete
    # preparation/radioligand, then the lowest Ki id. So the citation is a real,
    # fully-attributed assay line rather than a synthetic median.
    rep_val, rep = min(
        tier,
        key=lambda vr: (abs(vr[0] - med), 0 if _defined(vr[1]) else 1,
                        int(vr[1].get(COL_ID) or 0)))

    return {
        "target": our_target,
        "matched_rows": len(hits),
        "human": bool(human_rows),
        "n_human": n_human,
        "n_nonhuman": n_nonhuman,
        "inactive": inactive,
        "qualified_excluded": qualified,
        "ki_nm": {"median": round(med, 3),
                  "min": round(values[0], 3), "max": round(values[-1], 3)},
        # The precise source: one CSV row, fully attributed (grade: verified).
        "source": {
            "corpus": "pdsp_ki",
            "ki_id": int(rep.get(COL_ID) or 0),
            "value_nm": rep_val,
            "species": (rep.get(COL_SPECIES) or "").strip(),
            "preparation": (rep.get(COL_PREP) or "").strip(),
            "radioligand": (rep.get(COL_RADIO) or "").strip(),
            "reference": (rep.get(COL_REF) or "").strip(),
            "note": (rep.get(COL_NOTE) or "").strip(),
            "provenance": "verified",
        },
    }


def our_drug_targets(drug):
    data = json.load(open(DATASET, encoding="utf-8"))
    for d in data:
        if d["id"] == drug:
            return [b["target"] for b in d.get("bindings", [])]
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drug", required=True, help="drug id / ligand name (e.g. risperidone)")
    ap.add_argument("--all", action="store_true",
                    help="also list PDSP targets NOT in our dataset (candidate additions)")
    ap.add_argument("--json", metavar="OUT", help="write the preview JSON here")
    args = ap.parse_args()

    if not os.path.exists(CSV_PATH):
        sys.exit("PDSP CSV not found at %s (author-side; see its README)" % CSV_PATH)

    rows = load_rows(args.drug)
    if not rows:
        sys.exit("no PDSP rows for ligand %r" % args.drug)

    bound = our_drug_targets(args.drug)

    # Policy: annotate the drug's EXISTING bindings with Ki. We do not auto-add new
    # targets. But we DO surface any target PDSP measured that we omitted whose best
    # (min) affinity beats our weakest annotated binding, since omitting a stronger
    # target than one we kept is a modeling gap the author should see.
    annotated = {tgt: summarize_target(rows, tgt) for tgt in bound}
    ann_meds = [s["ki_nm"]["median"] for s in annotated.values()
                if s and s.get("ki_nm")]
    # Threshold = the weakest annotated affinity (largest median among our bindings).
    threshold = max(ann_meds) if ann_meds else None

    # Candidate omitted targets = every target id PDSP has for this drug that we did
    # not bind, minus subtypes already covered by an annotated coarse target, and
    # collapsing a coarse's subtypes when the coarse itself is a candidate.
    covered = set(bound)
    for b in bound:
        covered |= COARSE_MEMBERS.get(b, set())
    present = {resolve_target(r) for r in rows} - {None}
    sub_to_coarse = {sub: c for c, subs in COARSE_MEMBERS.items()
                     for sub in subs if sub != c}
    candidates = {c for c in (present - covered)
                  if sub_to_coarse.get(c) not in (present - covered)}

    flagged, weaker = {}, {}
    for tgt in sorted(candidates):
        s = summarize_target(rows, tgt)
        if not s or not s.get("ki_nm"):
            continue
        stronger = threshold is not None and s["ki_nm"]["min"] < threshold
        (flagged if stronger else weaker)[tgt] = s

    result = {
        "drug": args.drug,
        "pdsp_rows": len(rows),
        # Ki for our existing bindings (this is what would be written to the dataset).
        "annotated": annotated,
        # The weakest annotated median: the bar an omitted target must beat to flag.
        "annotated_threshold_nm": threshold,
        # Omitted targets that bind STRONGER than that bar (report these to the user).
        "pdsp_only_flagged": flagged,
    }
    if args.all:
        result["pdsp_only_weaker"] = weaker  # omitted + weaker (informational)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("wrote", args.json)
    else:
        print(text)


if __name__ == "__main__":
    main()
