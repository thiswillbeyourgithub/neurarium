"""data_generators.freshness: when each cited page of an editable corpus was downloaded.

A book page or a published abstract does not change under a citation. A Wikipedia
article or a live database does: the quote we checked against last year's download may
no longer be on today's page, and the value beside it may have been corrected. So every
page of an **editable** corpus (``SOURCE_CORPORA[c]["editable"]``) carries the date it was
downloaded, the viewer prints it in the source pill's tooltip, and ``check_data.py`` fails
once one is older than :data:`FRESHNESS_MAX_MONTHS` (a refetch is then due).

Where a date comes from (author-side, read by :func:`scan`), one rule per corpus shape:

* a corpus fetched **page by page** (a Wikipedia article, a GtoPdb target, a DailyMed
  label, a BDPM product): the ``fetched:`` / ``fetched_at:`` line its fetcher stamps
  in the page header (:func:`header_date`);
* a corpus downloaded **in bulk** (the PDSP CSV, GtoPdb's interactions.csv, the Allen
  donor zips, the committed CPIC + PharmFreq exports): that one download's date, shared
  by every page cut out of it (:data:`BULK_DATES`).

Those pages are author-side (gitignored ``data_sources/``), so :func:`scan` freezes the
dates into the committed ledger ``tools/generated_cache/fetch_dates.json``
(``python tools/fetch/stamp_fetch_dates.py``). ``generate_data.py`` reads the ledger to stamp
a ``fetched`` date on every emitted source of an editable corpus, so a clone emits and
checks the same dates with no ``data_sources/`` at all.

Made with the help of Claude Code.
"""
from __future__ import annotations

import datetime as _dt
import glob
import json
import os
import re
from typing import Any, Callable

from . import clinpgx, cpic, pharmfreq
from .corpora import SOURCE_CORPORA
from .provenance import corpus_page_path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEDGER_PATH = os.path.join(ROOT, "tools", "generated_cache", "fetch_dates.json")

# A cited page of an editable corpus older than this many months fails check_data.py.
FRESHNESS_MAX_MONTHS = 12

# The header line a fetcher stamps on a page: `fetched: 2026-10-11` (DailyMed, BDPM,
# GtoPdb) or Wikipedia's `fetched_at: 2026-10-11T08:07:13+00:00`. Only the date is kept.
_HEADER_RE = re.compile(r"\bfetched(?:_at)?:\s*(\d{4}-\d{2}-\d{2})")
_HEADER_LINES = 12  # a header sits at the top; never scan a whole article for it
_FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _repo(rel: str) -> str:
    return os.path.join(ROOT, *rel.split("/"))


def _mtime_date(paths: list[str]) -> str | None:
    """The OLDEST modification date among ``paths`` (a download's own timestamp), or None.

    Oldest, because a page cut out of several files is only as fresh as its stalest input.
    """
    stamps = [os.path.getmtime(p) for p in paths if os.path.exists(p)]
    if not stamps:
        return None
    return _dt.date.fromtimestamp(min(stamps)).isoformat()


def _export_fetched(module) -> str | None:
    """A committed JSON export's own ``fetched`` field (CPIC's or ClinPGx's: each
    fetcher writes it), read through the corpus module's ``export_path``."""
    path = module.export_path(ROOT)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("fetched")


def _pharmfreq_date() -> str | None:
    """The oldest date in the PharmFreq export file names (``..._2026-09-09.txt``).

    The export is downloaded by hand and committed, so a clone's mtime would be its
    checkout time; the file name carries the real download date.
    """
    dates = [m.group(1) for f in pharmfreq.export_files(_repo(pharmfreq.EXPORT_DIR))
             if (m := _FILENAME_DATE_RE.search(os.path.basename(f)))]
    return min(dates) if dates else None


# Bulk corpora: corpus -> the date of the one download behind every page it cites.
BULK_DATES: dict[str, Callable[[], str | None]] = {
    "pdsp_ki": lambda: _mtime_date([_repo(SOURCE_CORPORA["pdsp_ki"]["csv"])]),
    "gtopdb_ki": lambda: _mtime_date([_repo("data_sources/gtopdb/interactions.csv")]),
    "b3db": lambda: _mtime_date([_repo("data_sources/b3db/B3DB_classification.tsv")]),
    "allen_ahba": lambda: _mtime_date(
        glob.glob(_repo("data_sources/allen/raw/normalized_microarray_donor*.zip"))),
    "cpic": lambda: _export_fetched(cpic),
    "clinpgx": lambda: _export_fetched(clinpgx),
    "pharmfreq": _pharmfreq_date,
}


def editable_corpora() -> list[str]:
    """Every corpus whose pages can change upstream (``editable: True``), sorted."""
    return sorted(c for c, rec in SOURCE_CORPORA.items() if rec.get("editable"))


def header_field(path: str, pattern: re.Pattern) -> str | None:
    """Group 1 of ``pattern``'s first match in a page file's header, or None."""
    try:
        with open(path, encoding="utf-8") as fh:
            for _, line in zip(range(_HEADER_LINES), fh):
                m = pattern.search(line)
                if m:
                    return m.group(1)
    except OSError:
        return None
    return None


def header_date(path: str) -> str | None:
    """The ``fetched:`` date stamped in a page file's header, or None."""
    return header_field(path, _HEADER_RE)


def cited_page_file(corpus: str, page: Any) -> str | None:
    """The author-side page file a per-page corpus cites, or None for a bulk corpus."""
    path = None if corpus in BULK_DATES else corpus_page_path(corpus, page)
    return str(path) if path else None


def scan(corpus: str) -> str | dict[str, str] | None:
    """Read one editable corpus's download dates off disk (author-side).

    A bulk corpus yields one date string; a per-page corpus a ``{page: date}`` map of
    every stored page that carries a header date. None when nothing is on disk.
    """
    if corpus in BULK_DATES:
        return BULK_DATES[corpus]()
    pages_dir = SOURCE_CORPORA[corpus].get("pages_dir")
    if not pages_dir or not os.path.isdir(_repo(pages_dir)):
        return None
    out = {}
    for path in sorted(glob.glob(os.path.join(_repo(pages_dir), "*.md"))):
        date = header_date(path)
        if date:
            out[os.path.basename(path)[:-3]] = date
    return out or None


def load_ledger(path: str = LEDGER_PATH) -> dict[str, Any]:
    """The committed ``{corpus: date | {page: date}}`` ledger, or {} when absent. A
    corrupt file raises: read as empty, the next stamp run would rewrite it from this
    disk alone and silently drop every corpus this machine does not hold."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def build_ledger(prior: dict[str, Any]) -> dict[str, Any]:
    """Rescan every editable corpus over ``prior``.

    A corpus (or a page) absent from this disk keeps its prior entry, so stamping on a
    machine holding only some corpora never erases the others' dates.
    """
    out = {c: v for c, v in prior.items() if c in editable_corpora()}
    for corpus in editable_corpora():
        found = scan(corpus)
        if found is None:
            continue
        if isinstance(found, dict):
            merged = dict(out.get(corpus) or {}) if isinstance(out.get(corpus), dict) else {}
            merged.update(found)
            found = dict(sorted(merged.items()))
        out[corpus] = found
    return dict(sorted(out.items()))


def fetched_at(ledger: dict[str, Any], corpus: str, page: Any = None) -> str | None:
    """The download date of one cited page (or of a bulk corpus), or None if unknown."""
    entry = ledger.get(corpus)
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and page is not None:
        return entry.get(str(page))
    return None


def _months_before(day: _dt.date, months: int) -> _dt.date:
    """``day`` moved back ``months`` calendar months (clamped to the month's last day)."""
    y, m = divmod(day.year * 12 + day.month - 1 - months, 12)
    m += 1
    for d in (day.day, 30, 29, 28):
        try:
            return _dt.date(y, m, d)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def is_stale(fetched: str, today: _dt.date, months: int = FRESHNESS_MAX_MONTHS) -> bool:
    """True when ``fetched`` (YYYY-MM-DD) is more than ``months`` calendar months old."""
    return _dt.date.fromisoformat(fetched) < _months_before(today, months)


# Loaded once per generation: the emitted `fetched` stamps read this.
LEDGER: dict[str, Any] = load_ledger()
_EDITABLE = frozenset(editable_corpora())


def stamp(source: dict[str, Any]) -> str | None:
    """The ``fetched`` date to emit on one source dict, or None (not editable / unknown)."""
    corpus = source.get("corpus")
    if corpus not in _EDITABLE:
        return None
    return fetched_at(LEDGER, corpus, source.get("page"))
