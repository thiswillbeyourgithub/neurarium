#!/usr/bin/env python
"""Parse the PDSP Ki database CSV into per-drug, per-target binding affinities.

PROTOTYPE (2026-07): run against one drug (`--drug risperidone`) to eyeball the
shape before wiring anything into the dataset. It only reads + summarizes; it does
NOT yet write into `generate_data.py` / `drugs_data.jsonl`.

Source of the data: the PDSP Ki Database CSV, a public-domain NIMH resource of
experimentally measured binding-affinity (Ki, in nM) values. The file lives at
`data_sources/books/pdsp_ki/KiDatabase.csv` (gitignored, author-side; see that dir's
README for provenance + licensing). It is one row PER ASSAY, so a single
drug/target pair appears many times across species, tissue and radioligand.

Provenance philosophy (per the project's verified-tier ethos): the source of a Ki
value is NOT "the PDSP database" in the abstract, it is the CONTENT OF ONE CSV
ROW: its species, preparation, radioligand and literature reference. We surface a
specific representative row for each target so a value measured in rat (not human)
is never silently presented as if it were human.

Usage:
    python tools/fetch/fetch_ki.py --drug risperidone            # preview our bound targets
    python tools/fetch/fetch_ki.py --drug risperidone --all      # + candidate extra targets
    python tools/fetch/fetch_ki.py --drug risperidone --json OUT  # write the preview JSON
"""

import argparse
import csv
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))   # repo root (script in tools/fetch/)
sys.path.insert(0, os.path.dirname(HERE))        # tools/ for the shared drugs_io module
import drugs_io  # noqa: E402
CSV_PATH = os.path.join(REPO, "data_sources", "books", "pdsp_ki", "KiDatabase.csv")

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

# A coarse target in our dataset (e.g. `alpha2`) has no single gene; it collects
# its subtypes. Maps our coarse id -> the set of subtype ids that count as it. Only
# α2 remains coarse (its autoreceptor tone lives on the group node); the muscarinic /
# α1 / β / nicotinic families are split into per-subtype targets, so they resolve
# straight to their subtype ids and must NOT collapse back to a coarse bucket here.
COARSE_MEMBERS = {
    "alpha2": {"alpha2", "alpha2a", "alpha2b", "alpha2c", "alpha2d"},
}

# Fallback for the ~25% of rows with a blank Unigene: normalize the free-text
# Name and match a pattern -> our subtype/coarse id. `norm` lowercases + drops
# every non-alphanumeric, so "adrenergic Alpha1A" -> "adrenergicalpha1a".
NAME_PATTERNS = [
    # Nicotinic ACh receptors: PDSP lists these subtypes with a blank Unigene, so the
    # gene join misses them. Route the high-affinity a4b2 to `nachr_a4b2` and every
    # other neuronal subtype to `nachr_a7` as the "other nicotinic" bucket. These MUST
    # precede the adrenergic alpha patterns below, else a name like "Nicotinic
    # Alpha2Beta2" would be mis-read as adrenergic alpha2 (its substring "alpha2").
    (re.compile(r"alpha4beta2|nicotinicalpha4beta2|^a4b2"), "nachr_a4b2"),
    (re.compile(r"nicotinic|nachr|alpha\dbeta\d|alpha7|^a\db\d"), "nachr_a7"),
    # Transporters / ion channels / sigma PDSP also frequently lists with a blank
    # Unigene (the gene join covers the SLC*-labelled rows; these catch the rest).
    (re.compile(r"norepinephrinetransporter|noradrenalinetransporter|^net$"), "net"),
    (re.compile(r"nmda"), "nmda"),
    (re.compile(r"cannabinoidcb1|^cb1$"), "cb1"),
    (re.compile(r"opiatesigma|sigma1|^sigma$"), "sigma1"),
    (re.compile(r"5ht2a"), "5ht2a"), (re.compile(r"5ht2c"), "5ht2c"),
    (re.compile(r"5ht2b"), "5ht2b"), (re.compile(r"5ht7"), "5ht7"),
    (re.compile(r"5ht6"), "5ht6"), (re.compile(r"5ht1a"), "5ht1a"),
    (re.compile(r"d2long|d2short|d2a\b|(^|[^0-9])d2($|[^0-9])"), "d2"),
    (re.compile(r"(^|[^0-9])d3($|[^0-9])"), "d3"),
    (re.compile(r"(^|[^0-9])d4($|[^0-9])"), "d4"),
    # α1 is split into subtypes: match the lettered subtypes, but a subtype-less
    # "Alpha1" assay resolves to None (dropped) rather than a coarse bucket we no
    # longer carry. α2 keeps its coarse fallback (still a coarse target).
    (re.compile(r"alpha1b"), "alpha1b"), (re.compile(r"alpha1a"), "alpha1a"),
    (re.compile(r"alpha1d"), "alpha1d"),
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


# --- resolving our drug -> PDSP rows ----------------------------------------
# Curated alias map for drugs PDSP lists under a chemically-related name (an
# enantiomer, salt, prodrug or active metabolite). Each maps our drug id -> the
# EXACT PDSP ligand name(s) to borrow, plus the chemical relation and a human note.
# EVERY aliased match is flagged so the viewer warns which compound the Ki was
# actually measured on. Deutetrabenazine / valbenazine are deliberately NOT here:
# PDSP has only a single distant `tetrabenazine` assay, too weak to map honestly.
# Each value is (pdsp_names, relation, compound): `compound` is a short, language-
# neutral chemical label of what PDSP actually measured (shown in the viewer's "⚠
# measured as <compound>" badge); `relation` (identity | enantiomer | racemate |
# prodrug | metabolite) is turned into a localized phrase by the viewer.
ALIAS = {
    "paliperidone": (["9-OH-risperidone"], "identity", "9-OH-risperidone"),
    "esketamine": (["(S)-(+)-ketamine"], "enantiomer", "(S)-ketamine"),
    "amphetamine_d": (["Amphetamine,(+)", "(+)-Amphetamine"], "identity",
                      "(+)-amphetamine"),
    "amphetamine_dl": (["Amphetamine"], "identity", "amphetamine"),
    "methylphenidate_dl": (["METHYLPHENIDATE"], "identity", "methylphenidate"),
    "moclobemide": (["moclobemide, MCL"], "identity", "moclobemide"),
    "selegiline": (["selegiline, SEL"], "identity", "selegiline"),
    "levomilnacipran": (["Milnacipran"], "racemate", "milnacipran"),
    "zopiclone": (["eszopiclone"], "enantiomer", "eszopiclone"),
    "quazepam": (["2-Oxoquazepam"], "metabolite", "2-oxoquazepam"),
    "lofexidine": (["Levlofexidine"], "enantiomer", "levlofexidine"),
    "lisdexamfetamine": (["Amphetamine,(+)", "(+)-Amphetamine"], "prodrug",
                         "(+)-amphetamine"),
    "serdexmethylphenidate": (["METHYLPHENIDATE"], "prodrug", "methylphenidate"),
}

_ALL_ROWS = None


def all_rows():
    global _ALL_ROWS
    if _ALL_ROWS is None:
        with open(CSV_PATH, newline="", encoding="utf-8", errors="replace") as f:
            _ALL_ROWS = list(csv.DictReader(f))
    return _ALL_ROWS


def combo_constituents(name):
    """Combos ("A + B", "A-B" with an en/em dash) split into their parts, else None.
    Only + and en/em dashes count, never a plain hyphen (which appears in real names)."""
    if not name:
        return None
    if "+" in name or "–" in name or "—" in name:
        parts = re.split(r"\s*[+–—]\s*", name)
        return [p.strip() for p in parts if p.strip()]
    return None


def resolve_rows(name, drug_id):
    """Return (rows, mapping) for a drug. mapping is None for a direct name match,
    else {pdsp_names, relation, note} when recovered through the alias map."""
    rows = all_rows()
    want = {norm(name), norm(drug_id)}
    direct = [r for r in rows if norm(r.get(COL_LIGAND)) in want]
    if direct:
        return direct, None
    if drug_id in ALIAS:
        pdsp_names, relation, note = ALIAS[drug_id]
        target = {n.strip().lower() for n in pdsp_names}
        aliased = [r for r in rows
                   if (r.get(COL_LIGAND) or "").strip().lower() in target]
        if aliased:
            return aliased, {"pdsp_names": pdsp_names, "relation": relation,
                             "note": note}
    return [], None


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


def find_drug(query):
    """Return (record, all_drugs) for the drug whose id or name matches `query`."""
    data = drugs_io.load_drugs()
    for d in data:
        if d["id"] == query or norm(d["name"]) == norm(query):
            return d, data
    return None, data


def _stamp_mapping(summary, mapping):
    """Mark a summary's source as recovered through the alias map, so the viewer can
    warn which compound the Ki was actually measured on."""
    if summary and mapping and summary.get("source"):
        summary["source"]["mapped"] = True
        summary["source"]["measured_as"] = mapping["note"]
        summary["source"]["relation"] = mapping["relation"]
        summary["source"]["pdsp_names"] = mapping["pdsp_names"]


def analyze(rows, bound):
    """Split a drug's PDSP rows into annotated (its existing bindings), auto_add
    (omitted targets stronger by median than the weakest binding -> to be added),
    flagged_min_only (stronger only at best assay -> reported, not added) and weaker.
    Shared by the single-drug preview and --apply so the policy lives in one place."""
    annotated = {tgt: summarize_target(rows, tgt) for tgt in bound}
    ann_meds = [s["ki_nm"]["median"] for s in annotated.values()
                if s and s.get("ki_nm")]
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
    rest = present - covered
    candidates = {c for c in rest if sub_to_coarse.get(c) not in rest}

    auto_add, flagged_min_only, weaker = {}, {}, {}
    for tgt in sorted(candidates):
        s = summarize_target(rows, tgt)
        if not s or not s.get("ki_nm"):
            continue
        med, mn = s["ki_nm"]["median"], s["ki_nm"]["min"]
        if threshold is None or med >= threshold:
            (flagged_min_only if (threshold is not None and mn < threshold)
             else weaker)[tgt] = s
        else:
            auto_add[tgt] = s
    return {"annotated": annotated, "threshold": threshold, "auto_add": auto_add,
            "flagged_min_only": flagged_min_only, "weaker": weaker}


def _ki_from_summary(s):
    """The binding `ki` object written into drugs_data.jsonl, from a target summary."""
    ki = {
        "median": s["ki_nm"]["median"], "min": s["ki_nm"]["min"],
        "max": s["ki_nm"]["max"], "n_human": s["n_human"],
        "n_nonhuman": s["n_nonhuman"], "source": s["source"],
    }
    # Assays that hit the >=10 uM "tested, essentially inactive" ceiling are excluded
    # from the affinity stats; keep their count so the viewer can say the target was
    # tested and found not to bind, rather than silently showing only the active tier.
    if s.get("inactive"):
        ki["inactive"] = s["inactive"]
    return ki


def _is_pdsp_ki(binding):
    return binding.get("ki", {}).get("source", {}).get("corpus") == "pdsp_ki"


def _is_curated_ki(binding):
    """A hand-attached Ki the auto-pass must NOT touch. The resolver drops every
    assay >=10 uM as "inactive", so a genuine but weak binder (caffeine at A2a,
    amantadine at NMDA: real, sub-sentinel measurements) can only be recorded by
    hand; mark it ``source.curated`` so this idempotent refresh never strips it."""
    return bool(binding.get("ki", {}).get("source", {}).get("curated"))


def _ki_owned_by_pdsp(binding):
    """True iff --apply may write/refresh this binding's ``ki``: it has no Ki yet, or
    the Ki it has is fetch_ki's own prior (non-curated PDSP) output.

    A ``wikipedia_pharm`` fallback Ki (corpus #9, written only where PDSP had none) and
    a hand-curated Ki both belong to another tool. Annotating over them would flip the
    source corpus to ``pdsp_ki``; the NEXT --apply's strip then deletes the (now
    pdsp-looking) affinity-only binding, so the pass oscillates and loses data. Leaving
    a non-owned slot alone keeps --apply an idempotent fixpoint (its documented
    contract: it "only owns pdsp_ki Ki")."""
    ki = binding.get("ki")
    if not ki:
        return True
    if _is_curated_ki(binding):
        return False
    return _is_pdsp_ki(binding)


def apply_all(only=None):
    """Write PDSP Ki into tools/data/drugs_data.jsonl for every resolvable drug: annotate
    existing bindings with a `ki`, add the median-stronger omitted targets as new
    `affinity_only` bindings. Idempotent: strips its own prior output first, so a
    re-run after a fresh CSV download simply refreshes the values.

    ``only`` (a set of drug ids) scopes the pass to those drugs. Use it when adding a
    single drug: a corpus-wide refresh legitimately rewrites every drug whose PDSP rows
    moved since the last run, which buries the one-drug change in an unrelated diff."""
    data = drugs_io.load_drugs()
    n_ann = n_add = n_drugs = 0
    for d in data:
        if only and d["id"] not in only:
            continue
        # Idempotency: drop what a previous --apply added before recomputing, but
        # never a hand-curated Ki (a real sub-sentinel binder the resolver can't
        # reproduce, see _is_curated_ki).
        d["bindings"] = [b for b in d.get("bindings", [])
                         if not (b.get("affinity_only") and _is_pdsp_ki(b)
                                 and not _is_curated_ki(b))]
        for b in d["bindings"]:
            if _is_pdsp_ki(b) and not _is_curated_ki(b):
                b.pop("ki", None)

        if combo_constituents(d["name"]):     # combos handled in the viewer, not here
            continue
        rows, mapping = resolve_rows(d["name"], d["id"])
        if not rows:
            continue
        bound = [b["target"] for b in d["bindings"]]
        res = analyze(rows, bound)
        for s in list(res["annotated"].values()) + list(res["auto_add"].values()):
            _stamp_mapping(s, mapping)
        touched = False
        for b in d["bindings"]:
            if not _ki_owned_by_pdsp(b):   # curated or wikipedia_pharm fallback: leave alone
                continue
            s = res["annotated"].get(b["target"])
            if s and s.get("ki_nm"):
                b["ki"] = _ki_from_summary(s)
                n_ann += 1
                touched = True
        for tgt, s in res["auto_add"].items():
            d["bindings"].append({"target": tgt, "affinity_only": True,
                                  "ki": _ki_from_summary(s)})
            n_add += 1
            touched = True
        if touched:
            n_drugs += 1

    drugs_io.save_drugs(data)
    print("applied Ki to %d drugs: %d bindings annotated, %d affinity-only added"
          % (n_drugs, n_ann, n_add))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drug", help="drug id / ligand name to preview (e.g. risperidone)")
    ap.add_argument("--apply", action="store_true",
                    help="write Ki into tools/data/drugs_data.jsonl for every drug (idempotent)")
    ap.add_argument("--only", default="",
                    help="comma-separated drug ids to scope --apply to (e.g. bromazepam)")
    ap.add_argument("--all", action="store_true",
                    help="also list omitted PDSP targets weaker than our weakest binding")
    ap.add_argument("--json", metavar="OUT", help="write the preview JSON here")
    args = ap.parse_args()

    if not os.path.exists(CSV_PATH):
        sys.exit("PDSP CSV not found at %s (author-side; see its README)" % CSV_PATH)

    if args.apply:
        apply_all({s.strip() for s in args.only.split(",") if s.strip()} or None)
        return
    if not args.drug:
        sys.exit("give --drug <id> to preview, or --apply to write the dataset")

    rec, data = find_drug(args.drug)

    # A combo drug is not in PDSP as a mixture: report its constituents (linked to our
    # standalone drugs where they exist) so the viewer can warn + link out.
    combo = combo_constituents(rec["name"]) if rec else None
    if combo:
        ids = {d["id"] for d in data}
        by_name = {norm(d["name"]): d["id"] for d in data}
        constituents = [{"name": p,
                         "drug_id": p.lower() if p.lower() in ids else by_name.get(norm(p))}
                        for p in combo]
        print(json.dumps({"drug": args.drug, "combo": True,
                          "constituents": constituents}, ensure_ascii=False, indent=2))
        return

    name = rec["name"] if rec else args.drug
    did = rec["id"] if rec else args.drug
    rows, mapping = resolve_rows(name, did)
    if not rows:
        sys.exit("no PDSP rows for %r (no direct match or alias)" % args.drug)

    bound = [b["target"] for b in rec["bindings"]] if rec else []
    res = analyze(rows, bound)
    for grp in ("annotated", "auto_add", "flagged_min_only", "weaker"):
        for s in res[grp].values():
            _stamp_mapping(s, mapping)

    result = {
        "drug": args.drug,
        "pdsp_rows": len(rows),
        "mapping": mapping,               # None for a direct name match
        "annotated": res["annotated"],    # Ki for our existing bindings
        "annotated_threshold_nm": res["threshold"],
        "auto_add": res["auto_add"],      # median-stronger omitted -> would be added
        "flagged_min_only": res["flagged_min_only"],  # best-case-only -> not added
    }
    if args.all:
        result["weaker"] = res["weaker"]

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("wrote", args.json)
    else:
        print(text)


if __name__ == "__main__":
    main()
