#!/usr/bin/env python
"""Integrity checks over the emitted dataset (``public/data/``).

This validates the committed data files that the static site actually serves
(``meta.json`` + ``structures`` / ``projections`` / ``circuits`` / ``receptors``
/ ``drugs`` ``.jsonl``), independently of ``generate_data.py``. The generator
already raises on most of these at build time; running the same checks over the
*emitted* artifacts is a cheap regression guard that also catches generator/data
drift and the duplicate/TODO classes the generator does not look for.

Run it directly (stdlib only, no deps, like ``generate_data.py``):

    python tools/check_data.py

Exit status is ``0`` when there are no errors (warnings are allowed) and ``1``
when any error is found, so it is usable as a gate (see the pre-push hook in
``tools/git-hooks/``).

Fourteen families of checks, numbered 0 to 13 as the report headers print them
(each ``check_*`` function's docstring holds the detail of its family):

0. **Quote table** (``check_quotes``). Every ``quote_id`` resolves, none is orphaned.

1. **Duplicates** (per collection). An exact duplicate id/key, or two ids that
   collide once **normalized** (lowercased, every non-alphanumeric character
   stripped: ``mao_a`` and ``mao-a`` -> ``maoa``), is an **error**. Two entries
   whose **display names** collide once normalized is a **warning** (a likely
   accidental re-entry to eyeball, but occasionally legitimate). Projections have
   no id, so they are checked for duplicate ``from -> to`` endpoints instead.

2. **Reachability** (referential integrity). Every cross-reference must resolve
   or the detail is **unreachable** in the viewer. The canonical case: a drug
   binding whose ``target`` is not a key of ``meta.drug_targets`` can never be
   focused from its panel. This also covers every receptor ``location`` / target
   ``region``: it must name a structure **base** present in the atlas, otherwise
   its "Found in" row in the panel would point at nothing and so be **unclickable**.
   All dangling references are **errors**.

3. **TODOs**. A literal ``"TODO"`` placeholder anywhere **outside** a source url
   (e.g. a binding ``note`` left as TODO), plus any focusable target with no
   ``wikipedia`` (the viewer shows a NOSOURCE pill), is a **warning**. A source
   *url* left as ``"TODO"`` is handled **provenance-aware**: the viewer surfaces a
   source's tiered grade (the pill), never its url, so a missing link on an ``llm``
   citation is the expected "no free link yet" state (reported as an ``[ok]``
   count, not a warning); only a source that *claims* a higher grade
   (``sourced`` / ``verified``) yet still has a ``TODO`` url is **warned** (an
   inconsistency: it asserts more than its link backs).

4. **Provenance grades**. Every emitted source (a ``sources[].provenance``,
   including the per-binding drug sources) and every wikipedia reference (a
   ``wikipedia_provenance`` beside a ``wikipedia``) must carry a known grade
   (``llm`` / ``sourced`` / ``verified``), the value the viewer renders as a
   grey/yellow/green pill. An unknown or missing grade is an **error** (the pill
   would fall back to "no source" and mislead). An UNKNOWN stamp (``unknown`` on a
   binding, data_generators/unknown.py) is an **error** on a binding that states a
   direction, or when its search skipped a corpus ``UNKNOWN_REQUIRED_SOURCES`` lists.

5. **Source quotes**. Each per-binding drug source is
   ``{corpus, page, quote, provenance}``; a ``"verified"`` grade is the one that
   claims the quote was confirmed present in the source. This re-confirms it: the
   ``corpus`` must resolve to ``meta.source_corpora``, a verified source must
   carry a page + quote, and the **normalized** quote must be an exact substring
   of the **normalized** cited page text (``<pages_dir>/<page>.md``). The page
   material is author-side and may be absent on a clone (see ``data_sources/books/stahl/`` in
   CLAUDE.local.md); the quote-in-page check is then **skipped with a warning**
   while the structural checks still run. A quote that is genuinely not on its
   page (an invented or mistyped extraction) is an **error**, so this is the gate
   that keeps the LLM extraction honest.

6. **Structure connectivity**. Warns (never errors) about a structure the
   connectome leaves stranded or one-sided: **isolated** (no projection touches
   it), **inward-only** (receives but never projects out), or **outward-only**
   (projects out but never receives, e.g. the modeled ascending source nuclei).
   An eyeball list for the author, not a gate.

7. **Measured-affinity (Ki) coverage**. Warns (never errors) per drug that carries
   bindings but no measured PDSP Ki on any of them, and re-confirms the shipped
   ``meta.provenance_stats.ki_coverage`` figure against a recompute. The honest
   complement to "% sourced": where a measured affinity was never looked up.

8. **Drug flow vs. binding consistency**. Warns (never errors) where a drug's
   by-mechanism flow overlay and its own receptor bindings tell opposite stories:
   the modeled flow raises a system's tone while the drug's postsynaptic receptors
   on that system net-block (or the reverse), and where it boosts a system's flow
   *into* a region whose receptors it strongly blocks. Ports the viewer's flow
   model so it reasons about the same numbers; an eyeball list (most flags are the
   intended presynaptic-tone vs. postsynaptic-block split), not a gate.

9. **Changelog** (``check_changelog``). ``version.js`` has its release notes.
10. **Innervation coverage** (``check_innervation``). Warns per transmitter system.
11. **Baked meshes** (``check_baked_meshes``). The SDF bake matches its shapes.
12. **Enzyme variability** (``check_enzyme_variability``). Re-derived from the
    pinned PharmFreq tables.
13. **Freshness** (``check_freshness``). An editable online corpus page cited but
    downloaded too long ago fails, and so does an UNKNOWN search that old.

Built with the help of Claude Code.
"""

import csv
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

# The PharmFreq export reader, imported rather than restated: family 12
# rebuilds the emitted quotes with the very code that wrote them, which is
# the whole point of the derivation gate (see data_generators/pharmfreq.py).
from data_generators import (
    clinpgx,
    cpic,
    demographics as DEMOG,
    freshness,
    pharmfreq,
    release_modulation as RELMOD,
)
# The pathway per-claim word tests, imported for the same reason: family 5 re-runs the
# very test that graded a transmitter/sign sub-claim, so a hand-edited or stale ``claims``
# block (a source that does not name what it is cited for) fails instead of shipping.
from data_generators.quotes.attestation import (
    BASE_GRADE as CLAIM_BASE_GRADE,
    pattern_for as claim_pattern,
)
# The curated contradictions, keyed by citation site and resolved through the one site
# grammar (tools/sourcing/citation_site.py), exactly as the generator applies them.
from data_generators.quotes.contradictions import CONTRADICTIONS
from lib import stahl_index  # (the one INDEX.md reader)
from lib.page_file import page_file  # (refuses a path-like page)
from lib.quote_match import normalize_for_match
from lib.text_fold import alnum_key
from sourcing import citation_site as CS

from checks.baked_meshes import check_baked_meshes
from checks.changelog import check_changelog
from checks.common import (
    DATA_DIR,
    REPO_ROOT,
    Report,
    expand_mirrored,
    load_jsonl,
    load_meta,
)
from checks.connectivity import check_connectivity
from checks.duplicates import check_binding_dups, check_duplicates, check_id_collection
from checks.flow import _affinity_weight, _tone_of, check_flow_consistency
from checks.innervation import check_innervation
from checks.ki_coverage import check_ki_coverage
from checks.provenance import check_provenance
from checks.quotes import check_quotes, load_quotes, rehydrate_quotes
from checks.reachability import check_reachability
from checks.todos import check_todos
from checks.walks import iter_drug_sources, unknown_stamps


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

# A quote can be verbatim on the cited page and still not support the claim. The
# recurring way that happened here: Stahl's "How Drug Causes Side Effects" block
# lists the mechanisms of the drug's CLASS as subject-less rules ("Blocking
# muscarinic cholinergic receptors can cause dry mouth ..."), printed identically
# across the monographs (that one on 17 pages, the alpha-1 one on 28), so it never
# states that THIS drug blocks anything. 151 antipsychotic bindings were once
# sourced from three such lines, including muscarinic + H1 + alpha-1 blockade for
# sulpiride, a benzamide with none of them. A sentence that attributes the action
# ("By blocking X, IT can cause Y", "Paroxetine's weak antimuscarinic properties
# can cause ...") is fine and deliberately not matched: the subject is the point.
_NO_SUBJECT_QUOTE = re.compile(
    r"^(Blocking\b|Antihistaminic actions\b)[^.]*\b(can|may) cause\b", re.I)

# The other half of "is this quote about the drug we are talking about?": a Stahl
# quote must come from a page inside that drug's OWN monograph. The book is one
# monograph per drug over a contiguous page span, so a page outside the span is a
# quote read off a neighbour's entry, which no amount of verbatim matching would
# catch (the sentence really is on the page, just not that drug's page).
def _fold_name(name):
    """A drug name reduced to its letters+digits, so ``Amphetamine (d,l)`` and the
    index's ``Amphetamine (D,L)`` compare equal."""
    return alnum_key(name)


def stahl_monograph_ranges():
    """``folded drug name -> (first page, last page)`` from Stahl's generated INDEX.md.

    ``None`` when the author-side book tree is absent (a plain clone), so the
    caller skips the check exactly like the verbatim-quote gate does."""
    ranges = stahl_index.ranges(_fold_name, missing_ok=True)
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
    span = next((ranges[k] for k in map(_fold_name, names) if k in ranges), None)
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


def check_sources(report, meta, drugs, projections, structures, receptors, addons,
                  metabolites=(), circuits=(), groups=(), contradictions=()):
    """The core of the sourcing system: confirm every quote-level source (a
    binding's ``sources``, a drug's ``nbn_sources``, an enzyme's ``variability``
    sources, and a projection's quote-level ``sources``) is actually present in the
    page it cites.

    A source is ``{corpus, page, quote, provenance}`` (the one shape used everywhere:
    drug bindings, NbN, projection/circuit/group quotes, region anatomy). A source
    with no ``corpus`` field is defensively skipped (there are none today; fabricated
    bibliographic ``{citation, url}`` citations were removed). This:

    * checks ``corpus`` resolves to ``meta.source_corpora`` (else the citation is
      unrenderable) and that a ``"verified"`` grade carries a page + quote;
    * for any source that carries a quote + page, locates the corpus's page file
      (``<pages_dir>/<page>.md``) and asserts the **normalized** quote is a
      substring of the **normalized** page text (see :func:`normalize_for_match`).

    The page material is author-side and may be absent on a plain checkout (it is
    large + uncommitted, see ``data_sources/books/stahl/`` in CLAUDE.local.md); when a corpus has no
    ``pages_dir`` on disk the quote-in-page check is **skipped with a warning**
    while the structural checks above still run. So this hard-fails an invented or
    mistyped quote on the author's machine (and the pre-push gate) without
    breaking on a clone that lacks the sources.

    One corpus stands that lookup **down** rather than skipping it. A corpus shipping
    its own raw tables declares ``tsv_dir`` and no ``pages_dir`` (PharmFreq, #13):
    there is no prose page to look in, and a page written out of the same numbers as
    the quote would prove nothing. Its quotes are gated by re-derivation from the
    sha256-pinned files instead, in :func:`check_enzyme_variability` (family 12),
    which is why that is the one quote gate that runs on a plain clone."""
    report.header("5. Source quotes (verbatim in cited page)")
    corpora = meta.get("source_corpora", {})
    # The closed vocabulary the "uncertain" bullets draw their reason kinds from,
    # read from the data rather than restated here so the two cannot drift.
    reason_kinds = set(meta.get("uncertainty_reasons", {}))
    before = report.errors

    # pipeline key -> its chain of custody (see provenance.QUOTE_PIPELINES). The rule
    # below is read OFF the chains rather than restated as a list of key names: a
    # pipeline in which a model chose the sentence but no model ever judged it is the
    # violation, whatever it ends up being called.
    pipelines = meta.get("quote_pipelines", {})
    unjudged_pipelines = {k for k, steps in pipelines.items()
                          if "extract_llm" in steps and "judge_llm" not in steps}
    unjudged = []

    page_cache = {}            # (corpus, page) -> normalized page text or None
    skipped_corpora = set()
    n_checked = 0
    # Every source carrying a derived book heading, checked in one pass below
    # (collected here so the whole dataset is walked once, not twice).
    headings = []

    def page_text(corpus, page):
        key = (corpus, page)
        if key not in page_cache:
            entry = corpora.get(corpus) or {}
            pages_dir = entry.get("pages_dir")
            text = None
            md = page_file(REPO_ROOT / pages_dir, page) if pages_dir else None
            if md and md.exists():
                text = normalize_for_match(md.read_text(encoding="utf-8"))
            page_cache[key] = text
        return page_cache[key]

    def check_one(ctx, src, short_ok=False):
        nonlocal n_checked
        if "corpus" not in src:
            return  # a bibliographic citation, not a quote-level source
        corpus = src.get("corpus")
        if corpus not in corpora:
            report.error(f"{ctx}: corpus {corpus!r} is not in "
                         f"meta.source_corpora (citation unrenderable)")
            return
        if src.get("heading"):
            headings.append((ctx, corpus, src.get("page"), src["heading"]))
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
            if src.get("pipeline") not in pipelines:
                report.error(f"{ctx}: pipeline {src.get('pipeline')!r} is not in "
                             f"meta.quote_pipelines (chain of custody unrenderable)")
            elif src["pipeline"] in unjudged_pipelines:
                unjudged.append(ctx)
        if not quote or page is None:
            return  # weaker grade with no quote to check
        if spans_heading(quote):
            report.error(f"{ctx}: quote runs across a page heading (two sections "
                         f"glued into one claim): {quote!r}")
        entry = corpora.get(corpus) or {}
        # A corpus shipping its raw tables (`tsv_dir`) has no prose page to look in:
        # its quote is COMPOSED out of those tables, so family 13 re-derives it from
        # them instead. Everything structural above still applies.
        if entry.get("tsv_dir"):
            return
        if not entry.get("pages_dir"):
            skipped_corpora.add(corpus)
            return
        text = page_text(corpus, page)
        if text is None:
            skipped_corpora.add(corpus)
            return
        needle = normalize_for_match(quote)
        if needle not in text:
            report.error(f"{ctx}: quote NOT found verbatim on {corpus} "
                         f"p.{page}: {quote!r}")
            return
        n_checked += 1
        # A brand quote IS a short proper noun (the name, verbatim) and a Ki quote one
        # table row: short by design (callers pass short_ok). Any flattened table row
        # ("α 2A | 15 | Antagonist") is too, whichever node cites it: its cells are a
        # whole row of the page, never an incidental substring of prose.
        if (not short_ok and " | " not in quote
                and len(needle.replace(" ", "")) < _MIN_QUOTE_CHARS):
            report.warn(f"{ctx}: quote is very short ({quote!r}); it matched "
                        f"but may be an incidental substring")

    def check_claims(ctx, node, claimed):
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
        for claim, entry in (node.get("claims") or {}).items():
            srcs = entry.get("sources") or []
            for i, src in enumerate(srcs):
                where = f"{ctx} claims[{claim}] sources[{i}]"
                check_one(where, src)
                pattern = claim_pattern(claim, claimed.get(claim) or "")
                if pattern is None:
                    report.error(f"{where}: {claim} {claimed.get(claim)!r} has no word "
                                 f"test, so nothing could have attested it")
                elif not pattern.search(src.get("quote") or ""):
                    report.error(f"{where}: the quote does not name the {claim} it is "
                                 f"cited for ({claimed.get(claim)!r})")
            # A sub-claim another corpus denies, or a set-level sentence covers,
            # carries the same bullets as a whole node, gated the same way.
            check_uncertainty(f"{ctx} claims[{claim}]", entry)
            if not srcs and entry.get("grade") != CLAIM_BASE_GRADE:
                report.error(f"{ctx} claims[{claim}]: grade {entry.get('grade')!r} with "
                             f"no source (an unattested sub-claim is "
                             f"{CLAIM_BASE_GRADE!r})")

    gated = set()              # id() of every node whose bullets were gated below

    def check_uncertainty(what, node):
        """Gate the "uncertain" badge's bullets on any node that carries them.

        Each bullet is itself a claim shown to the reader with its own pill, so each is
        gated like any other node: its quote must be verbatim on the cited page, its
        reason kind must be one the vocabulary defines, and a bullet with no source must
        SAY it is an absence of evidence rather than leave a silent blank. Shared by the
        drug bindings and the projections, which carry the same bullet shape.
        """
        gated.add(id(node))
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
                if (corpora.get(src.get("corpus"), {}).get("csv")
                        and not src.get("quote")):
                    continue
                check_one(f"{uctx} sources[{k}]", src)

    def check_location_uncertainty(what, owner):
        """A "Found in" region's bullets, keyed like its location_sources."""
        for base, bullets in (owner.get("location_uncertainty") or {}).items():
            if base not in (owner.get("location_sources") or {}):
                report.error(f"{what} location_uncertainty[{base}]: no location_sources "
                             f"for that region, so the doubt has no claim to doubt")
            check_uncertainty(f"{what} location[{base}]", {"uncertainty": bullets})

    for drug in drugs:
        did = drug.get("id")
        for ctx, src, short_ok, facet, owner in iter_drug_sources(drug):
            check_one(ctx, src, short_ok=short_ok)
            # A binding that DECLARES the problem (the orange "uncertain" badge, whose
            # own bullets say the sentence attributes nothing) is not silently passing
            # a subject-less quote off as a green check, so the gate stands down.
            if (facet == "binding" and not owner.get("uncertainty")
                    and _NO_SUBJECT_QUOTE.match(src.get("quote") or "")):
                report.error(
                    f"{ctx}: quote is a subject-less mechanism -> side-effect rule "
                    f"({src.get('quote')!r}). Stahl's 'How Drug Causes Side Effects' "
                    f"block prints the same lines on every monograph in the class, so "
                    f"such a sentence never says THIS drug has the action: it cannot "
                    f"source a binding (an attributed one, 'By blocking X, IT can "
                    f"cause Y', can)")
        for binding in drug.get("bindings", []):
            # A quote-carrying Ki source (corpus #9 wikipedia_pharm cites the verbatim
            # affinity-table row) is gated here like any other quote. A PDSP Ki cites a
            # CSV row (ki_id, no quote) and is verified by the CSV gate below instead, so
            # only feed a Ki source that actually carries a quote.
            ki_src = (binding.get("ki") or {}).get("source")
            if ki_src and ki_src.get("quote"):
                # A Ki quote is one table row (target | value | species): short by
                # design, and its number + target make a chance match implausible.
                check_one(f"drug {did} binding {binding.get('target')} ki.source", ki_src,
                          short_ok=True)
            check_uncertainty(f"drug {did} binding {binding.get('target')}", binding)
        for e in drug.get("enzymes", []) or []:
            # The denial quote of a contradicted row is gated exactly like the claim it
            # doubts: both sides of a corpus disagreement earn their grade the same way.
            check_uncertainty(f"drug {did} enzyme {e.get('enzyme')} ({e.get('role')})", e)
            # HOW MUCH of the clearing the row claims: its own node, so its own gate.
            check_claims(f"drug {did} enzyme {e.get('enzyme')}", e,
                         {"strength": e.get("strength")})
        # A denial of a metabolite link (CONTRADICTIONS), gated like the link.
        for m in drug.get("metabolites", []) or []:
            check_uncertainty(f"drug {did} metabolite {m.get('id')}", m)

    for m in metabolites:
        mid = f"metabolite {m.get('id')}"
        for i, src in enumerate(m.get("half_life_sources", []) or []):
            check_one(f"{mid} half_life_sources[{i}]", src)
        for binding in m.get("bindings", []) or []:
            for i, src in enumerate(binding.get("sources", []) or []):
                check_one(f"{mid} binding {binding.get('target')} sources[{i}]", src)
            # A metabolite binding's quote-carrying Ki (wikipedia_pharm table row) is
            # gated exactly like a drug binding's (a PDSP CSV Ki is checked below).
            ki_src = (binding.get("ki") or {}).get("source")
            if ki_src and ki_src.get("quote"):
                check_one(f"{mid} binding {binding.get('target')} ki.source", ki_src,
                          short_ok=True)  # a table row, as for a drug's Ki above
            check_uncertainty(f"{mid} binding {binding.get('target')}", binding)

    for addon in addons:
        for i, src in enumerate(addon.get("sources", []) or []):
            check_one(f"addon {addon.get('id')} sources[{i}]", src)

    for proj in projections:
        pid = f"{proj.get('from')}->{proj.get('to')}"
        for i, src in enumerate(proj.get("sources", []) or []):
            check_one(f"projection {pid} sources[{i}]", src)
        # The per-claim split (transmitter / sign): gated by the shared helper above.
        check_claims(f"projection {pid}", proj, {
            "transmitter": proj.get("neurotransmitter"),
            "sign": (meta.get("kind_signs") or {}).get(proj.get("kind")),
        })
        # A pathway the book only states as a blanket sweep wears the same orange badge
        # a binding does, and its bullets are gated the same way.
        check_uncertainty(f"projection {pid}", proj)

    effect_modes = meta.get("receptor_effect_modes") or {}
    effect_labels = meta.get("receptor_effect_labels") or {}

    def check_effects(ctx, owner, is_receptor):
        """receptor_effect nodes (BETA): closed vocabularies, one quote at least, each
        quote gated like any other. ``inhibition`` is a non-receptor target's mode."""
        for e in owner.get("effects") or []:
            where = f"{ctx} effects[{e.get('mode')}:{e.get('effect')}]"
            if e.get("mode") not in effect_modes or e.get("effect") not in effect_labels:
                report.error(f"{where}: mode/effect not in meta.receptor_effect_*")
            if is_receptor and e.get("mode") == "inhibition":
                report.error(f"{where}: 'inhibition' on a receptor")
            if not e.get("sources"):
                report.error(f"{where}: an effect node with no source")
            for i, src in enumerate(e.get("sources") or []):
                check_one(f"{where} sources[{i}]", src)

    structure_bases = {s.get("id", "").removesuffix("_R").removesuffix("_L")
                       for s in structures}

    def check_release_modulation(r):
        """receptor_release_modulation nodes (BETA): the same closed-vocabulary rules
        the applier and the emitter enforce (``release_modulation.vocab_error``), one
        quote at least, each quote gated like any other."""
        for n in r.get("release_modulation") or []:
            site = n.get("site") or {}
            f = {"kind": n.get("kind"), "structure": site.get("structure"),
                 "cell": site.get("cell"), "modulates": n.get("modulates"),
                 "effect": n.get("effect_of_activation")}
            where = f"receptor {r.get('id')} release_modulation[{RELMOD.node_key(**f)}]"
            neuro = r.get("neurotransmitter")
            why = RELMOD.vocab_error(f, neuro.get("en") if isinstance(neuro, dict) else neuro,
                                     structure_bases)
            if why:
                report.error(f"{where}: {why}")
            if not n.get("sources"):
                report.error(f"{where}: a release-modulation node with no source")
            for i, src in enumerate(n.get("sources") or []):
                check_one(f"{where} sources[{i}]", src)

    def check_demographics(ctx, owner):
        """receptor_demographic nodes (BETA): the closed vocabulary the applier and the
        emitter enforce (``demographics.vocab_error``), a magnitude verbatim in one of
        its own quotes, one quote at least, each quote gated like any other."""
        for n in owner.get("demographics") or []:
            f = {k: n.get(k) for k in ("factor", "direction", "structure")}
            where = f"{ctx} demographics[{DEMOG.node_key(**f)}]"
            why = DEMOG.vocab_error(f, structure_bases)
            if why:
                report.error(f"{where}: {why}")
            if not n.get("sources"):
                report.error(f"{where}: a demographic node with no source")
            mag = n.get("magnitude")
            if mag and not any(normalize_for_match(mag) in normalize_for_match(s.get("quote") or "")
                               for s in n.get("sources") or []):
                report.error(f"{where}: magnitude {mag!r} is in none of its quotes")
            for i, src in enumerate(n.get("sources") or []):
                check_one(f"{where} sources[{i}]", src)

    for s in structures:
        for i, src in enumerate(s.get("sources", []) or []):
            check_one(f"structure {s.get('id')} sources[{i}]", src)

    for r in receptors:
        for attr, entry in (r.get("classification") or {}).items():
            for i, src in enumerate(entry.get("sources") or []):
                check_one(f"receptor {r.get('id')} classification[{attr}] sources[{i}]", src)
            check_uncertainty(f"receptor {r.get('id')} classification[{attr}]", entry)
        # Per-region expression sources are quote-checked like any other (the gate
        # that keeps a future "5-HT2A is dense in the PFC" citation honest).
        for base, srcs in (r.get("location_sources") or {}).items():
            for i, src in enumerate(srcs or []):
                # One tissue line of the receptor's own gene page ("CNS: pons.").
                check_one(f"receptor {r.get('id')} location_sources[{base}][{i}]", src,
                          short_ok=True)
        check_location_uncertainty(f"receptor {r.get('id')}", r)
        # The density profile's quote carries the z per region and the cross-donor
        # agreement, so gating it verbatim is what keeps those numbers honest.
        for i, src in enumerate((r.get("density") or {}).get("sources") or []):
            check_one(f"receptor {r.get('id')} density sources[{i}]", src)
        check_effects(f"receptor {r.get('id')}", r, is_receptor=True)
        check_release_modulation(r)
        check_demographics(f"receptor {r.get('id')}", r)
        for n in r.get("variants") or []:
            for i, src in enumerate(n.get("sources") or []):
                check_one(f"receptor {r.get('id')} variants[{n.get('annotation')}] "
                          f"sources[{i}]", src)

    for tid, tinfo in (meta.get("drug_targets", {}) or {}).items():
        if isinstance(tinfo, dict):
            for i, src in enumerate(tinfo.get("sources", []) or []):
                check_one(f"target {tid} sources[{i}]", src)
            # A non-receptor target's per-region expression sources, quote-checked
            # like the receptor ones (same honesty gate for a future citation).
            for base, srcs in (tinfo.get("location_sources") or {}).items():
                for i, src in enumerate(srcs or []):
                    check_one(f"target {tid} location_sources[{base}][{i}]", src,
                              short_ok=True)  # one line of its gene page, as above
            check_location_uncertainty(f"target {tid}", tinfo)
            for i, src in enumerate((tinfo.get("density") or {}).get("sources") or []):
                check_one(f"target {tid} density sources[{i}]", src)
            check_effects(f"target {tid}", tinfo, is_receptor=False)
            check_demographics(f"target {tid}", tinfo)
            for n in tinfo.get("variants") or []:
                for i, src in enumerate(n.get("sources") or []):
                    check_one(f"target {tid} variants[{n.get('annotation')}] "
                              f"sources[{i}]", src)

    # Metabolizer-status profiles hang off `meta.enzymes`, not off any node file, so
    # they are reached from here rather than by the walks above. The page lookup stands
    # down for them (see the `tsv_dir` branch), but the structural half applies: a
    # `verified` grade still owes a page and a quote, and the pipeline still has to be
    # one `meta.quote_pipelines` describes.
    for eid, enzyme in sorted((meta.get("enzymes") or {}).items()):
        for i, src in enumerate(((enzyme.get("variability") or {})
                                 .get("sources") or [])):
            check_one(f"enzyme {eid} variability sources[{i}]", src)

    if skipped_corpora:
        report.warn(f"source pages absent for {sorted(skipped_corpora)} "
                    f"(author-only material); skipped the quote-in-page check there")
    if report.errors == before:
        report.ok(f"every checkable source quote ({n_checked}) is present verbatim "
                  f"in its cited page" if n_checked
                  else "no source quotes to verify yet")

    # A source's `heading` (the breadcrumb of book headings the passage sits under)
    # is DERIVED, keyed by quote id, from the author-side page trees by
    # tools/fetch/fetch_quote_headers.py. Nothing in the emitted data proves it is
    # still current, so check what is checkable without the books: the shape. A
    # blank level would render as an empty crumb, which reads like a heading the
    # book actually prints rather than one the resolver failed to find.
    before_shape = report.errors
    for ctx, corpus, page, trail in headings:
        if not isinstance(trail, list) or not trail:
            report.error(f"{ctx}: heading must be a non-empty list of headings, "
                         f"outermost first (got {trail!r}); omit it rather than "
                         f"storing an empty breadcrumb")
            continue
        for part in trail:
            if not isinstance(part, str) or not part.strip():
                report.error(f"{ctx}: heading trail has a blank level ({trail!r}); "
                             f"drop the level rather than storing a blank crumb")
    if report.errors == before_shape and headings:
        report.ok(f"all {len(headings)} derived heading trails are non-empty lists "
                  f"of non-blank headings")

    # Every Stahl quote on a drug must come off that drug's own monograph pages.
    ranges = stahl_monograph_ranges()
    if ranges is None:
        report.warn("Stahl INDEX.md absent (author-only material); skipped the "
                    "check that each drug's quotes come from its own monograph")
    else:
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
            span = ranges.get(_fold_name(trail[0])) if trail else None
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

    # A binding's `ki` cites one CSV row by ki_id (the analogue of a quote's page):
    # confirm that row really exists in the corpus CSV with the cited value. Like the
    # quote gate this is author-side (the CSV is large + uncommitted, see
    # data_sources/books/pdsp_ki/), skipped with a warning on a clone that lacks it.
    ki_before = report.errors
    ki_index_cache = {}          # corpus -> {ki_id: ki_val_str} or None if csv absent

    def ki_index(corpus):
        if corpus not in ki_index_cache:
            entry = corpora.get(corpus) or {}
            path = entry.get("csv")
            idx = None
            if path and (REPO_ROOT / path).exists():
                idx = {}
                with open(REPO_ROOT / path, newline="", encoding="utf-8",
                          errors="replace") as f:
                    for row in csv.DictReader(f):
                        try:
                            idx[int(row["Number"])] = (row.get("ki Val") or "").strip()
                        except (TypeError, ValueError, KeyError):
                            pass
            ki_index_cache[corpus] = idx
        return ki_index_cache[corpus]

    n_ki = 0
    ki_skipped = set()

    def check_ki_source(ctx, src):
        """Gate one source citing a PDSP-CSV row by ki_id: a binding's Ki, or an
        uncertainty bullet's measurement (a curated denial included)."""
        nonlocal n_ki
        corpus, ki_id = src.get("corpus"), src.get("ki_id")
        # Only a CSV corpus (PDSP) cites a row by ki_id; a quote-gated Ki corpus
        # (wikipedia_pharm) was already verified by the source-quote gate above.
        if not (corpora.get(corpus) or {}).get("csv"):
            return
        if src.get("provenance") == "verified" and ki_id is None:
            report.error(f"{ctx}: 'verified' source needs a ki_id")
            return
        if ki_id is None:
            return
        idx = ki_index(corpus)
        if idx is None:
            ki_skipped.add(corpus)
            return
        if ki_id not in idx:
            report.error(f"{ctx}: ki_id {ki_id} not found in {corpus} CSV")
            return
        # The stored value must be the row's own value (we took it from there).
        try:
            if abs(float(idx[ki_id]) - float(src.get("value_nm"))) > 0.01:
                report.error(f"{ctx}: value_nm {src.get('value_nm')} != CSV row "
                             f"{ki_id} value {idx[ki_id]!r}")
                return
        except (TypeError, ValueError):
            pass
        n_ki += 1

    def check_bullet_ki(ctx, node):
        """The CSV-row sources of a node's uncertainty bullets, which the bullet gate
        (``check_uncertainty``) hands over to this family."""
        for j, u in enumerate(node.get("uncertainty") or []):
            for k, src in enumerate(u.get("sources") or []):
                if src.get("ki_id") is not None:
                    check_ki_source(f"{ctx} uncertainty[{j}] sources[{k}]", src)

    def check_ki(ctx, binding):
        """Gate one binding's PDSP-CSV Ki (a metabolite binding's Ki is checked the same
        way as a drug's) and its bullets' CSV rows."""
        check_ki_source(f"{ctx} ki", (binding.get("ki") or {}).get("source") or {})
        check_bullet_ki(ctx, binding)

    for drug in drugs:
        did = drug.get("id")
        for binding in drug.get("bindings", []):
            check_ki(f"drug {did} binding {binding.get('target')}", binding)
    for m in metabolites:
        for binding in m.get("bindings", []) or []:
            check_ki(f"metabolite {m.get('id')} binding {binding.get('target')}", binding)
    if ki_skipped:
        report.warn(f"Ki CSV absent for {sorted(ki_skipped)} (author-only material); "
                    f"skipped the ki-row-in-CSV check there")
    if report.errors == ki_before:
        report.ok(f"every checkable Ki annotation ({n_ki}) cites a real CSV row"
                  if n_ki else "no Ki annotations to verify yet")

    # The curated "contradicted" table, keyed by citation site (any node kind): every
    # site must still name exactly one emitted node, that node must wear the badge, and
    # its denial quotes are gated here when no per-kind walk above reached the node.
    nodes, ambiguous = CS.node_index(
        drugs=drugs, metabolites=metabolites, receptors=receptors,
        targets=meta.get("drug_targets") or {}, projections=projections,
        circuits=circuits, groups=groups, structures=structures)
    for site in contradictions:
        node = None if site in ambiguous else nodes.get(site)
        if node is None:
            report.error(f"CONTRADICTIONS[{site!r}]: names "
                         f"{'two emitted nodes' if site in ambiguous else 'no emitted node'}"
                         f" (gone, renamed, or a flat facet): the contradiction marks "
                         f"nothing")
            continue
        if not any(u.get("kind") == "contradicted" for u in node.get("uncertainty") or []):
            report.error(f"CONTRADICTIONS[{site!r}]: the node carries no contradicted "
                         f"bullet (stale data/: rerun tools/generate_data.py)")
        if id(node) not in gated:
            check_uncertainty(site, node)
            check_bullet_ki(site, node)

    if unjudged:
        report.error(f"{len(unjudged)} LLM-picked quote citation(s) were never judged "
                     f"by a second model (pipeline {sorted(unjudged_pipelines)}); run "
                     f"tools/sourcing/recheck_quotes.py, e.g. {unjudged[:2]}")
    else:
        report.ok("every LLM-picked quote was judged by a second model")


def check_enzyme_variability(report, meta, drugs):
    """Family 12: the metabolizer-status profiles, re-derived from their pinned tables.

    Every other corpus proves a quote by finding it verbatim in prose somebody else
    wrote. PharmFreq (corpus #13) publishes a table instead, and the sentence a reader
    sees is one this repo composes out of it, so there is no page to look in: writing
    that sentence to a page file and then finding it there would prove only that the
    same code ran twice.

    So the proof runs the other way. The export is committed under `tools/data/`
    (small, freely redistributable, unlike the books), the cache that built the profiles
    pins each file's sha256, and this rebuilds every emitted profile and quote straight
    off those files. A hand-edited frequency, a stale cache, a refreshed download nobody
    re-ran the fetcher over: each one lands here as an error, on any clone, with no
    author-side material needed.
    """
    report.header("12. Enzyme variability (profiles re-derived from the pinned export)")
    corpora = meta.get("source_corpora") or {}
    tsv_corpora = {c: e for c, e in corpora.items() if e.get("tsv_dir")}
    if not tsv_corpora:
        report.ok("no committed-table corpus to re-derive")
        return
    for corpus, entry in sorted(tsv_corpora.items()):
        export = REPO_ROOT / entry["tsv_dir"]
        if not export.is_dir():
            report.error(f"{corpus}: {entry['tsv_dir']} is missing, yet the corpus is "
                         f"committed with the repo (its quotes cannot be re-derived)")
            return
        pins = entry.get("export_sha256") or {}
        if not pins:
            report.error(f"{corpus}: declares {entry['tsv_dir']} but pins no file "
                         f"sha256, so nothing anchors its quotes")
            return
        # Every file that looks like part of this export, by the extension the pins
        # themselves use (PharmFreq ships TSVs, CPIC one JSON), so a new sibling data
        # file nothing anchors is caught while the dir's README is left alone.
        suffixes = {Path(name).suffix for name in pins}
        on_disk = {p.name for p in export.iterdir()
                   if p.is_file() and p.suffix in suffixes}
        fetcher = f"tools/fetch/fetch_{corpus}.py"
        for name in sorted(set(pins) | on_disk):
            if name not in on_disk:
                report.error(f"{corpus}: pins {name}, which is not in "
                             f"{entry['tsv_dir']}")
            elif name not in pins:
                report.error(f"{corpus}: {entry['tsv_dir']}/{name} is not pinned "
                             f"(re-run {fetcher})")
            elif pharmfreq.sha256(str(export / name)) != pins[name]:
                report.error(f"{corpus}: {entry['tsv_dir']}/{name} no longer hashes to "
                             f"its pin, so the emitted numbers are not the ones in it "
                             f"(re-run {fetcher})")
        if report.errors:
            return

    export = REPO_ROOT / tsv_corpora["pharmfreq"]["tsv_dir"]
    try:
        raw = pharmfreq.read_export(str(export))
    except pharmfreq.ExportError as exc:
        report.error(f"pharmfreq: {exc}")
        return

    n = 0
    for eid, enzyme in sorted((meta.get("enzymes") or {}).items()):
        var = enzyme.get("variability")
        if not var:
            continue
        gene = var.get("gene")
        ctx = f"enzyme {eid} variability"
        if gene not in raw:
            report.error(f"{ctx}: cites gene {gene!r}, which the export does not cover")
            continue
        if pharmfreq.GENE_ENZYMES.get(gene) != eid:
            report.error(f"{ctx}: gene {gene!r} is mapped to "
                         f"{pharmfreq.GENE_ENZYMES.get(gene)!r}, not to {eid!r}")
            continue
        want_profile = pharmfreq.ordered_profile(raw[gene])
        if var.get("profile") != want_profile:
            report.error(f"{ctx}: the emitted profile is not what {gene} reads in the "
                         f"export (re-run tools/fetch/fetch_pharmfreq.py)")
            continue
        # Key order is deliberately NOT checked: the viewer walks
        # `meta.metabolizer_groups` and looks each group up, so the profile is a
        # mapping and the cache is free to serialize it sorted.
        want_quote = pharmfreq.quote_for(gene, want_profile)
        srcs = var.get("sources") or []
        if not srcs:
            report.error(f"{ctx}: carries a profile but no source")
            continue
        for i, src in enumerate(srcs):
            if src.get("page") != gene:
                report.error(f"{ctx} sources[{i}]: page {src.get('page')!r} is not the "
                             f"gene symbol {gene!r} the profile is keyed by")
            if src.get("quote") != want_quote:
                report.error(f"{ctx} sources[{i}]: the quote is not the one the export "
                             f"yields for {gene} (re-run tools/fetch/fetch_pharmfreq.py)")
            else:
                n += 1

    covered = {eid for eid, e in (meta.get("enzymes") or {}).items()
               if e.get("variability")}
    uncovered = sorted(set(pharmfreq.GENE_ENZYMES.values()) - covered)
    if uncovered:
        report.warn(f"mapped to a PharmFreq gene but carrying no profile: "
                    f"{', '.join(uncovered)}")
    report.ok(f"{n} metabolizer-status quote(s) re-derived from the pinned export, "
              f"exact match")
    check_cpic_guidance(report, meta, drugs)


def check_cpic_guidance(report, meta, drugs):
    """Family 12, second half: CPIC's guidance, re-derived from its pinned export.

    Same mechanism as the profiles above and for a different reason. The quote here IS
    somebody else's sentence, so it could be gated against a page; the point of
    re-deriving instead is that this is the one corpus whose text is **clinical advice**
    ("use 50% of the typical dose"), so every emitted word has to come out of the pinned
    file by code, with no step in between where a sentence could be trimmed, joined or
    paraphrased into saying something CPIC did not.

    Checks the whole shape, not just the quotes: the gene-drug pairs present, each row's
    phenotype / implication / recommendation / classification / assumption, and both of
    its citations. A pair that drifts, or one the emitted data invents, is an error.
    """
    corpora = meta.get("source_corpora") or {}
    if "cpic" not in corpora:
        report.ok("no CPIC corpus to re-derive")
        return
    try:
        want = cpic.guidance_for(cpic.read_export(cpic.export_path(str(REPO_ROOT))))
    except cpic.ExportError as exc:
        report.error(f"cpic: {exc}")
        return

    got = {d["id"]: d["pgx"] for d in drugs if d.get("pgx")}
    for drug in sorted(set(want) | set(got)):
        if drug not in got:
            report.error(f"cpic: the export carries guidance for {drug}, which the "
                         f"emitted drug does not (re-run tools/generate_data.py)")
            continue
        if drug not in want:
            report.error(f"drug {drug} carries CPIC guidance the export does not "
                         f"(re-run tools/fetch/fetch_cpic.py)")
            continue
    n = 0
    for drug in sorted(set(want) & set(got)):
        blocks, emitted = want[drug], got[drug]
        if len(blocks) != len(emitted):
            report.error(f"drug {drug} pgx: {len(emitted)} gene block(s) emitted, "
                         f"{len(blocks)} in the export")
            continue
        for block, out in zip(blocks, emitted):
            ctx = f"drug {drug} pgx {block['gene']}"
            for key in ("gene", "enzyme", "level"):
                if out.get(key) != block[key]:
                    report.error(f"{ctx}: {key} is {out.get(key)!r}, not "
                                 f"{block[key]!r} as the export reads")
            if (out.get("guideline") or {}).get("id") != block["guideline"]["id"]:
                report.error(f"{ctx}: cites a guideline the export does not")
            if len(out.get("rows") or []) != len(block["rows"]):
                report.error(f"{ctx}: {len(out.get('rows') or [])} row(s) emitted, "
                             f"{len(block['rows'])} in the export")
                continue
            for row, wrow in zip(out["rows"], block["rows"]):
                rctx = f"{ctx} {wrow['phenotype']}"
                for key in ("phenotype", "implication", "recommendation",
                            "classification"):
                    if row.get(key) != wrow[key]:
                        report.error(f"{rctx}: {key} is not what the export reads "
                                     f"(re-run tools/fetch/fetch_cpic.py)")
                if (row.get("assumes") or {}) != (wrow.get("assumes") or {}):
                    report.error(f"{rctx}: the co-dosed-gene assumption differs from "
                                 f"the export's")
                # Two citations per node: CPIC's implication, then its recommendation.
                # Both quotes must be the export's own strings, verbatim.
                srcs = row.get("sources") or []
                quotes = [s.get("quote") for s in srcs]
                if quotes != [wrow["implication"], wrow["recommendation"]]:
                    report.error(f"{rctx}: its {len(srcs)} citation(s) do not quote the "
                                 f"export's implication then its recommendation")
                    continue
                for i, src in enumerate(srcs):
                    if src.get("page") != block["guideline"]["id"]:
                        report.error(f"{rctx} sources[{i}]: page {src.get('page')!r} is "
                                     f"not the guideline id "
                                     f"{block['guideline']['id']!r}")
                    else:
                        n += 1
    n += check_cpic_enzyme_claims(report, want, drugs)
    check_cpic_enzyme_coverage(report, want, drugs)
    report.ok(f"{n} CPIC guidance quote(s) re-derived from the pinned export, "
              f"exact match")


def check_clinpgx_variants(report, meta, receptors):
    """Family 12, last part: ClinPGx's variant annotations, re-derived from their export.

    Every ``receptor_variant`` node is rebuilt from the pinned export by the generator's
    own reader (``clinpgx.variant_nodes``) and must match the emitted one field for
    field, its quotes included: ClinPGx's sentences are copied by code, so no step may
    trim or reword one. An export row no owner carries (an owner id the emitted data
    does not have) and an emitted node the export does not hold are both errors.
    """
    corpora = meta.get("source_corpora") or {}
    if "clinpgx" not in corpora:
        report.ok("no ClinPGx corpus to re-derive")
        return
    try:
        want = clinpgx.variant_nodes(
            clinpgx.read_export(clinpgx.export_path(str(REPO_ROOT))))
    except clinpgx.ExportError as exc:
        report.error(f"clinpgx: {exc}")
        return
    got = {("receptor", r["id"]): r.get("variants") or [] for r in receptors}
    got.update((("target", tid), t.get("variants") or [])
               for tid, t in (meta.get("drug_targets") or {}).items()
               if isinstance(t, dict) and t.get("type") != "receptor")
    keys = ("annotation", "variant", "genes", "level", "categories", "drugs",
            "drug_names", "phenotypes", "pmids", "genotypes", "population", "url")
    n = 0
    for owner in sorted(set(want) | {k for k, v in got.items() if v}):
        ctx = f"{owner[0]} {owner[1]} variants"
        if owner not in got:
            report.error(f"{ctx}: the export holds {len(want[owner])} annotation(s) for "
                         f"an owner the emitted data does not have (fix genes.GENE_OWNERS)")
            continue
        wants, emitted = want.get(owner, []), got[owner]
        if [w["annotation"] for w in wants] != [e.get("annotation") for e in emitted]:
            report.error(f"{ctx}: emitted annotations are not the export's (re-run "
                         f"tools/generate_data.py)")
            continue
        for w, e in zip(wants, emitted):
            for key in keys:
                if e.get(key) != w.get(key):
                    report.error(f"{ctx} {w['annotation']}: {key} is {e.get(key)!r}, not "
                                 f"{w.get(key)!r} as the export reads")
            quotes = [s.get("quote") for s in e.get("sources") or []]
            if quotes != [s["quote"] for s in w["sources"]]:
                report.error(f"{ctx} {w['annotation']}: its citations do not quote the "
                             f"export's genotype sentences verbatim")
                continue
            for i, src in enumerate(e["sources"]):
                if src.get("corpus") != "clinpgx" or src.get("page") != w["annotation"]:
                    report.error(f"{ctx} {w['annotation']} sources[{i}]: not cited to "
                                 f"clinpgx page {w['annotation']!r}")
                else:
                    n += 1
    report.ok(f"{n} ClinPGx variant quote(s) re-derived from the pinned export, "
              f"exact match")


def check_cpic_enzyme_coverage(report, want, drugs):
    """A gene CPIC doses a drug on, that the drug's enzyme list does not carry.

    Not an error, and deliberately not one: it means no corpus here states the route,
    which is a hole in the sources and not a mistake in the data. Flagging it is still
    worth a line, because the panel then shows a reader advice about their CYP2C19
    speed over an Enzymes section that never mentions CYP2C19, and because the enzyme
    list feeds the derived drug-drug edges, so a missing route quietly removes
    interactions nobody sees go missing.

    Clomipramine was exactly that case (fixed in 3.93.1: 11 interaction edges appeared
    with the row). This exists so the next one is reported rather than noticed by eye,
    since either side can produce it: a CPIC refresh adding a pair, or a CYP fetcher
    re-run dropping a row.
    """
    by_id = {d["id"]: d for d in drugs}
    for drug in sorted(want):
        doc = by_id.get(drug)
        if doc is None:
            continue
        have = {e["enzyme"] for e in doc.get("enzymes") or []}
        for block in want[drug]:
            if block["enzyme"] in have:
                continue
            report.warn(f"drug {drug}: CPIC doses it on {block['gene']}, which its "
                        f"enzyme list does not carry, so the guidance sits over a "
                        f"section that never names the gene (no corpus here states "
                        f"the route; see docs/SOURCING_GAPS.md)")


def check_cpic_enzyme_claims(report, want, drugs) -> int:
    """The enzyme routes CPIC's own wording states (see ``cpic.enzyme_claims_for``).

    An enzyme row sourced to CPIC is the one place this corpus is read for something
    other than guidance, so it gets the same treatment: re-derived from the export and
    compared. The gate runs both ways. A row the re-derivation does not produce is an
    error (it would mean we asserted a metabolic route CPIC never phrased), and a claim
    the re-derivation produces that no drug carries is checked only for its quote,
    because another corpus legitimately owns that (enzyme, role) pair already.
    """
    claims = {(drug, r["enzyme"]): r["sources"][0]["quote"]
              for drug, rows in cpic.enzyme_claims_for(want).items() for r in rows}
    n = 0
    for drug in drugs:
        for row in drug.get("enzymes") or []:
            src = (row.get("sources") or [{}])[0]
            if src.get("corpus") != "cpic":
                continue  # another corpus owns this row
            quote = src.get("quote")
            ctx = f"drug {drug['id']} enzymes[{row['enzyme']}]"
            if claims.get((drug["id"], row["enzyme"])) != quote:
                report.error(f"{ctx}: cites a CPIC sentence the export does not state "
                             f"for this pair (re-run tools/fetch/fetch_cpic.py)")
            elif row.get("role") != "substrate":
                report.error(f"{ctx}: CPIC's wording states a route, so the role can "
                             f"only be 'substrate', not {row.get('role')!r}")
            else:
                n += 1
    return n


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
        path = freshness.page_path(corpus, page)
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


def main():
    argv = sys.argv[1:]
    verbose = "--verbose" in argv
    argv = [a for a in argv if a != "--verbose"]
    only = argv == ["--only", "freshness"]
    if argv and not only:
        print("usage: check_data.py [--verbose] [--only freshness]", file=sys.stderr)
        return 2
    report = Report(verbose=verbose)
    print(f"neurarium data integrity check\nreading {DATA_DIR}")

    meta = load_meta(report)
    structures = load_jsonl(report, "structures")
    projections = expand_mirrored(load_jsonl(report, "projections"))
    circuits = load_jsonl(report, "circuits")
    projection_groups = load_jsonl(report, "projection_groups")
    receptors = load_jsonl(report, "receptors")
    drugs = load_jsonl(report, "drugs")
    metabolites = load_jsonl(report, "metabolites")
    addons = load_jsonl(report, "addons")

    # Rehydrate the externalized source quotes in place (collecting referenced +
    # dangling ids), so every check below sees the original inline source shape;
    # then report the quote table's referential integrity.
    quotes_by_id = load_quotes(report)
    referenced, dangling = set(), []
    rehydrate_quotes([meta, structures, projections, circuits, projection_groups,
                      receptors, drugs, metabolites, addons], quotes_by_id, referenced,
                     dangling)
    check_quotes(report, quotes_by_id, referenced, dangling)
    collections = [meta, structures, projections, circuits, projection_groups,
                   receptors, drugs, metabolites, addons]
    if only:
        check_freshness(report, meta, collections, metabolites=metabolites,
                        receptors=receptors)
        return _summary(report)

    args = (report, meta, structures, projections, circuits, projection_groups,
            receptors, drugs)
    check_duplicates(*args, metabolites)
    check_reachability(*args, addons, metabolites)
    check_todos(*args)
    check_provenance(*args, addons, metabolites)
    check_sources(report, meta, drugs, projections, structures, receptors, addons,
                  metabolites, circuits, projection_groups, CONTRADICTIONS)
    check_connectivity(report, structures, projections)
    check_ki_coverage(report, meta, drugs)
    check_flow_consistency(report, meta, drugs, projections, receptors)
    check_changelog(report)
    check_innervation(report, meta, structures, projections, receptors)
    check_baked_meshes(report, structures)
    check_enzyme_variability(report, meta, drugs)
    check_clinpgx_variants(report, meta, receptors)
    check_freshness(report, meta, collections, metabolites=metabolites,
                        receptors=receptors)
    return _summary(report)


def _summary(report):
    print(f"\nSummary: {report.errors} error(s), {report.warnings} warning(s)")
    if report.reviews and not report.verbose:
        print(f"         {report.reviews} review item(s) not listed "
              f"(intended-by-design eyeball lists; --verbose prints them)")
    if report.errors:
        print("FAILED: fix the errors above (warnings are informational).")
        return 1
    print("PASSED (warnings are informational).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
