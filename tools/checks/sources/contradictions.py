"""Family 5: the curated "contradicted" table, keyed by citation site (any node kind).

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

from sourcing import citation_site as CS


def check_contradictions(gate, ki, meta, contradictions, *, drugs, metabolites,
                         receptors, projections, circuits, groups, structures):
    """Every site must still name exactly one emitted node, that node must wear the
    badge, and its denial quotes are gated here when no per-kind walk reached it."""
    report = gate.report
    nodes, ambiguous = CS.node_index(
        drugs=drugs, metabolites=metabolites, receptors=receptors,
        targets=meta.get("drug_targets") or {}, projections=projections,
        circuits=circuits, groups=groups, structures=structures)
    for site in contradictions:
        node = None if site in ambiguous else nodes.get(site)
        if node is None:
            report.error(f"CONTRADICTIONS[{site!r}]: names "
                         f"{'two emitted nodes' if site in ambiguous else 'no emitted node'}"
                         f" (gone, renamed, or a flat facet): the contradiction marks "
                         f"nothing")
            continue
        if not any(u.get("kind") == "contradicted" for u in node.get("uncertainty") or []):
            report.error(f"CONTRADICTIONS[{site!r}]: the node carries no contradicted "
                         f"bullet (stale data/: rerun tools/generate_data.py)")
        if id(node) not in gate.gated:
            gate.check_uncertainty(site, node)
            ki.check_bullet_ki(site, node)
