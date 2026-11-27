"""Large-scale networks (BETA): every network names emitted functional areas and
structures, covers each member area's structures, and has unique ids.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md); the network
quotes themselves are gated with every other quote by the quote-table sweep.
"""


def check_networks(report, structures, areas, networks):
    report.header("Large-scale networks (beta)")
    sids = {s.get("id") for s in structures}
    area_by_id = {a.get("id"): a for a in areas}
    seen = set()
    for n in networks:
        nid = n.get("id")
        if nid in seen:
            report.error(f"network {nid}: duplicate id")
        seen.add(nid)
        if not n.get("areas"):
            report.error(f"network {nid}: no functional area")
        members = set(n.get("structures") or [])
        for aid in n.get("areas") or []:
            area = area_by_id.get(aid)
            if area is None:
                report.error(f"network {nid}: functional area {aid!r} is not emitted")
            elif not set(area.get("structures") or []) <= members:
                report.error(f"network {nid}: misses the structures of area {aid!r}")
        for sid in members - sids:
            report.error(f"network {nid}: structure {sid!r} is not emitted")
        if n.get("wikipedia") and not n.get("wikipedia_provenance"):
            report.error(f"network {nid}: wikipedia link without a grade")
    report.ok(f"{len(networks)} network(s), "
              f"{sum(1 for n in networks if n.get('sources'))} sourced")
