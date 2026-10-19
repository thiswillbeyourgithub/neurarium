"""Family 12, last part: ClinPGx variant annotations, re-derived from their export.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

from data_generators import clinpgx
from data_generators.provenance_stats import own_targets

from .common import REPO_ROOT


def check_clinpgx_variants(report, meta, receptors):
    """Family 12, last part: ClinPGx's variant annotations, re-derived from their export.

    Every ``receptor_variant`` node is rebuilt from the pinned export by the generator's
    own reader (``clinpgx.variant_nodes``) and must match the emitted one field for
    field, its quotes included: ClinPGx's sentences are copied by code, so no step may
    trim or reword one. An export row no owner carries (an owner id the emitted data
    does not have) and an emitted node the export does not hold are both errors.
    """
    corpora = meta.get("source_corpora") or {}
    if "clinpgx" not in corpora:
        report.ok("no ClinPGx corpus to re-derive")
        return
    try:
        want = clinpgx.variant_nodes(
            clinpgx.read_export(clinpgx.export_path(str(REPO_ROOT))))
    except clinpgx.ExportError as exc:
        report.error(f"clinpgx: {exc}")
        return
    got = {("receptor", r["id"]): r.get("variants") or [] for r in receptors}
    got.update((("target", tid), t.get("variants") or [])
               for tid, t in own_targets(meta.get("drug_targets") or {}).items())
    keys = ("annotation", "variant", "genes", "level", "categories", "drugs",
            "drug_names", "phenotypes", "pmids", "genotypes", "population", "url")
    n = 0
    for owner in sorted(set(want) | {k for k, v in got.items() if v}):
        ctx = f"{owner[0]} {owner[1]} variants"
        if owner not in got:
            report.error(f"{ctx}: the export holds {len(want[owner])} annotation(s) for "
                         f"an owner the emitted data does not have (fix genes.GENE_OWNERS)")
            continue
        wants, emitted = want.get(owner, []), got[owner]
        if [w["annotation"] for w in wants] != [e.get("annotation") for e in emitted]:
            report.error(f"{ctx}: emitted annotations are not the export's (re-run "
                         f"tools/generate_data.py)")
            continue
        for w, e in zip(wants, emitted):
            for key in keys:
                if e.get(key) != w.get(key):
                    report.error(f"{ctx} {w['annotation']}: {key} is {e.get(key)!r}, not "
                                 f"{w.get(key)!r} as the export reads")
            quotes = [s.get("quote") for s in e.get("sources") or []]
            if quotes != [s["quote"] for s in w["sources"]]:
                report.error(f"{ctx} {w['annotation']}: its citations do not quote the "
                             f"export's genotype sentences verbatim")
                continue
            for i, src in enumerate(e["sources"]):
                if src.get("corpus") != "clinpgx" or src.get("page") != w["annotation"]:
                    report.error(f"{ctx} {w['annotation']} sources[{i}]: not cited to "
                                 f"clinpgx page {w['annotation']!r}")
                else:
                    n += 1
    report.ok(f"{n} ClinPGx variant quote(s) re-derived from the pinned export, "
              f"exact match")
