"""data_generators.page_links: a clickable url for each cited page no template can build.

Most corpora turn a cited ``page`` into a link with their ``page_url`` template
(``{page}`` -> a PMID, a DailyMed setid). Some cannot: a Wikipedia ``page`` is a lossy
file slug (``agom_latine`` for "Agomélatine"), and a Drugs@FDA page ``NDA005010`` links
to ``ApplNo=005010``. Their fetchers already stamp the exact url in each page's header
(Wikipedia's revision ``permalink:``, Drugs@FDA's ``source:``, a paper's ``doi:``), so this reads it from
there, like :mod:`data_generators.freshness` reads the download date.

Pages are author-side (gitignored ``data_sources/``), so :func:`build_ledger` freezes the
urls into the committed ``tools/generated_cache/page_links.json``
(``python tools/fetch/stamp_fetch_dates.py`` writes both ledgers). ``generate_data.py``
then emits, per corpus, the ``page_urls`` of the pages actually cited
(:func:`attach`), so a clone links them with no ``data_sources/`` at all.

Made with the help of Claude Code.
"""
from __future__ import annotations

import glob
import os
import re
from typing import Any, Iterable

from .freshness import ROOT, _repo, header_field
from .freshness import load_ledger as _load_json_ledger
from .corpora import SOURCE_CORPORA

LEDGER_PATH = os.path.join(ROOT, "tools", "generated_cache", "page_links.json")

# corpus -> (the header line holding its page's own link, the url it makes). A Wikipedia
# page's `source:` is the live article; the `permalink:` pins the revision the quote was
# checked on. A paper links by DOI when it has one (`doi: None` matches nothing), else the
# corpus's PMID `page_url` template still applies.
HEADER_LINKS: dict[str, tuple[re.Pattern, str]] = {
    "wikipedia_pharm": (re.compile(r"\bpermalink:\s*(https?://\S+)"), "{}"),
    "wikipedia_fr": (re.compile(r"\bpermalink:\s*(https?://\S+)"), "{}"),
    "drugsfda": (re.compile(r"^source:\s*(https?://\S+)"), "{}"),
    "europepmc": (re.compile(r"^doi:\s*(10\.\S+)"), "https://doi.org/{}"),
    # A centrally authorised product's RCP is EMA's SmPC PDF, not the ANSM page the
    # corpus template builds (fetch_bdpm_rcp.ema_copies); national ones keep the template.
    "bdpm_rcp": (re.compile(r"^source:\s*(https://www\.ema\.europa\.eu/\S+)"), "{}"),
}


def scan(corpus: str) -> dict[str, str] | None:
    """``{page: url}`` for every stored page of ``corpus`` whose header names one."""
    pages_dir = SOURCE_CORPORA[corpus].get("pages_dir")
    if not pages_dir or not os.path.isdir(_repo(pages_dir)):
        return None
    out = {}
    for path in sorted(glob.glob(os.path.join(_repo(pages_dir), "*.md"))):
        pattern, template = HEADER_LINKS[corpus]
        found = header_field(path, pattern)
        if found:
            out[os.path.basename(path)[:-3]] = template.format(found)
    return out or None


def load_ledger(path: str = LEDGER_PATH) -> dict[str, dict[str, str]]:
    """The committed ``{corpus: {page: url}}`` ledger (``freshness.load_ledger``'s
    reader: {} when absent, a corrupt file raises)."""
    return _load_json_ledger(path)


def build_ledger(prior: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Rescan every :data:`HEADER_LINKS` corpus over ``prior``; a page absent from this
    disk keeps its prior url, so a partial checkout never erases the others."""
    out = {}
    for corpus in sorted(HEADER_LINKS):
        merged = dict(prior.get(corpus) or {})
        merged.update(scan(corpus) or {})
        if merged:
            out[corpus] = dict(sorted(merged.items()))
    return out


def attach(corpora: dict[str, dict], quotes: Iterable[dict[str, Any]],
           ledger: dict[str, dict[str, str]] | None = None) -> dict[str, dict]:
    """``corpora`` with each :data:`HEADER_LINKS` corpus given the ``page_urls`` of its
    cited pages (the ones some quote names). Returns copies; the input is untouched."""
    ledger = load_ledger() if ledger is None else ledger
    cited: dict[str, set[str]] = {}
    for q in quotes:
        if q.get("corpus") in HEADER_LINKS and q.get("page") is not None:
            cited.setdefault(q["corpus"], set()).add(str(q["page"]))
    out = dict(corpora)
    for corpus, pages in cited.items():
        known = ledger.get(corpus) or {}
        urls = {p: known[p] for p in sorted(pages) if p in known}
        if urls and corpus in out:
            out[corpus] = {**out[corpus], "page_urls": urls}
    return out
