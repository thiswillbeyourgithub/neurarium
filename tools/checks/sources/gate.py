"""Family 5's one quote gate: the per-source check every node walk feeds.

``QuoteGate`` holds the state one run of family 5 shares across the walks (the page
cache, the corpora whose pages are absent, the derived headings collected for the
later passes, the unjudged LLM picks, the nodes whose bullets were already gated), so
each walk in this package is a plain loop over its own node kind.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import re
from pathlib import Path

# The pathway per-claim word tests, imported for the same reason: family 5 re-runs the
# very test that graded a transmitter/sign sub-claim, so a hand-edited or stale ``claims``
# block (a source that does not name what it is cited for) fails instead of shipping.
from data_generators.quotes.attestation import BASE_GRADE as CLAIM_BASE_GRADE
from data_generators.quotes.attestation import pattern_for as claim_pattern
from lib.page_file import page_file, read_page_file  # (refuses a path-like page)
from lib.quote_match import normalize_for_match

from ..common import REPO_ROOT

# A normalized quote shorter than this risks an incidental substring match (a few
# common words appearing on the page by chance), so a too-short quote is warned
# about even when it "matches".
_MIN_QUOTE_CHARS = 16

# A page's Markdown heading line ("## Interactions") opens another section: a quote
# running across one glues two sections' sentences into one claim, and still matches
# verbatim once whitespace is normalized, so it is refused on its own.
_HEADING_IN_QUOTE = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]")


def spans_heading(quote):
    """Whether ``quote`` runs across a Markdown heading line of its page."""
    return bool(_HEADING_IN_QUOTE.search(quote or ""))


class QuoteGate:
    """The quote-level checks of family 5, plus the state they accumulate."""

    def __init__(self, report, meta, root=REPO_ROOT):
        self.report = report
        self.root = Path(root)  # where each corpus's ``pages_dir`` is resolved
        self.corpora = meta.get("source_corpora", {})
        # The closed vocabulary the "uncertain" bullets draw their reason kinds from,
        # read from the data rather than restated here so the two cannot drift.
        self.reason_kinds = set(meta.get("uncertainty_reasons", {}))

        # pipeline key -> its chain of custody (see provenance.QUOTE_PIPELINES). The
        # rule below is read OFF the chains rather than restated as a list of key names:
        # a pipeline in which a model chose the sentence but no model ever judged it is
        # the violation, whatever it ends up being called.
        self.pipelines = meta.get("quote_pipelines", {})
        self.unjudged_pipelines = {k for k, steps in self.pipelines.items()
                                   if "extract_llm" in steps and "judge_llm" not in steps}
        self.unjudged = []

        self.page_cache = {}       # (corpus, page) -> normalized page text or None
        self.skipped_corpora = set()
        self.n_checked = 0
        # Every source carrying a derived book heading, checked in one pass afterwards
        # (collected here so the whole dataset is walked once, not twice).
        self.headings = []
        self.gated = set()         # id() of every node whose bullets were gated

    def page_text(self, corpus, page):
        """The cited page, normalized; ``None`` when the corpus's page tree is absent
        (a clone: skip + warn), ``""`` when the tree is present but the page file is
        missing or the page id is path-like (an error, never a silent pass)."""
        key = (corpus, page)
        if key not in self.page_cache:
            pages_dir = (self.corpora.get(corpus) or {}).get("pages_dir")
            tree = self.root / pages_dir if pages_dir else None
            text = None
            if tree is not None and tree.is_dir():
                md = page_file(tree, page)
                text = (normalize_for_match(read_page_file(md))
                        if md is not None and md.is_file() else "")
            self.page_cache[key] = text
        return self.page_cache[key]

    def on_page(self, ctx, corpus, page, quote):
        """Look ``quote`` up on its cited page: True when found, False when not (an
        error is reported), None when this corpus cannot be looked up here (a
        ``tsv_dir`` corpus is re-derived by its own family; an absent page tree is
        skipped + warned)."""
        entry = self.corpora.get(corpus) or {}
        # A corpus shipping its raw tables (`tsv_dir`) has no prose page to look in:
        # its quote is COMPOSED out of those tables, so family 13 re-derives it from
        # them instead.
        if entry.get("tsv_dir"):
            return None
        text = self.page_text(corpus, page) if entry.get("pages_dir") else None
        if text is None:
            self.skipped_corpora.add(corpus)
            return None
        if normalize_for_match(quote) not in text:
            missing = "" if text else " (page file missing, empty, or path-like)"
            self.report.error(f"{ctx}: quote NOT found verbatim on {corpus} "
                              f"p.{page}{missing}: {quote!r}")
            return False
        return True

    def check_one(self, ctx, src, short_ok=False):
        report, corpora = self.report, self.corpora
        if "corpus" not in src:
            return  # a bibliographic citation, not a quote-level source
        corpus = src.get("corpus")
        if corpus not in corpora:
            report.error(f"{ctx}: corpus {corpus!r} is not in "
                         f"meta.source_corpora (citation unrenderable)")
            return
        if src.get("heading"):
            self.headings.append((ctx, corpus, src.get("page"), src["heading"]))
        quote, page = src.get("quote"), src.get("page")
        if src.get("provenance") == "verified" and not (quote and page is not None):
            report.error(f"{ctx}: 'verified' source missing a page or quote "
                         f"(verified is the quote-checked grade)")
            return
        if quote:
            # NO LLM-PICKED QUOTE SHIPS UNJUDGED. A sentence a model chose out of prose
            # is the one that can be chosen wrongly (right page, wrong claim), so it
            # does not count as backed until a second model, which never saw the first
            # one's reasoning, agreed it supports the claim. A quote code copied out of
            # a table has no such failure mode and needs no judge. See CLAUDE.md "The
            # sourcing model" and tools/sourcing/recheck_quotes.py.
            if src.get("pipeline") not in self.pipelines:
                report.error(f"{ctx}: pipeline {src.get('pipeline')!r} is not in "
                             f"meta.quote_pipelines (chain of custody unrenderable)")
            elif src["pipeline"] in self.unjudged_pipelines:
                self.unjudged.append(ctx)
        if not quote or page is None:
            return  # weaker grade with no quote to check
        if spans_heading(quote):
            report.error(f"{ctx}: quote runs across a page heading (two sections "
                         f"glued into one claim): {quote!r}")
        if not self.on_page(ctx, corpus, page, quote):
            return
        needle = normalize_for_match(quote)
        self.n_checked += 1
        # A brand quote IS a short proper noun (the name, verbatim) and a Ki quote one
        # table row: short by design (callers pass short_ok). Any flattened table row
        # ("α 2A | 15 | Antagonist") is too, whichever node cites it: its cells are a
        # whole row of the page, never an incidental substring of prose.
        if (not short_ok and " | " not in quote
                and len(needle.replace(" ", "")) < _MIN_QUOTE_CHARS):
            report.warn(f"{ctx}: quote is very short ({quote!r}); it matched "
                        f"but may be an incidental substring")

    def check_claims(self, ctx, node, claimed):
        """Gate a node's per-claim split (``claims``, see quotes/attestation.py).

        A sub-claim's sources are a SUBSET of the owner's own, picked by a word test, so
        the verbatim gate would already cover the text; what is checked here is the
        SELECTION: every quote a sub-claim cites must really name what it is cited for,
        and a sub-claim citing nothing must carry the base grade rather than a borrowed
        check. Re-derived from the very vocabulary the generator graded it with, so a
        hand-edited or stale ``claims`` block fails instead of shipping.

        ``claimed`` maps each claim name to the value the node states for it (the
        transmitter, the sign, the strength tier), which is what the word test is run
        for.
        """
        report = self.report
        for claim, entry in (node.get("claims") or {}).items():
            srcs = entry.get("sources") or []
            for i, src in enumerate(srcs):
                where = f"{ctx} claims[{claim}] sources[{i}]"
                self.check_one(where, src)
                pattern = claim_pattern(claim, claimed.get(claim) or "")
                if pattern is None:
                    report.error(f"{where}: {claim} {claimed.get(claim)!r} has no word "
                                 f"test, so nothing could have attested it")
                elif not pattern.search(src.get("quote") or ""):
                    report.error(f"{where}: the quote does not name the {claim} it is "
                                 f"cited for ({claimed.get(claim)!r})")
            # A sub-claim another corpus denies, or a set-level sentence covers,
            # carries the same bullets as a whole node, gated the same way.
            self.check_uncertainty(f"{ctx} claims[{claim}]", entry)
            if not srcs and entry.get("grade") != CLAIM_BASE_GRADE:
                report.error(f"{ctx} claims[{claim}]: grade {entry.get('grade')!r} with "
                             f"no source (an unattested sub-claim is "
                             f"{CLAIM_BASE_GRADE!r})")

    def check_uncertainty(self, what, node):
        """Gate the "uncertain" badge's bullets on any node that carries them.

        Each bullet is itself a claim shown to the reader with its own pill, so each is
        gated like any other node: its quote must be verbatim on the cited page, its
        reason kind must be one the vocabulary defines, and a bullet with no source must
        SAY it is an absence of evidence rather than leave a silent blank. Shared by the
        drug bindings and the projections, which carry the same bullet shape.
        """
        report, reason_kinds = self.report, self.reason_kinds
        self.gated.add(id(node))
        for j, u in enumerate(node.get("uncertainty", []) or []):
            uctx = f"{what} uncertainty[{j}] ({u.get('kind')})"
            if u.get("kind") not in reason_kinds:
                report.error(f"{uctx}: reason kind is not one of "
                             f"meta.uncertainty_reasons ({sorted(reason_kinds)})")
            srcs = u.get("sources") or []
            if not srcs and not u.get("absence"):
                report.error(
                    f"{uctx}: has no source and does not declare absence=true. "
                    f"A bullet either cites a document or says outright that the "
                    f"corpus is silent; a blank one reads as the latter while "
                    f"meaning the source was forgotten")
            if srcs and u.get("absence"):
                report.error(f"{uctx}: declares absence=true yet cites a source")
            for k, src in enumerate(srcs):
                # A measured-affinity source is a CSV row id, not prose, so it is
                # gated by the Ki family (8) instead, exactly like a binding's own
                # ki.source.
                if (self.corpora.get(src.get("corpus"), {}).get("csv")
                        and not src.get("quote")):
                    continue
                self.check_one(f"{uctx} sources[{k}]", src)

    def check_location_uncertainty(self, what, owner):
        """A "Regional distribution" region's bullets, keyed like its location_sources."""
        for base, bullets in (owner.get("location_uncertainty") or {}).items():
            if base not in (owner.get("location_sources") or {}):
                self.report.error(f"{what} location_uncertainty[{base}]: no "
                                  f"location_sources for that region, so the doubt has "
                                  f"no claim to doubt")
            self.check_uncertainty(f"{what} location[{base}]", {"uncertainty": bullets})

    def report_quotes(self, before):
        """The verdict over every walk: absent page trees, then the verbatim tally."""
        report = self.report
        if self.skipped_corpora:
            report.warn(f"source pages absent for {sorted(self.skipped_corpora)} "
                        f"(author-only material); skipped the quote-in-page check there")
        if report.errors == before:
            report.ok(f"every checkable source quote ({self.n_checked}) is present "
                      f"verbatim in its cited page" if self.n_checked
                      else "no source quotes to verify yet")

    def report_unjudged(self):
        if self.unjudged:
            self.report.error(
                f"{len(self.unjudged)} LLM-picked quote citation(s) were never judged "
                f"by a second model (pipeline {sorted(self.unjudged_pipelines)}); run "
                f"tools/sourcing/recheck_quotes.py, e.g. {self.unjudged[:2]}")
        else:
            self.report.ok("every LLM-picked quote was judged by a second model")
