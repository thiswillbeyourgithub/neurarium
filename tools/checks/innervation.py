"""Family 10: innervation coverage per transmitter system.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

from collections import defaultdict

from .common import base_id


def check_innervation(report, meta, structures, projections, receptors):
    """Family 10: per-transmitter-system **innervation coverage** (warns, never errors).

    The dots and the arrows are independent node kinds with wildly different coverage:
    a region lights for a drug because it *expresses* one of the drug's targets
    (``receptor_locations``, sourced in bulk from GtoPdb + Allen), while an arrow needs
    its own hand-found textbook quote. So a region can carry six adrenergic receptors
    with no noradrenergic pathway drawn anywhere near it, and the viewer honestly says
    "acts here" while showing no supply. That reads as a contradiction to a visitor,
    and it is invisible to every other family: nothing is dangling, nothing is
    ungraded, the data is simply thin in one layer.

    So: for each system in ``meta.system_flow_kinds``, compare the regions expressing
    its receptors + non-receptor targets against the regions its projections touch, and
    list the difference. NOT a gate. A gap is usually a missing *pathway* from a source
    nucleus that already exists (raphe -> striatum), occasionally a missing *structure*
    (the nucleus basalis was one: cortical M1-M5 with no cholinergic source at all).
    Glutamate + GABA are deliberately absent from the map (they are not diffuse
    ascending systems), so they never appear here.

    Also runs the mirror question, which catches the opposite hole: a pathway landing
    where no receptor of its own transmitter is recorded means the *expression* layer
    is missing something. A system's own source nuclei are excluded (a nucleus need not
    express the receptors it projects onto)."""
    report.header("10. Innervation coverage (transmitter systems)")
    flow = (meta.get("system_flow_kinds") or {})
    if not flow:
        report.warn("meta.system_flow_kinds is empty; skipping innervation coverage")
        return
    names = {base_id(s["id"]): s.get("base_name") or base_id(s["id"])
             for s in structures}

    # Where each system is expressed: its receptors' locations + its non-receptor
    # targets' regions. A ubiquitous receptor is everywhere by definition, so it can
    # never be part of a gap and would only drown the signal.
    expressed = defaultdict(set)
    owners = defaultdict(lambda: defaultdict(set))
    everywhere = set()   # systems carrying a ubiquitous receptor: expressed in ALL
    for rec in receptors:
        kind = flow.get(rec.get("family"))
        if kind and rec.get("ubiquitous"):
            everywhere.add(kind)
        if not kind or rec.get("ubiquitous"):
            continue
        for base in rec.get("locations") or []:
            expressed[kind].add(base)
            owners[kind][base].add(rec.get("id"))
    for tid, tgt in (meta.get("drug_targets") or {}).items():
        kind = flow.get(tgt.get("system"))
        if not kind or tgt.get("receptor"):   # receptor-backed: counted above
            continue
        for base in tgt.get("regions") or []:
            expressed[kind].add(base)
            owners[kind][base].add(tid)

    # Where each system's pathways go. ``projections`` is already mirror-expanded, so
    # both hemispheres are present; either endpoint counts as innervated.
    reached, sources = defaultdict(set), defaultdict(set)
    for p in projections:
        kind = p.get("kind")
        reached[kind].add(base_id(p.get("from")))
        reached[kind].add(base_id(p.get("to")))
        sources[kind].add(base_id(p.get("from")))

    for kind in sorted(set(flow.values())):
        exp, got = expressed[kind], reached[kind]
        gap = sorted(exp - got, key=lambda b: (-len(owners[kind][b]), b))
        if gap:
            report.warn(
                f"{kind}: {len(gap)}/{len(exp)} region(s) express it but no {kind} "
                f"pathway reaches them: "
                + ", ".join(f"{names.get(b, b)} ({len(owners[kind][b])})" for b in gap))
        else:
            report.ok(f"{kind}: every one of the {len(exp)} region(s) expressing it "
                      "is reached by a pathway")
        # The reverse question asks about EXPRESSION, so it must count the ubiquitous
        # receptors the forward gap deliberately drops: a system with one is expressed
        # everywhere, and can never be landed on blind.
        blind = [] if kind in everywhere else sorted((got - exp) - sources[kind])
        if blind:
            report.warn(f"{kind}: a {kind} pathway lands in {', '.join(blind)} but no "
                        f"{kind} receptor/target is recorded there (expression gap)")

    # A system with receptors but no projection kind at all has no source nucleus in
    # the model. Often correct (opioid / cannabinoid / sigma are local neuromodulators
    # with no single source), but it is also how a genuinely missing source shows up.
    unmapped = defaultdict(set)
    for rec in receptors:
        fam = rec.get("family")
        if fam and fam not in flow and not rec.get("ubiquitous"):
            unmapped[fam] |= set(rec.get("locations") or [])
    if unmapped:
        report.warn(
            "system(s) with receptors but no projection kind at all (no modeled "
            "source nucleus; expected for a local neuromodulator, a real hole for a "
            "diffuse one): "
            + ", ".join(f"{fam} ({len(regs)} region(s))"
                        for fam, regs in sorted(unmapped.items(),
                                                key=lambda kv: -len(kv[1]))))
