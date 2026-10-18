"""Family 12, second half: CPIC's guidance, re-derived from its pinned export.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

from data_generators import cpic

from .common import REPO_ROOT


def check_cpic_guidance(report, meta, drugs):
    """Family 12, second half: CPIC's guidance, re-derived from its pinned export.

    Same mechanism as the profiles above and for a different reason. The quote here IS
    somebody else's sentence, so it could be gated against a page; the point of
    re-deriving instead is that this is the one corpus whose text is **clinical advice**
    ("use 50% of the typical dose"), so every emitted word has to come out of the pinned
    file by code, with no step in between where a sentence could be trimmed, joined or
    paraphrased into saying something CPIC did not.

    Checks the whole shape, not just the quotes: the gene-drug pairs present, each row's
    phenotype / implication / recommendation / classification / assumption, and both of
    its citations. A pair that drifts, or one the emitted data invents, is an error.
    """
    corpora = meta.get("source_corpora") or {}
    if "cpic" not in corpora:
        report.ok("no CPIC corpus to re-derive")
        return
    try:
        want = cpic.guidance_for(cpic.read_export(cpic.export_path(str(REPO_ROOT))))
    except cpic.ExportError as exc:
        report.error(f"cpic: {exc}")
        return

    got = {d["id"]: d["pgx"] for d in drugs if d.get("pgx")}
    for drug in sorted(set(want) | set(got)):
        if drug not in got:
            report.error(f"cpic: the export carries guidance for {drug}, which the "
                         f"emitted drug does not (re-run tools/generate_data.py)")
            continue
        if drug not in want:
            report.error(f"drug {drug} carries CPIC guidance the export does not "
                         f"(re-run tools/fetch/fetch_cpic.py)")
            continue
    n = 0
    for drug in sorted(set(want) & set(got)):
        blocks, emitted = want[drug], got[drug]
        if len(blocks) != len(emitted):
            report.error(f"drug {drug} pgx: {len(emitted)} gene block(s) emitted, "
                         f"{len(blocks)} in the export")
            continue
        for block, out in zip(blocks, emitted):
            ctx = f"drug {drug} pgx {block['gene']}"
            for key in ("gene", "enzyme", "level"):
                if out.get(key) != block[key]:
                    report.error(f"{ctx}: {key} is {out.get(key)!r}, not "
                                 f"{block[key]!r} as the export reads")
            if (out.get("guideline") or {}).get("id") != block["guideline"]["id"]:
                report.error(f"{ctx}: cites a guideline the export does not")
            if len(out.get("rows") or []) != len(block["rows"]):
                report.error(f"{ctx}: {len(out.get('rows') or [])} row(s) emitted, "
                             f"{len(block['rows'])} in the export")
                continue
            for row, wrow in zip(out["rows"], block["rows"]):
                rctx = f"{ctx} {wrow['phenotype']}"
                for key in ("phenotype", "implication", "recommendation",
                            "classification"):
                    if row.get(key) != wrow[key]:
                        report.error(f"{rctx}: {key} is not what the export reads "
                                     f"(re-run tools/fetch/fetch_cpic.py)")
                if (row.get("assumes") or {}) != (wrow.get("assumes") or {}):
                    report.error(f"{rctx}: the co-dosed-gene assumption differs from "
                                 f"the export's")
                # Two citations per node: CPIC's implication, then its recommendation.
                # Both quotes must be the export's own strings, verbatim.
                srcs = row.get("sources") or []
                quotes = [s.get("quote") for s in srcs]
                if quotes != [wrow["implication"], wrow["recommendation"]]:
                    report.error(f"{rctx}: its {len(srcs)} citation(s) do not quote the "
                                 f"export's implication then its recommendation")
                    continue
                for i, src in enumerate(srcs):
                    if src.get("page") != block["guideline"]["id"]:
                        report.error(f"{rctx} sources[{i}]: page {src.get('page')!r} is "
                                     f"not the guideline id "
                                     f"{block['guideline']['id']!r}")
                    else:
                        n += 1
    n += check_cpic_enzyme_claims(report, want, drugs)
    check_cpic_enzyme_coverage(report, want, drugs)
    report.ok(f"{n} CPIC guidance quote(s) re-derived from the pinned export, "
              f"exact match")


def check_cpic_enzyme_coverage(report, want, drugs):
    """A gene CPIC doses a drug on, that the drug's enzyme list does not carry.

    Not an error, and deliberately not one: it means no corpus here states the route,
    which is a hole in the sources and not a mistake in the data. Flagging it is still
    worth a line, because the panel then shows a reader advice about their CYP2C19
    speed over an Enzymes section that never mentions CYP2C19, and because the enzyme
    list feeds the derived drug-drug edges, so a missing route quietly removes
    interactions nobody sees go missing.

    Clomipramine was exactly that case (fixed in 3.93.1: 11 interaction edges appeared
    with the row). This exists so the next one is reported rather than noticed by eye,
    since either side can produce it: a CPIC refresh adding a pair, or a CYP fetcher
    re-run dropping a row.
    """
    by_id = {d["id"]: d for d in drugs}
    for drug in sorted(want):
        doc = by_id.get(drug)
        if doc is None:
            continue
        have = {e["enzyme"] for e in doc.get("enzymes") or []}
        for block in want[drug]:
            if block["enzyme"] in have:
                continue
            report.warn(f"drug {drug}: CPIC doses it on {block['gene']}, which its "
                        f"enzyme list does not carry, so the guidance sits over a "
                        f"section that never names the gene (no corpus here states "
                        f"the route; see docs/SOURCING_GAPS.md)")


def check_cpic_enzyme_claims(report, want, drugs) -> int:
    """The enzyme routes CPIC's own wording states (see ``cpic.enzyme_claims_for``).

    An enzyme row sourced to CPIC is the one place this corpus is read for something
    other than guidance, so it gets the same treatment: re-derived from the export and
    compared. The gate runs both ways. A row the re-derivation does not produce is an
    error (it would mean we asserted a metabolic route CPIC never phrased), and a claim
    the re-derivation produces that no drug carries is checked only for its quote,
    because another corpus legitimately owns that (enzyme, role) pair already.
    """
    claims = {(drug, r["enzyme"]): r["sources"][0]["quote"]
              for drug, rows in cpic.enzyme_claims_for(want).items() for r in rows}
    n = 0
    for drug in drugs:
        for row in drug.get("enzymes") or []:
            src = (row.get("sources") or [{}])[0]
            if src.get("corpus") != "cpic":
                continue  # another corpus owns this row
            quote = src.get("quote")
            ctx = f"drug {drug['id']} enzymes[{row['enzyme']}]"
            if claims.get((drug["id"], row["enzyme"])) != quote:
                report.error(f"{ctx}: cites a CPIC sentence the export does not state "
                             f"for this pair (re-run tools/fetch/fetch_cpic.py)")
            elif row.get("role") != "substrate":
                report.error(f"{ctx}: CPIC's wording states a route, so the role can "
                             f"only be 'substrate', not {row.get('role')!r}")
            else:
                n += 1
    return n
