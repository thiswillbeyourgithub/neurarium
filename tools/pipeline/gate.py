"""The applier's quote gate, written once: re-find a picked sentence on its stored page.

Every applier (step three of fetch -> judge -> apply -> recheck) ends the same way: the
quote it is about to write must still be on the stored page it cites, compared under
``lib.quote_match.normalize_for_match`` so "accepted here" means "passes check_data". This
module holds that last step plus the tally every applier prints:

* :class:`PageGate`: the normalized page text per ``(corpus, page)``, read once and
  cached, and :meth:`PageGate.on_page` / :meth:`PageGate.sources` on top of it. Pages are
  read from a ``{corpus: page directory}`` map (``<dir>/<page>.md``), or through a
  ``read(corpus, page)`` callable a caller (or a test) supplies.
* :class:`Tally`: the ``stats`` counter and ``rejected`` log, one ``reject`` call each.

Documented exception: ``tools/sourcing/apply_brand_names.py`` keeps its own page reads,
since its brand dedup key (``brand_key``) folds accents differently from
``normalize_for_match`` and its BDPM mode gates only a page's header line.

Example::

    >>> gate = PageGate(read=lambda corpus, page: "drug x blocks d2")
    >>> gate.on_page("wikipedia_pharm", "x", "Drug X blocks D2.")
    True

Built with the help of Claude Code.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from lib.quote_match import normalize_for_match  # noqa: E402 (the gate's one normalizer)
from page_file import page_file  # noqa: E402 (refuses a path-like page)
from pipeline.judged import resolve_all  # noqa: E402


def registry_pages() -> dict[str, Path]:
    """``{corpus: absolute page directory}`` for every registered corpus with a page tree.

    The ``pages`` map for a gate that may meet any corpus (a hand-curated table citing
    Stahl next to Wikipedia, say). It resolves exactly as
    ``data_generators.provenance.corpus_page_path`` does: ``SOURCE_CORPORA[c]["pages_dir"]``
    under the repo root, a corpus with no ``pages_dir`` (a CSV corpus) left out.
    """
    # Imported here, so a gate over one known corpus never loads the corpus registry.
    from data_generators.provenance import SOURCE_CORPORA

    return {c: TOOLS.parent / e["pages_dir"] for c, e in SOURCE_CORPORA.items()
            if e.get("pages_dir")}


class PageGate:
    """Re-finds picked candidates on their stored pages, caching each page's text.

    ``pages`` maps a corpus to its page directory (page file = ``<page>.md``). ``read``,
    when given instead, is ``(corpus, page) -> normalized text or None`` (a test's fake
    store, or a corpus whose pages live elsewhere).
    """

    def __init__(self, pages: dict[str, Path] | None = None, read=None):
        self.pages = pages or {}
        self._read = read
        self._text: dict[tuple, str | None] = {}

    def _load(self, corpus: str, page) -> str | None:
        if self._read is not None:
            return self._read(corpus, page)
        path = page_file(self.pages.get(corpus), page)
        return (normalize_for_match(path.read_text("utf-8", errors="replace"))
                if path and path.exists() else None)

    def text(self, corpus: str, page) -> str | None:
        """The stored page, normalized, or None when the corpus has no such page file."""
        key = (corpus, str(page))
        if key not in self._text:
            self._text[key] = self._load(corpus, page)
        return self._text[key]

    def on_page(self, corpus: str, page, line: str) -> bool:
        body = self.text(corpus, page)
        return bool(body) and normalize_for_match(line) in body

    def sources(self, cands: list[dict], picks, what: str,
                misses: list[str]) -> list[dict] | None:
        """The ``{corpus, page, quote, provenance}`` sources for ``picks`` (``{index, qid}``
        refs, see ``pipeline.judged``), else None.

        All or nothing: one unresolvable pick or one quote missing from its page drops every
        pick for ``what`` (and records why in ``misses``), so a half-checked set never lands.
        """
        picked, why = resolve_all(cands, picks)
        if why:
            misses.append(f"{what}: {why}")
            return None
        out = []
        for c in picked:
            if not self.on_page(c["corpus"], c["page"], c["line"]):
                misses.append(f"{what}: quote not on {c['corpus']}/{c['page']}: "
                              f"{c['line'][:80]!r}")
                return None
            src = {"corpus": c["corpus"], "page": c["page"], "quote": c["line"],
                   "provenance": "verified"}
            if c.get("species"):  # a corpus recording its assay species (GtoPdb #23)
                src["species"] = c["species"]
            out.append(src)
        return out


class Tally:
    """An applier's ``stats`` counter and ``rejected`` log (one line per refused row)."""

    def __init__(self) -> None:
        self.stats: collections.Counter = collections.Counter()
        self.rejected: list[str] = []

    def reject(self, why: str, detail: str) -> None:
        self.stats[f"rejected: {why}"] += 1
        self.rejected.append(f"[{why}] {detail}")
