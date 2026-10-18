"""Family 7: measured-affinity (Ki) coverage (warns, never errors).

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

from lib.drugs_io import is_combination


def check_ki_coverage(report, meta, drugs):
    """Report **measured-affinity (PDSP Ki) coverage** as an eyeball list.

    A binding backed only by a Stahl quote (no Ki) is legitimately sourced, so this
    is NOT a provenance gate: it is the honest complement to the "% sourced" figure,
    surfacing where a *measured* affinity was never looked up (the "we didn't even
    bother to look" case the grade tally cannot see). Each drug carrying at least one
    binding but **zero** Ki across all of them is warned (combo drugs "A + B" are
    Ki-exempt by design and excluded, matching the generator). Recomputed here from
    the emitted drugs, then cross-checked against ``meta.provenance_stats.ki_coverage``
    so the shipped number can never silently drift."""
    report.header("7. Measured-affinity (Ki) coverage")
    ki_drugs = [d for d in drugs if d.get("bindings") and not is_combination(d)]
    bindings = [b for d in ki_drugs for b in d["bindings"]]
    with_ki = [b for b in bindings if b.get("ki")]
    no_ki = sorted(d["id"] for d in ki_drugs
                   if not any(b.get("ki") for b in d["bindings"]))
    pct = round(100 * len(with_ki) / len(bindings)) if bindings else 0

    stat = (meta.get("provenance_stats") or {}).get("ki_coverage") or {}
    for key, want in (("bindings_total", len(bindings)),
                      ("bindings_with_ki", len(with_ki)),
                      ("pct_bindings_with_ki", pct),
                      ("drugs_total", len(ki_drugs)),
                      ("drugs_without_ki", len(no_ki))):
        if stat.get(key) != want:
            report.error(f"provenance_stats.ki_coverage[{key}]={stat.get(key)} "
                         f"!= recomputed ({want})")
    if stat.get("drugs_without_ki_ids") != no_ki:
        report.error("provenance_stats.ki_coverage.drugs_without_ki_ids "
                     "disagrees with recomputed list")

    for did in no_ki:
        report.review(f"drug {did!r}: no measured Ki on any binding "
                    "(sourced by quote only, or unsourced)")
    report.ok(f"{pct}% of {len(bindings)} bindings carry a measured Ki; "
              f"{len(no_ki)}/{len(ki_drugs)} drugs have none")
