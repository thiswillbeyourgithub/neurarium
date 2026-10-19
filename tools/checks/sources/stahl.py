"""Family 5: every Stahl quote on a drug comes off that drug's own monograph.

The other half of "is this quote about the drug we are talking about?": a Stahl
quote must come from a page inside that drug's OWN monograph. The book is one
monograph per drug over a contiguous page span, so a page outside the span is a
quote read off a neighbour's entry, which no amount of verbatim matching would
catch (the sentence really is on the page, just not that drug's page).

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import re

from lib import stahl_index  # (the one INDEX.md reader)
from lib.text_fold import alnum_key


def stahl_monograph_ranges():
    """``folded drug name -> (first page, last page)`` from Stahl's generated INDEX.md.

    ``None`` when the author-side book tree is absent (a plain clone), so the
    caller skips the check exactly like the verbatim-quote gate does."""
    ranges = stahl_index.ranges(alnum_key, missing_ok=True)
    return ranges or None


def stahl_monograph_check(drug, ranges):
    """``(pages, span, stray)`` for one drug against the monograph index.

    ``pages`` is every Stahl page it quotes, ``span`` its own monograph (``None``
    when the index has no row under its name or any of its brands, so the caller
    reports it as unrangeable rather than as a violation), and ``stray`` the
    quoted pages that fall outside that span."""
    pages = sorted(quote_pages(drug, "stahl", set()))
    names = [drug.get("name") or ""]
    names += re.split(r"\s*\+\s*", names[0])          # a combo names both halves
    names += [b for b in (drug.get("brands") or []) if isinstance(b, str)]
    span = next((ranges[k] for k in map(alnum_key, names) if k in ranges), None)
    if span is None:
        return pages, None, []
    return pages, span, [p for p in pages if not span[0] <= p <= span[1]]


def quote_pages(node, corpus, out):
    """Collect every page a ``corpus`` quote in this subtree cites (sources are
    rehydrated in place, so a plain recursive walk sees them all)."""
    if isinstance(node, dict):
        if node.get("corpus") == corpus and node.get("page") is not None:
            out.add(node["page"])
        for value in node.values():
            quote_pages(value, corpus, out)
    elif isinstance(node, list):
        for value in node:
            quote_pages(value, corpus, out)
    return out


def check_stahl_monographs(report, drugs, headings):
    """Every Stahl quote on a drug must come off that drug's own monograph pages, and
    every Stahl heading trail must open with the monograph its page falls in."""
    ranges = stahl_monograph_ranges()
    if ranges is None:
        report.warn("Stahl INDEX.md absent (author-only material); skipped the "
                    "check that each drug's quotes come from its own monograph")
        return
    before_range = report.errors
    checked = unindexed = 0
    for drug in drugs:
        pages, span, stray = stahl_monograph_check(drug, ranges)
        if not pages:
            continue
        if span is None:
            unindexed += 1
            report.warn(f"drug {drug.get('id')} ({drug.get('name')}) cites Stahl "
                        f"pages {pages} but has no INDEX.md monograph; "
                        f"its quotes cannot be range-checked")
            continue
        checked += 1
        if stray:
            report.error(f"drug {drug.get('id')}: Stahl quote(s) from page(s) "
                         f"{stray}, outside its own monograph (pages "
                         f"{span[0]}-{span[1]}). A quote read off a neighbouring "
                         f"drug's entry is verbatim on the page and still says "
                         f"nothing about this drug")
    if report.errors == before_range:
        report.ok(f"all Stahl quotes on {checked} drugs come from that drug's own "
                  f"monograph" + (f" ({unindexed} unindexed)" if unindexed else ""))

    # A Stahl heading trail LEADS with the monograph title, which is checkable
    # offline against the same INDEX.md ranges: the drug it names must be the
    # monograph the cited page actually falls in. That is what catches a
    # hand-edited or stale generated_cache entry, which would otherwise print a
    # confident and wrong breadcrumb over a real quote.
    before_head = report.errors
    stahl_headings = 0
    for ctx, corpus, page, trail in headings:
        if corpus != "stahl" or page is None or not isinstance(trail, list):
            continue
        stahl_headings += 1
        span = ranges.get(alnum_key(trail[0])) if trail else None
        if span is None:
            report.error(f"{ctx}: heading trail leads with {trail[:1]!r}, which "
                         f"is no INDEX.md monograph. A Stahl trail must open "
                         f"with the drug whose monograph the page falls in")
        elif not (span[0] <= page <= span[1]):
            report.error(f"{ctx}: heading says the quote is in {trail[0]!r}'s "
                         f"monograph (pages {span[0]}-{span[1]}) but it cites "
                         f"p.{page}. Re-run tools/fetch/fetch_quote_headers.py")
    if report.errors == before_head:
        report.ok(f"all {stahl_headings} Stahl heading trails open with the "
                  f"monograph their page falls in" if stahl_headings
                  else "no derived Stahl headings yet "
                       "(run tools/fetch/fetch_quote_headers.py)")
