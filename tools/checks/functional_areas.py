"""Functional areas (BETA): every area names emitted structures, ids are unique, and
the wikipedia reference carries a grade.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md); the area quotes
themselves are gated with every other quote by the quote-table sweep.
"""


def check_functional_areas(report, structures, areas):
    report.header("Functional areas (beta)")
    ids = {s.get("id") for s in structures}
    seen = set()
    for a in areas:
        aid = a.get("id")
        if aid in seen:
            report.error(f"functional area {aid}: duplicate id")
        seen.add(aid)
        for sid in a.get("structures") or []:
            if sid not in ids:
                report.error(f"functional area {aid}: structure {sid!r} is not emitted")
        if not a.get("structures"):
            report.error(f"functional area {aid}: no structure")
        if a.get("wikipedia") and not a.get("wikipedia_provenance"):
            report.error(f"functional area {aid}: wikipedia link without a grade")
    drawn = sum(1 for a in areas if a.get("own_shape"))
    report.ok(f"{len(areas)} functional area(s), {drawn} with their own shape, "
              f"{sum(1 for a in areas if a.get('sources'))} sourced")
