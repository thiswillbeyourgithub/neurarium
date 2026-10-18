"""Family 0: the externalized quote table (rehydration + referential integrity).

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

from .common import load_jsonl


def load_quotes(report):
    """Load ``quotes.jsonl`` into a ``quote_id -> quote node`` map.

    Source quotes are emitted once into this side table; each node references
    one by ``quote_id`` (see quote_table.py). A duplicate id is a hard error.
    """
    by_id = {}
    for q in load_jsonl(report, "quotes"):
        qid = q.get("id")
        if not isinstance(qid, str):
            report.error(f"quotes.jsonl: entry without a string id: {q!r}")
            continue
        if qid in by_id:
            report.error(f"quotes.jsonl: duplicate quote id {qid!r}")
        by_id[qid] = q
    return by_id


def rehydrate_quotes(node, by_id, referenced, dangling):
    """Merge each ``{quote_id, ...}`` reference's excerpt back in place.

    Mirrors the viewer's rehydration (js/data.js): copies every field of the quote
    node except its ``id`` onto the reference (so a field the generator adds to the
    quote node needs no edit here) and drops the ``quote_id`` key, so every later
    check sees the original inline source shape.
    Records each referenced id (for the orphan check) and any id with no entry.
    """
    if isinstance(node, dict):
        qid = node.get("quote_id")
        if isinstance(qid, str):
            referenced.add(qid)
            quote = by_id.get(qid)
            if quote is None:
                dangling.append(qid)
            else:
                node.update((k, v) for k, v in quote.items() if k != "id")
            node.pop("quote_id", None)
        for value in node.values():
            rehydrate_quotes(value, by_id, referenced, dangling)
    elif isinstance(node, list):
        for value in node:
            rehydrate_quotes(value, by_id, referenced, dangling)


def check_quotes(report, quotes_by_id, referenced, dangling):
    """Referential integrity of the externalized quote table.

    Every node's ``quote_id`` must resolve to a quote node, and every quote node
    must be referenced by at least one node (no orphans left behind by the
    generator). ``referenced``/``dangling`` are collected during rehydration.
    """
    report.header("0. Quote table")
    if dangling:
        for qid in sorted(set(dangling)):
            report.error(f"quote reference {qid!r} has no entry in quotes.jsonl")
    else:
        report.ok(f"all {len(referenced)} distinct quote references resolve "
                  f"to a quote node")
    orphans = sorted(set(quotes_by_id) - referenced)
    if orphans:
        report.error(f"{len(orphans)} quote(s) in quotes.jsonl are unreferenced "
                     f"(orphans, e.g. {orphans[:3]})")
    else:
        report.ok(f"no orphan quotes ({len(quotes_by_id)} quotes all referenced)")
