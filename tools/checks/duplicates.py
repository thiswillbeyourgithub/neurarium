"""Family 1: duplicate ids, keys and display names per collection.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

from collections import Counter, defaultdict

from data_generators import node_id

from .common import display_name, normalize


def check_id_collection(report, label, items, id_key="id", name_key="name"):
    """Exact + normalized duplicate ids (errors) and normalized duplicate display
    names (warnings) within one id-bearing collection."""
    ids = [item.get(id_key) for item in items]

    exact = {value: count for value, count in Counter(ids).items() if count > 1}
    for value, count in sorted(exact.items(), key=lambda kv: str(kv[0])):
        report.error(f"{label}: id {value!r} appears {count} times")

    by_norm_id = defaultdict(set)
    for value in ids:
        by_norm_id[normalize(value)].add(value)
    near = [raws for raws in by_norm_id.values() if len(raws) > 1]
    for raws in sorted(near, key=lambda s: sorted(map(str, s))):
        report.error(f"{label}: ids collide once normalized: {sorted(raws)}")

    by_norm_name = defaultdict(set)
    for item in items:
        name = display_name(item.get(name_key))
        if name:
            by_norm_name[normalize(name)].add(item.get(id_key))
    name_dups = {(nk, frozenset(idset)) for nk, idset in by_norm_name.items() if len(idset) > 1}
    for nk, idset in sorted(name_dups, key=lambda kv: kv[0]):
        report.warn(f"{label}: ids {sorted(idset)} share normalized name {nk!r}")

    # An id becomes a file name and a URL segment (render_api, the viewer's ?params).
    malformed = sorted({str(v) for v in ids if not node_id.is_node_id(v)})
    for value in malformed:
        report.error(f"{label}: id {value!r} is not {node_id.NODE_ID_RE.pattern}")

    if not exact and not near and not name_dups and not malformed:
        report.ok(f"{label}: {len(items)} entries, no duplicate ids or names")


def check_projection_dups(report, projections):
    pairs = Counter((p.get("from"), p.get("to")) for p in projections)
    dups = {pair: count for pair, count in pairs.items() if count > 1}
    for (src, dst), count in sorted(dups.items(), key=lambda kv: str(kv[0])):
        report.error(f"projections: {src} -> {dst} defined {count} times")
    if not dups:
        report.ok(f"projections: {len(projections)} pathways, no duplicate from->to")


def check_binding_dups(report, drugs):
    """A drug may list one target twice (a dual mechanism: amphetamine both blocks DAT
    reuptake and releases through it), but never the same (target, action) twice: that
    is a dual pair one bulk edit collapsed onto a single action, losing the other."""
    n = 0
    for drug in drugs:
        pairs = Counter((b.get("target"), b.get("action")) for b in drug.get("bindings", []))
        for (target, action), count in sorted(pairs.items(), key=str):
            if count > 1:
                n += 1
                report.error(f"drug {drug.get('id')}: binding {target}/{action} listed "
                             f"{count} times (a collapsed dual-mechanism pair?)")
    if not n:
        report.ok("drug bindings: no (target, action) pair listed twice")


def check_duplicates(report, meta, structures, projections, circuits,
                     projection_groups, receptors, drugs, metabolites=()):
    report.header("1. Duplicates (exact + normalized)")
    check_id_collection(report, "structures", structures)
    check_id_collection(report, "receptors", receptors)
    check_id_collection(report, "drugs", drugs)
    check_id_collection(report, "metabolites", metabolites)
    check_id_collection(report, "circuits", circuits)
    check_id_collection(report, "projection groups", projection_groups)
    # drug_targets is a dict in meta; reshape to id-bearing records to reuse the
    # same machinery (the key is the id, the value carries the {en,fr} name).
    targets = [dict(value, id=key) for key, value in meta.get("drug_targets", {}).items()]
    check_id_collection(report, "targets", targets)
    check_projection_dups(report, projections)
    check_binding_dups(report, drugs)
