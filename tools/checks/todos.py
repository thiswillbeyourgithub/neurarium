"""Family 3: stray ``TODO`` placeholders.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import re

from .common import walk_strings


# A path like "...sources[3].url" (a citation) is a source url: its TODO is the
# known backlog, reported on its own. Anything else is a stray TODO.
_SOURCE_URL_RE = re.compile(r"\.sources\[\d+\]\.url$")


def check_todos(report, meta, structures, projections, circuits,
                projection_groups, receptors, drugs):
    report.header("3. TODOs")

    def record_id(label, record):
        if label == "projection":
            return f"{record.get('from')}->{record.get('to')}"
        return record.get("id")

    scan = []
    for label, items in (("structure", structures), ("projection", projections),
                         ("circuit", circuits), ("projection group", projection_groups),
                         ("receptor", receptors),
                         ("drug", drugs)):
        for record in items:
            scan.append((f"{label}:{record_id(label, record)}", record))
    scan.append(("meta", meta))

    source_todos = []
    other_todos = []
    for base, record in scan:
        for path, value in walk_strings(record, base):
            if "TODO" not in value:
                continue
            (source_todos if _SOURCE_URL_RE.search(path) else other_todos).append(path)

    # A focusable target with no wikipedia surfaces as a TODO pill in showTarget;
    # surface it here as a non-source TODO too (a non-receptor target is focusable
    # once it has regions to light).
    missing_wiki = [
        key for key, target in meta.get("drug_targets", {}).items()
        if target.get("receptor") is None and not target.get("wikipedia")
        and target.get("regions")
    ]

    # --- non-source TODOs (warned, listed individually) ---
    if not other_todos and not missing_wiki:
        report.ok("no stray TODOs outside of source urls")
    else:
        for path in other_todos:
            report.warn(f"stray TODO placeholder at {path}")
        for key in missing_wiki:
            report.warn(f"target {key}: no wikipedia url (shows a TODO pill)")

    # --- corpus links ---
    # Per-claim sources are quote-level ``{corpus, page, quote}`` and carry no url of
    # their own: the viewer links a cited page from ``meta.source_corpora``, trying the
    # corpus's ``page_urls[page]``, then its ``page_url`` template, then its ``url``
    # landing page (a book's DOI or ISBN). So every corpus needs a real ``url``, and any
    # link it does carry must be one.
    def is_link(u):
        return str(u).startswith(("http://", "https://"))

    no_link = []
    for cid, corpus in (meta.get("source_corpora", {}) or {}).items():
        if not isinstance(corpus, dict):
            continue
        url = corpus.get("url")
        if url is None:
            no_link.append(cid)
        elif not is_link(url):
            report.error(f"source_corpora.{cid}.url is not a real link: {url!r}")
        bad = [p for p, u in (corpus.get("page_urls") or {}).items() if not is_link(u)]
        if bad:
            report.error(f"source_corpora.{cid}.page_urls: not a real link for "
                         f"{len(bad)} page(s), e.g. {bad[0]!r}")
    if no_link:
        report.warn(f"{len(no_link)} source corpus/corpora carry no url, so their "
                    f"citations are not clickable: {', '.join(sorted(no_link))}")
    else:
        report.ok("every source corpus carries a real url")
