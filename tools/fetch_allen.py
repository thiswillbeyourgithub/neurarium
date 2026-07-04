#!/usr/bin/env python
"""Fetch Allen Human Brain Atlas microarray expression -> per-region presence calls.

Phase 2 of the expression-location sourcing (see ``SOURCING_GAPS.md`` "Phase 2 plan"):
the source for the ``target_locations`` (and the residual ``receptor_locations`` GtoPdb
could not reach). Allen is the only source that resolves our deep nuclei AND covers the
non-receptor targets (transporters/enzymes/channels), and it ships a **PACall**
present/absent boolean per (probe, sample) that is a threshold-free basis for a *verified*
"expressed here" claim (the honest detection call Allen's own pipeline computes).

Licence: Allen data is copyright-reserved, non-commercial research use with required
citation (Hawrylycz et al. 2012, Nature 489:391). This project is AGPL / free /
non-commercial / educational, within those terms, and we vendor only the minimal cited
slice (the presence lines we actually cite), never the atlas, exactly as abagen/neuromaps
do under attribution.

Pipeline (mirrors ``fetch_gtopdb.py`` -> ``apply_location_sources.py``):
  1. Download each donor's ``normalized_microarray_donor<id>.zip`` (~426 MB) into
     ``sources/allen/raw/`` (author-side, gitignored; skipped if already present). We read
     only PACall.csv + SampleAnnot.csv + Probes.csv from the zip, never the ~400 MB
     MicroarrayExpression.csv, so memory stays small.
  2. Map each tissue sample to our coarse ``base`` region via ``BASE_ALLEN`` (the Allen
     ontology-subtree crosswalk) using the cached ``raw/ontology.json`` structure paths.
  3. For each gene (``TARGET_GENES`` / ``fetch_gtopdb.RECEPTOR_GENES``), pick the
     representative probe (most PACall detections) and, per base, the fraction of that
     base's samples that detect it. A base is **present** if that fraction >= ``PRESENT_MIN``
     (majority) across the downloaded donors.
  4. Emit ``sources/allen/pages/<gene>.md`` (one presence line per present base; the
     quote-gate page) and ``sources/allen/confirmed.json`` (the deterministic confirm list
     ``[{owner_kind, owner, base, page, quote}]`` that ``apply_location_sources.py
     --corpus allen`` merges into ``tools/location_sources.json``). Un-confirmable
     (owner, base) pairs (region has 0 Allen samples, e.g. pituitary) are logged, not
     dropped.

Stdlib only (urllib + zipfile + csv). Idempotent; ``--only``/``--donors``/``--refresh``.
Run from the repo root::

    python tools/fetch_allen.py                      # all targets + receptors, all donors
    python tools/fetch_allen.py --only sert,dat,mao_a --donors 9861   # prove on one donor

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
ALLEN = REPO / "sources" / "allen"
RAW = ALLEN / "raw"
PAGES = ALLEN / "pages"
ONTOLOGY_CACHE = RAW / "ontology.json"

API = "http://api.brain-map.org/api/v2/data/query.json"
DOWNLOAD = "http://human.brain-map.org/api/v2/well_known_file_download/{fid}"
UA = {"User-Agent": "neurarium-dev/0.1 (expression sourcing; contact via project repo)"}

# The 6 AHBA donors -> the well_known_file id of their NormalizedMicroarrayDataAsCSV zip.
DONORS = {
    9861: 178238387,   # H0351.2001
    10021: 178238373,  # H0351.2002
    12876: 178238359,  # H0351.1009
    14380: 178238266,  # H0351.1012
    15496: 178238316,  # H0351.1015
    15697: 178236545,  # H0351.1016
}

PRESENT_MIN = 0.5  # a base is "present" if the representative probe detects in >= half its samples

# --- Crosswalk: our coarse base region -> Allen ontology-subtree root id(s). A sample
# counts toward a base if its structure_id_path contains any of the base's roots. Nesting
# is intentional + anatomically correct (SN/VTA/midbrain-raphe are under midbrain 9001,
# LC/pontine-raphe under pons 9131, medullary-raphe under medulla 9512); confirm-only means
# a coarse region is only ever confirmed for a target we already claimed lives there.
BASE_ALLEN = {
    "frontal": [4009], "parietal": [4084], "temporal": [4132], "occipital": [4180],
    "cingulate": [4220], "insula": [4268],
    "caudate": [4278], "putamen": [4287], "accumbens": [4290], "globus_pallidus": [4293],
    "claustrum": [4321], "amygdala": [4327], "hippocampus": [4249],
    "thalamus": [4392], "hypothalamus": [4540], "septal_nuclei": [13002],
    "mammillary": [12909], "fornix": [9249],
    "cerebellum": [4696],
    "midbrain": [9001], "pons": [9131], "medulla": [9512],
    "substantia_nigra": [9072], "vta": [9066], "locus_coeruleus": [9148],
    "raphe": [9642, 9455, 9157],
    # olfactory_bulb + pituitary + subthalamic_nucleus: Allen does not sample them in this
    # atlas (pituitary is outside the brain block); left unmapped -> those regions stay llm.
}

# Non-receptor drug targets (the 25 target_locations owners) -> HGNC gene symbol(s). A
# multi-gene group (muscarinic, the adrenergic/nicotinic groups, ...) is "present in B" if
# ANY member gene detects there; the citation names the member gene that did.
TARGET_GENES = {
    "sert": ["SLC6A4"], "net": ["SLC6A2"], "dat": ["SLC6A3"], "gat": ["SLC6A1"],
    "vmat2": ["SLC18A2"], "mao_a": ["MAOA"], "mao_b": ["MAOB"],
    "ache": ["ACHE"], "bche": ["BCHE"],
    "carbonic_anhydrase": ["CA2"], "pde5": ["PDE5A"],
    "nav": ["SCN1A", "SCN2A", "SCN3A", "SCN8A"],
    "cav": ["CACNA1A", "CACNA1B", "CACNA1C"],
    "cav_a2d": ["CACNA2D1", "CACNA2D2"],
    "cav_t": ["CACNA1G", "CACNA1H", "CACNA1I"],
    "sv2a": ["SV2A"],
    "muscarinic": ["CHRM1", "CHRM2", "CHRM3", "CHRM4", "CHRM5"],
    "nicotinic": ["CHRNA4", "CHRNB2", "CHRNA7"],
    "alpha1": ["ADRA1A", "ADRA1B", "ADRA1D"],
    "alpha2": ["ADRA2A", "ADRA2B", "ADRA2C"],
    "beta": ["ADRB1", "ADRB2", "ADRB3"],
    "glutamate": ["GRIN1", "GRIA1", "GRIA2"],
    "melatonin": ["MTNR1A", "MTNR1B"],
    "orexin": ["HCRTR1", "HCRTR2"],
    "melanocortin": ["MC4R", "MC3R"],
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def fetch_ontology() -> list[dict]:
    """Cache the Allen human-brain-atlas ontology (graph 10) once."""
    if ONTOLOGY_CACHE.exists():
        return json.loads(ONTOLOGY_CACHE.read_text("utf-8"))
    url = (API + "?criteria=model::Structure,rma::criteria,[graph_id$eq10],"
           "rma::options[num_rows$eq'all']")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        structs = json.loads(r.read().decode())["msg"]
    RAW.mkdir(parents=True, exist_ok=True)
    ONTOLOGY_CACHE.write_text(json.dumps(structs), encoding="utf-8")
    log(f"cached {len(structs)} ontology structures")
    return structs


def build_structure_bases(structs: list[dict]) -> dict[int, list[str]]:
    """structure_id -> the base region(s) whose crosswalk root is on its ontology path."""
    root_to_base = {rid: base for base, roots in BASE_ALLEN.items() for rid in roots}
    out: dict[int, list[str]] = {}
    for s in structs:
        path = [int(x) for x in s["structure_id_path"].strip("/").split("/") if x]
        bases = [root_to_base[rid] for rid in path if rid in root_to_base]
        if bases:
            out[s["id"]] = sorted(set(bases))
    return out


def download_donor(donor: int) -> Path:
    """Download a donor's normalized microarray zip if absent (~426 MB)."""
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"normalized_microarray_donor{donor}.zip"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    url = DOWNLOAD.format(fid=DONORS[donor])
    log(f"downloading donor {donor} (~426 MB) ...")
    req = urllib.request.Request(url, headers=UA)
    tmp = dest.with_suffix(".zip.part")
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    tmp.rename(dest)
    log(f"  saved {dest.name} ({dest.stat().st_size/1e6:.0f} MB)")
    return dest


def read_donor(zpath: Path) -> tuple[dict[int, list[str]], list[int], dict[int, list[int]]]:
    """From a donor zip, return (probe_id -> [PACall per sample], sample structure_ids,
    gene_symbol -> [probe_ids]). Reads only the three small members, not expression."""
    with zipfile.ZipFile(zpath) as z:
        names = {n.split("/")[-1]: n for n in z.namelist()}
        # SampleAnnot.csv: one row per sample (same column order as PACall), has structure_id
        with z.open(names["SampleAnnot.csv"]) as fh:
            rows = list(csv.DictReader(io.TextIOWrapper(fh, "utf-8")))
        sample_structs = [int(r["structure_id"]) for r in rows]
        # Probes.csv: probe_id, ..., gene_symbol
        with z.open(names["Probes.csv"]) as fh:
            gene_probes: dict[str, list[int]] = {}
            for r in csv.DictReader(io.TextIOWrapper(fh, "utf-8")):
                gene_probes.setdefault(r["gene_symbol"], []).append(int(r["probe_id"]))
        # PACall.csv: NO header; row = probe_id, then one 0/1 per sample (SampleAnnot order)
        wanted = {p for probes in gene_probes.values() for p in probes}
        pacall: dict[int, list[int]] = {}
        with z.open(names["PACall.csv"]) as fh:
            for row in csv.reader(io.TextIOWrapper(fh, "utf-8")):
                pid = int(row[0])
                if pid in wanted:
                    pacall[pid] = [int(v) for v in row[1:]]
    return pacall, sample_structs, gene_probes


def presence_for_gene(gene: str, donor_data: list[tuple]) -> dict[str, dict]:
    """Aggregate PACall for one gene across donors -> {base: {n_present, n_samples, donors,
    probe}}. Representative probe = the gene's probe with the most detections overall."""
    # tally per (base) using each donor's representative probe for this gene
    agg: dict[str, dict] = {}
    for pacall, sample_structs, gene_probes, struct_bases, donor in donor_data:
        probes = [p for p in gene_probes.get(gene, []) if p in pacall]
        if not probes:
            continue
        rep = max(probes, key=lambda p: sum(pacall[p]))  # most-detected probe this donor
        calls = pacall[rep]
        for j, sid in enumerate(sample_structs):
            for base in struct_bases.get(sid, ()):  # a sample can be in nested bases
                a = agg.setdefault(base, {"n_present": 0, "n_samples": 0,
                                          "donors": set(), "probe": rep})
                a["n_samples"] += 1
                a["donors"].add(donor)
                if calls[j]:
                    a["n_present"] += 1
    return agg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="comma-separated owner ids (targets/receptors) to limit")
    ap.add_argument("--donors", help="comma-separated donor ids (default: all 6)")
    ap.add_argument("--refresh", action="store_true", help="re-download donor zips")
    args = ap.parse_args()

    # receptor genes reuse the GtoPdb map (Phase 2b); targets use TARGET_GENES.
    sys.path.insert(0, str(TOOLS))
    from fetch_gtopdb import RECEPTOR_GENES  # noqa: E402

    owners: dict[str, tuple[str, list[str]]] = {}  # owner id -> (kind, [genes])
    for tid, genes in TARGET_GENES.items():
        owners[tid] = ("target", genes)
    for rid, gene in RECEPTOR_GENES.items():
        owners[rid] = ("receptor", [gene] if isinstance(gene, str) else list(gene))
    if args.only:
        keep = set(args.only.split(","))
        owners = {k: v for k, v in owners.items() if k in keep}
        missing = keep - set(owners)
        if missing:
            log(f"warning: --only ids not in gene maps: {sorted(missing)}")

    donors = [int(d) for d in args.donors.split(",")] if args.donors else list(DONORS)
    if args.refresh:
        for d in donors:
            (RAW / f"normalized_microarray_donor{d}.zip").unlink(missing_ok=True)

    structs = fetch_ontology()
    struct_bases = build_structure_bases(structs)

    # load each donor once (all genes we might need)
    donor_data = []
    for d in donors:
        z = download_donor(d)
        pacall, sample_structs, gene_probes = read_donor(z)
        donor_data.append((pacall, sample_structs, gene_probes, struct_bases, d))
        log(f"donor {d}: {len(sample_structs)} samples, {len(gene_probes)} genes on array")

    # load the current data so we only confirm regions we ALREADY claim (confirm-only)
    recs = [json.loads(l) for l in (REPO / "public/data/receptors.jsonl").read_text().splitlines() if l.strip()]
    rec_regions = {r["id"]: set(r.get("locations") or []) for r in recs}
    meta = json.loads((REPO / "public/data/meta.json").read_text())
    tgt_regions = {k: set(v.get("regions") or [])
                   for k, v in meta["drug_targets"].items() if isinstance(v, dict)}

    PAGES.mkdir(parents=True, exist_ok=True)
    confirmed: list[dict] = []
    page_lines: dict[str, list[str]] = {}
    unconfirmable: list[str] = []
    stats = {"owners": 0, "confirmed": 0, "absent": 0, "nodata": 0}

    for owner, (kind, genes) in sorted(owners.items()):
        claimed = (rec_regions if kind == "receptor" else tgt_regions).get(owner, set())
        if not claimed:
            continue
        stats["owners"] += 1
        # per gene, presence per base
        gene_pres = {g: presence_for_gene(g, donor_data) for g in genes}
        for base in sorted(claimed):
            if base not in BASE_ALLEN:
                unconfirmable.append(f"{owner}/{base}: base not in Allen crosswalk")
                stats["nodata"] += 1
                continue
            # best member gene detecting in this base (fraction >= PRESENT_MIN)
            best = None
            for g in genes:
                a = gene_pres[g].get(base)
                if not a or a["n_samples"] == 0:
                    continue
                frac = a["n_present"] / a["n_samples"]
                if frac >= PRESENT_MIN and (best is None or frac > best[1]):
                    best = (g, frac, a)
            any_samples = any(gene_pres[g].get(base, {}).get("n_samples") for g in genes)
            if best is None:
                if any_samples:
                    stats["absent"] += 1  # Allen sampled it but did not detect -> stays llm
                else:
                    unconfirmable.append(f"{owner}/{base}: 0 Allen samples in region")
                    stats["nodata"] += 1
                continue
            g, frac, a = best
            donors_s = ",".join(str(x) for x in sorted(a["donors"]))
            quote = (f"{g} detected in {base}: probe {a['probe']} PACall present in "
                     f"{a['n_present']}/{a['n_samples']} samples (donors {donors_s})")
            page_lines.setdefault(g, []).append(quote)
            confirmed.append({"owner_kind": kind, "owner": owner, "base": base,
                              "page": g, "quote": quote})
            stats["confirmed"] += 1

    # emit one page per gene (the quote-gate reference text) + the confirm list
    for g, lines in page_lines.items():
        (PAGES / f"{g}.md").write_text("\n".join(sorted(set(lines))) + "\n", encoding="utf-8")
    (ALLEN / "confirmed.json").write_text(json.dumps(confirmed, indent=2) + "\n", encoding="utf-8")

    for u in unconfirmable[:40]:
        log(f"  [nodata] {u}")
    if len(unconfirmable) > 40:
        log(f"  ... +{len(unconfirmable)-40} more un-confirmable (region unsampled/off-atlas)")
    log(f"\nowners with claims: {stats['owners']}; confirmed present: {stats['confirmed']}; "
        f"sampled-but-absent (stays llm): {stats['absent']}; unsampled (stays llm): {stats['nodata']}")
    log(f"wrote {len(page_lines)} gene pages + sources/allen/confirmed.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
