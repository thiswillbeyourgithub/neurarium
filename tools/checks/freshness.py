"""Family 13: editable online corpora downloaded recently enough.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import re
from collections import defaultdict
from datetime import date

from data_generators import freshness

from .walks import unknown_stamps


def _editable_sources(node, editable, out):
    """Collect every source dict of an ``editable`` corpus in this (rehydrated) subtree."""
    if isinstance(node, dict):
        if node.get("corpus") in editable:
            out.append(node)
        for value in node.values():
            _editable_sources(value, editable, out)
    elif isinstance(node, list):
        for value in node:
            _editable_sources(value, editable, out)
    return out


def check_freshness(report, meta, collections, today=None, metabolites=(), receptors=()):
    """Family 13: every cited page of an editable online corpus was downloaded recently.

    A book page does not change under a citation; a Wikipedia article or a live database
    does, so a quote checked against an old download may no longer be on today's page.
    Each source of a corpus flagged `editable` in `meta.source_corpora` carries the date
    its page was downloaded (`fetched`, stamped by generate_data.py from the committed
    ledger, see data_generators/freshness.py). An error when a source has no date (the
    ledger does not know its page: run tools/fetch/stamp_fetch_dates.py) or when the date
    is more than FRESHNESS_MAX_MONTHS old (refetch the corpus). Author-side, a page
    whose own header date disagrees with the emitted one means a refetch was not
    restamped. Runs on a clone (no page material needed for the first two), and alone
    via `--only freshness` from the pre-push hook.
    """
    months = freshness.FRESHNESS_MAX_MONTHS
    report.header("13. Freshness (editable corpora downloaded within "
                  f"{months} months)")
    today = today or date.today()
    corpora = meta.get("source_corpora") or {}
    editable = {c for c, rec in corpora.items() if rec.get("editable")}
    if not editable:
        report.error("meta.source_corpora flags no corpus as editable")
        return
    undated, stale, drift = defaultdict(set), defaultdict(dict), defaultdict(set)
    n = 0
    for src in _editable_sources(collections, editable, []):
        n += 1
        corpus, page, fetched = src["corpus"], src.get("page"), src.get("fetched")
        where = "(bulk)" if page is None else str(page)
        if not isinstance(fetched, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fetched):
            undated[corpus].add(where)
            continue
        if freshness.is_stale(fetched, today, months):
            stale[corpus][where] = fetched
        path = freshness.cited_page_file(corpus, page)
        on_disk = freshness.header_date(path) if path else None
        if on_disk and on_disk != fetched:
            drift[corpus].add(f"{where} (page {on_disk}, emitted {fetched})")

    def _some(items):
        items = sorted(items)
        return ", ".join(items[:8]) + (f" (+{len(items) - 8} more)" if len(items) > 8 else "")

    for corpus, pages in sorted(undated.items()):
        report.error(f"{corpus}: {len(pages)} cited page(s) carry no download date "
                     f"(run tools/fetch/stamp_fetch_dates.py, then generate_data.py): "
                     f"{_some(pages)}")
    for corpus, pages in sorted(stale.items()):
        report.error(f"{corpus}: {len(pages)} cited page(s) downloaded more than {months} "
                     f"months ago (oldest {min(pages.values())}); refetch the corpus "
                     f"(see tools/README.md): {_some(pages)}")
    for corpus, pages in sorted(drift.items()):
        report.error(f"{corpus}: {len(pages)} page(s) refetched but not restamped (run "
                     f"tools/fetch/stamp_fetch_dates.py): {_some(pages)}")
    # An UNKNOWN is a search result, and the literature moves: the same age limit.
    drugs = next((c for c in collections if isinstance(c, list) and c
                  and isinstance(c[0], dict) and "bindings" in c[0]), [])
    old_searches = {}
    for where, _k, _c, stamp in unknown_stamps(drugs, metabolites, receptors, meta):
        searched = str(stamp.get("searched"))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", searched) and freshness.is_stale(
                searched, today, months):
            old_searches[where] = searched
    if old_searches:
        report.error(f"{len(old_searches)} UNKNOWN search(es) older than {months} months "
                     f"(oldest {min(old_searches.values())}); rerun the search (see "
                     f"tools/README.md): {_some(old_searches)}")
    if not (undated or stale or drift or old_searches):
        report.ok(f"{n} source(s) across {len(editable)} editable corpora, all downloaded "
                  f"within {months} months")
