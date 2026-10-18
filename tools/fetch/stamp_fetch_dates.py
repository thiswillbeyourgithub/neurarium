#!/usr/bin/env python
"""Freeze the editable corpora's download dates into the committed ledger.

Reads every editable corpus's author-side pages (or its bulk download) through
``data_generators.freshness.scan`` and writes ``tools/generated_cache/fetch_dates.json``,
which ``generate_data.py`` stamps onto each emitted source. Run it after any refetch, then
``generate_data.py``; a cited page the ledger does not know fails ``check_data.py``.
A corpus absent from this disk keeps its prior dates. It also writes
``tools/generated_cache/page_links.json`` (``data_generators.page_links``): the url each
Wikipedia / Drugs@FDA page header names, so a cited page is a clickable link on a clone.
Stdlib only, offline.

    python tools/fetch/stamp_fetch_dates.py            # write the ledger
    python tools/fetch/stamp_fetch_dates.py --dry-run  # report only

Made with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_generators import freshness, page_links  # noqa: E402  (path shim above)
from lib.io_atomic import atomic_write_json  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    ledger = freshness.build_ledger(freshness.load_ledger())
    today = datetime.date.today()
    for corpus in freshness.editable_corpora():
        entry = ledger.get(corpus)
        dates = [entry] if isinstance(entry, str) else sorted((entry or {}).values())
        if not dates:
            print(f"  {corpus:<16} no date on disk or in the ledger")
            continue
        stale = sum(freshness.is_stale(d, today) for d in dates)
        span = dates[0] if dates[0] == dates[-1] else f"{dates[0]} .. {dates[-1]}"
        pages = "bulk" if isinstance(entry, str) else f"{len(dates)} pages"
        print(f"  {corpus:<16} {pages:<10} {span}" + (f"  ({stale} stale)" if stale else ""))
    links = page_links.build_ledger(page_links.load_ledger())
    for corpus, urls in links.items():
        print(f"  {corpus:<16} {len(urls)} page links")
    if args.dry_run:
        return 0
    for path, data in ((freshness.LEDGER_PATH, ledger), (page_links.LEDGER_PATH, links)):
        atomic_write_json(path, data, indent=1, sort_keys=True, ensure_ascii=True)
        print(f"wrote {Path(path).relative_to(freshness.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
