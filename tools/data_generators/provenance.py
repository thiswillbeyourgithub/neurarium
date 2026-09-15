"""Source provenance: grades, corpora registry, and the source validators.

Every source / reference the viewer shows carries a ``provenance`` grade (llm /
sourced / verified). This module holds the grade vocabulary, the per-id override
registries, the ``SOURCE_CORPORA`` citation registry, and the validators that
normalize + check every quote-level source (drug bindings, Ki annotations,
expression locations). Kept dependency-free so any data module can import it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import pharmfreq

# ---------------------------------------------------------------------------
# Source provenance grades. Every source / reference the viewer shows carries a
# ``provenance`` level saying *how trustworthy its attribution is*, rendered as a
# small coloured pill (the palette + tooltips live in the viewer; the grade here
# is the data). Weakest to strongest:
#   "llm"      grey   - produced by an LLM from memory, unchecked against any
#                       document, so it may be a hallucination.
#   "sourced"  yellow - written by an LLM that was given the source document
#                       (e.g. the Stahl dump), but the specific claim was not
#                       quote-verified.
#   "verified" green  - an LLM extracted a quote, the quote was programmatically
#                       confirmed to be present in the source, and a separate LLM
#                       agreed it supports the claim. (Still LLM-driven, so not
#                       infallible: see the viewer tooltip; going further would
#                       need substantial, error-prone human review, out of scope.)
# The *absence* of any source/reference is rendered as the orange "TODO" pill
# instead; it is not one of these stored grades. Everything currently grades as
# "llm" (the default) until individually upgraded.
PROVENANCE_LEVELS: tuple[str, ...] = ("llm", "sourced", "verified")
DEFAULT_PROVENANCE = "llm"

# The model that extracted + judged a *verified* quote, recorded on the quote node
# (``llm`` metadata field, see quote_table.py) so the reader can weigh a quote by the
# capability of the model that sourced it. Optional: a quote authored before this was
# tracked (or a non-LLM deterministic source like Allen's PACall) simply omits it and
# reads as "unknown" until a recheck stamps it. Any new sourcing/recheck pass MUST set it.
SOURCING_LLMS: tuple[str, ...] = ("haiku", "sonnet", "opus")

# How a quote came to be on the page it is cited from, and what checked it on the way.
# The grade above says how well a claim is backed; this says by what *mechanism*, which
# is a different question with a different failure mode: a green pill earned by a model
# reading a book is not the same evidence as one earned by a parser copying a table cell,
# and a reader deserves to be told which they are looking at.
#
# Only ONE bit of this is authored, because only one bit is unrecoverable: who found the
# sentence. ``EXTRACTIONS`` is that bit, stamped by the pass that wrote the source.
# Everything else the emitted data already knows: the verbatim gate runs over every paged
# corpus, and the ``llm`` stamp says whether a second model judged the quote. So the
# chain is *derived* (see :func:`quote_pipeline`), never a second thing to keep in step.
EXTRACTIONS: tuple[str, ...] = ("code", "llm")
DEFAULT_EXTRACTION = "llm"

# pipeline key -> its chain of custody, as ordered step keys. Emitted whole into
# ``meta.quote_pipelines`` and rendered by the viewer at the bottom of every source
# tooltip, so a new pipeline is one entry plus its translations and never a viewer edit.
# The step keys are i18n keys (``quotechain.<step>``), like every other emitted vocabulary.
QUOTE_PIPELINES: dict[str, tuple[str, ...]] = {
    # A parser copied the value out of a machine-readable store (a CSV row, an API
    # response, a wiki table cell) and code confirmed the copy against the stored page.
    "machine": ("raw_data", "extract_code", "gate", "neurarium"),
    # As above, but a model then decided WHICH claim the copied line backs (GtoPdb's
    # tissue comments, corpus #7: confirm-only, it can never add or drop a region).
    "machine_judged": ("raw_data", "extract_code", "gate", "judge_llm", "neurarium"),
    # Code read a labelled line off a page of prose (Stahl prints "Brands: ..." and
    # "Neuroscience-based Nomenclature: ..." in a fixed shape), so no model chose the
    # sentence even though the corpus is a book.
    "page_code": ("page", "extract_code", "gate", "neurarium"),
    "page_code_judged": ("page", "extract_code", "gate", "judge_llm", "neurarium"),
    # The four-step pipeline: a model reads the page and proposes a sentence, code
    # confirms the sentence is verbatim on that page, and a second model that has never
    # seen the first one's reasoning judges whether it really supports the claim.
    "page_llm_judged": ("page", "extract_llm", "gate", "judge_llm", "neurarium"),
    # The same, with the judging step still missing. This is a state to fix, not a tier
    # to ship: ``check_data.py`` fails on it (see CLAUDE.md "The sourcing model").
    "page_llm": ("page", "extract_llm", "gate", "neurarium"),
}

# The pipelines whose quote a model chose. These are the ones the judging rule binds:
# a sentence a model picked out of prose is the one that can be picked wrongly.
LLM_PICKED_PIPELINES = ("page_llm", "page_llm_judged")


def quote_extraction(corpus: str, stated: str | None = None) -> str:
    """Who found a quote from ``corpus``, unless the pass that wrote it stated otherwise.

    A ``machine`` corpus has no prose to read: every quote from it is a record line a
    parser copied out of a CSV, an API response or a wiki table, so the corpus answers
    for its own quotes and no authoring site has to remember to. Everywhere else the
    honest default is that a model read the page and chose the sentence.
    """
    if stated:
        return stated
    return "code" if SOURCE_CORPORA.get(corpus, {}).get("machine") else DEFAULT_EXTRACTION


def quote_pipeline(corpus: str, extraction: str, llm: str | None) -> str:
    """The pipeline key for one citation: where it came from, who found it, who judged it.

    Three bits, and none of them is a second thing to keep in step with the data: the
    corpus says whether there was a page to read at all, ``extraction`` is stamped by the
    pass that wrote the source (see :func:`quote_extraction`), and ``llm`` is the sourcing
    stamp, which exists exactly when a second model judged the quote.
    """
    if extraction == "code":
        key = "machine" if SOURCE_CORPORA.get(corpus, {}).get("machine") else "page_code"
    else:
        key = "page_llm"
    return f"{key}_judged" if llm else key



# Per-link provenance overrides for the *wikipedia* references (which are bare URL
# strings, not ``{citation, url}`` objects, so they have nowhere inline to carry a
# grade). Keyed by the owner's id: a structure *base* id, a receptor id, a
# DRUG_TARGETS key, or a drug id. Anything absent defaults to
# :data:`WIKIPEDIA_DEFAULT_PROVENANCE` below; upgrade an individual link to
# ``verified`` here once it is confirmed to be the canonical article, keeping the
# grading in the data rather than in code.
WIKIPEDIA_PROVENANCE: dict[str, str] = {}

# A *present* wikipedia link is itself a real reference: a CC BY-SA article the
# viewer can open (and live-fetches the lead from, grading that description
# "sourced"). So a reference link defaults to "sourced", NOT the bare "llm": an LLM
# chose which article, but the link points at a genuine source document, not a
# from-memory claim that could be a hallucination (the "llm"/"?" pill, whose tooltip
# says "may be a hallucination", was both wrong and confusing next to a working
# link). The absence of a link is still rendered as the orange NOSOURCE pill by the
# viewer, not as a grade here.
WIKIPEDIA_DEFAULT_PROVENANCE = "sourced"


# Verified quote-source constructors: build the ``{corpus, page, quote}`` source
# shape for a book corpus, pre-graded ``verified`` (the quote is confirmed on the
# cited page by ``check_data.py``). Shared by every data module that cites a book.
def _kandel(page: int, quote: str) -> dict[str, Any]:
    """A verified Kandel quote-source (the drug-binding ``{corpus,page,quote}`` shape)."""
    return dict(corpus="kandel", page=page, provenance="verified", quote=quote)


def _nieuwenhuys(page: int, quote: str) -> dict[str, Any]:
    """A verified Nieuwenhuys atlas quote-source (``page`` = the PDF/.md page number)."""
    return dict(corpus="nieuwenhuys", page=page, provenance="verified", quote=quote)


def _stahl_ess(page: int, quote: str) -> dict[str, Any]:
    """A verified Stahl Essential Psychopharmacology quote-source."""
    return dict(corpus="stahl_essential", page=page,
                provenance="verified", quote=quote)


def _provenance(level: str, what: str) -> str:
    """Validate a provenance grade against :data:`PROVENANCE_LEVELS` (typo guard)."""
    if level not in PROVENANCE_LEVELS:
        raise ValueError(
            f"{what} has unknown provenance {level!r}; "
            f"expected one of {PROVENANCE_LEVELS}")
    return level


def _lookup_provenance(table: dict[str, str], owner_id: str, what: str,
                       default: str = DEFAULT_PROVENANCE) -> str:
    """Grade for ``owner_id`` from an override ``table``, validated.

    The single core behind every per-id provenance map (wikipedia references,
    receptor / target / structure classifications): look the id up, fall back to
    ``default`` (``llm`` unless overridden, e.g. wikipedia links default
    ``sourced``), and validate so an upgraded grade can't be a typo.
    """
    return _provenance(table.get(owner_id, default), what)


def _wiki_provenance(owner_id: str) -> str:
    """Provenance grade for an owner's wikipedia reference (a structure base /
    receptor id / DRUG_TARGETS key / drug id); a present link defaults to
    ``sourced`` (see :data:`WIKIPEDIA_DEFAULT_PROVENANCE`)."""
    return _lookup_provenance(
        WIKIPEDIA_PROVENANCE, owner_id, f"wikipedia reference for {owner_id!r}",
        default=WIKIPEDIA_DEFAULT_PROVENANCE)


# Per-id provenance overrides for the *classification* claims of a receptor (its
# neurotransmitter / mechanism class / sign / synaptic site), a non-receptor drug
# target (its type / system / region footprint) and a brain structure (its
# existence / group / position), all authored from general / Wikipedia / textbook
# knowledge, so they default to the honest ``"llm"`` grade (LLM-only, unchecked).
# Keyed by receptor id / DRUG_TARGETS key / structure *base* id; upgrade an entry
# here as its claim is checked against a document (raise to ``"sourced"`` /
# ``"verified"``), keeping the grading in the data, not in code. Empty for now
# (everything grades as ``"llm"``). A receptor's *expression regions* are graded
# separately, per region (see RECEPTOR_LOCATION_SOURCES); this override covers only
# the mechanism classification, not "which regions express it".
RECEPTOR_PROVENANCE: dict[str, str] = {}
TARGET_PROVENANCE: dict[str, str] = {}
STRUCTURE_PROVENANCE: dict[str, str] = {}
# The same, for a drug's *class* classification (its ``categories`` set, e.g. "SSRI"):
# the claim "this drug belongs to class X" is a node in its own right (kind
# ``drug_categories``), one per drug, graded like the receptor/target classification.
# Authored from general knowledge, so default ``"llm"``; keyed by drug id. A drug may
# additionally carry quote-level ``category_sources`` in tools/data/drugs_data.jsonl, which
# upgrade the emitted grade (mirror of the target classification's optional quotes).
DRUG_CATEGORY_PROVENANCE: dict[str, str] = {}
# Manual per-target polarity-grade overrides (mirror TARGET_PROVENANCE). Empty:
# grade defaults to `llm`, upgraded only by a TARGET_POLARITY_QUOTES quote.
TARGET_POLARITY_PROVENANCE: dict[str, str] = {}

# Per-region provenance for a receptor's *expression locations* ("Found in"): the
# claim "receptor R is expressed in region B" is distinct from R's mechanism
# classification and is authored from general knowledge, so every location defaults
# to ``"llm"`` (unsourced). This registry upgrades an individual (receptor, region)
# to a quote-source: ``{receptor_id: {base: [ {corpus, page, quote, provenance} ]}}``.
# ``_receptor_record`` validates each base is one of that receptor's own locations
# and emits the sources; the viewer shows a per-region pill and the coverage tally
# counts each region separately. Empty for now: no expression atlas is wired yet, so
# every "Found in" region is honestly ``"llm"``. Add entries as regions are sourced.
RECEPTOR_LOCATION_SOURCES: dict[str, dict[str, list[dict[str, Any]]]] = {}

# The same, for a non-receptor drug target's *expression regions* ("Found in"): the
# claim "target T is found in region B" is a distinct node from T's type/system
# classification, so each region grades separately (default ``"llm"``). Keyed by
# DRUG_TARGETS id: ``{target_id: {base: [ {corpus, page, quote, provenance} ]}}``.
# ``_build_drug_targets`` validates each base is one of that target's own regions and
# emits ``location_sources``; the viewer shows a per-region pill and the coverage
# tally counts each region (kind ``target_locations``). Empty for now. Add entries as
# a target's regions are sourced.
TARGET_LOCATION_SOURCES: dict[str, dict[str, list[dict[str, Any]]]] = {}


# Relative expression *density* across an owner's regions: the claim "receptor R is not
# merely present in these regions, it is concentrated in these ones". A separate node kind
# (``receptor_density`` / ``target_density``) from the per-region presence nodes, and ONE
# node per owner rather than one per region: it is a single measurement over the whole
# region set, so per-region tallying would inflate the coverage headline with ~1000
# uniformly-verified nodes. Shape: ``{owner_id: {reliability, profile {base: z},
# sources [...]}}``. Machine-written (Allen AHBA, see below); empty when that file is absent.
RECEPTOR_DENSITY: dict[str, dict[str, Any]] = {}
TARGET_DENSITY: dict[str, dict[str, Any]] = {}
# The cross-donor-agreement floor a profile had to clear to be published at all. Carried
# from the fetcher through the data (rather than restated in the viewer) so the figure the
# panel quotes is the one that actually filtered. None when no density file is present.
DENSITY_MIN_RELIABILITY: float | None = None


def _merge_external_density() -> None:
    """Merge ``tools/generated_cache/expression_density.json`` into the two registries above.

    Written by ``tools/fetch/fetch_allen.py`` -> ``tools/sourcing/apply_expression_density.py``
    (the Allen microarray intensities behind the same PACall booleans that source the
    presence nodes). A missing file is fine: no owner then carries a density, exactly as
    before the pass existed."""
    src = Path(__file__).resolve().parent.parent / "generated_cache" / "expression_density.json"
    if not src.exists():
        return
    global DENSITY_MIN_RELIABILITY
    data = json.loads(src.read_text(encoding="utf-8"))
    RECEPTOR_DENSITY.update(data.get("receptors") or {})
    TARGET_DENSITY.update(data.get("targets") or {})
    DENSITY_MIN_RELIABILITY = data.get("min_reliability")


# Machine-written metabolizer-status profiles: ``{enzyme_id: {"gene", "profile":
# {group: {phenotype: frequency}}, "sources": [...]}}``. One node per enzyme (kind
# ``enzyme_variability``), not one per population group, for the same reason a density
# profile is one node and not one per region: it is a single published aggregation
# ranking the groups against each other. Written by ``tools/fetch/fetch_pharmfreq.py``
# (corpus #13); empty when that file is absent, in which case no enzyme carries one.
ENZYME_VARIABILITY: dict[str, dict[str, Any]] = {}


# ``{file name: sha256}`` for the committed PharmFreq export the cache above was built
# from, filled by the merge below and emitted onto the corpus record so `check_data.py`
# can re-derive every profile straight from the pinned files.
ENZYME_VARIABILITY_PINS: dict[str, str] = {}


def _merge_enzyme_variability() -> None:
    """Merge ``tools/generated_cache/enzyme_variability.json`` into the registry above.

    The cache pins the sha256 of every source TSV it was built from, and this is where
    that pin is cashed in: the export is committed (see `pharmfreq.py`), so a mismatch
    means the cache and the files under `tools/data/pharmfreq/` have parted ways, and
    the quotes below would then carry numbers no committed measurement backs. Loud, at
    generation time, rather than a green check nobody can trace.
    """
    src = Path(__file__).resolve().parent.parent / "generated_cache" / "enzyme_variability.json"
    if not src.exists():
        return
    cache = json.loads(src.read_text(encoding="utf-8"))
    ENZYME_VARIABILITY.update(cache.get("enzymes") or {})
    pins = cache.get("export_sha256") or {}
    root = Path(__file__).resolve().parent.parent.parent
    export = root / pharmfreq.EXPORT_DIR
    for name, want in sorted(pins.items()):
        path = export / name
        if not path.exists():
            raise ValueError(f"enzyme_variability.json pins {name}, which is not in "
                             f"{pharmfreq.EXPORT_DIR}: re-run "
                             f"tools/fetch/fetch_pharmfreq.py")
        got = pharmfreq.sha256(str(path))
        if got != want:
            raise ValueError(f"{pharmfreq.EXPORT_DIR}/{name} has changed since the "
                             f"enzyme variability cache was built ({got[:12]} != "
                             f"{want[:12]}): re-run tools/fetch/fetch_pharmfreq.py")
    for name in pharmfreq.export_files(str(export)):
        if name not in pins:
            raise ValueError(f"{pharmfreq.EXPORT_DIR}/{name} is not pinned by "
                             f"enzyme_variability.json: re-run "
                             f"tools/fetch/fetch_pharmfreq.py")
    ENZYME_VARIABILITY_PINS.update(pins)


# Machine-written *classification* sources, the mechanism counterpart of the location
# registries above. A receptor's classification is four independent graded sub-claims,
# so this is keyed per attribute: ``{receptor_id: {attr: [source, ...]}}`` for
# ``receptor_class`` / ``sign`` (GtoPdb states neither ``family`` nor a pre/post site,
# so those attributes never appear here). A non-receptor target's single classification
# node takes a flat list: ``{target_id: [source, ...]}``. These *add to* whatever a book
# quote already backs rather than replacing it, so a doubly-sourced attribute shows both.
RECEPTOR_CLASSIFICATION_SOURCES: dict[str, dict[str, list[dict[str, Any]]]] = {}
TARGET_CLASSIFICATION_SOURCES: dict[str, list[dict[str, Any]]] = {}


def _merge_external_classification_sources() -> None:
    """Merge ``tools/generated_cache/classification_sources.json`` into the two
    registries above.

    Written by ``tools/fetch/fetch_gtopdb_class.py`` ->
    ``tools/sourcing/apply_classification_sources.py`` (corpus #12 ``gtopdb_class``:
    GtoPdb's ``type`` field and its transduction table, applied confirm-only). A
    missing file is fine: every mechanism attribute then grades as it did before the
    pass existed."""
    src = (Path(__file__).resolve().parent.parent / "generated_cache"
           / "classification_sources.json")
    if not src.exists():
        return
    data = json.loads(src.read_text(encoding="utf-8"))
    for owner, per_attr in (data.get("receptors") or {}).items():
        RECEPTOR_CLASSIFICATION_SOURCES.setdefault(owner, {}).update(per_attr)
    for owner, srcs in (data.get("targets") or {}).items():
        TARGET_CLASSIFICATION_SOURCES.setdefault(owner, []).extend(srcs)


def _merge_external_location_sources() -> None:
    """Merge author-side sourced expression locations from ``tools/generated_cache/location_sources.json``
    into the two registries above.

    That file is machine-written by the expression-sourcing pipeline (fetch ->
    judge -> ``tools/sourcing/apply_location_sources.py``, e.g. from GtoPdb tissue
    distributions), so the bulk of per-region sources lives in a sibling JSON rather
    than inline here (mirroring ``drugs_data.jsonl`` / ``*_images_sources.json``); the
    in-code dicts above stay the place for any hand-authored override. Shape:
    ``{"receptors": {rid: {base: [source, ...]}}, "targets": {tid: {base: [...]}}}``.
    An external entry wins per (owner, base). A missing file is fine (nothing sourced),
    so the generator still runs on a checkout without it."""
    src = Path(__file__).resolve().parent.parent / "generated_cache" / "location_sources.json"
    if not src.exists():
        return
    data = json.loads(src.read_text(encoding="utf-8"))
    for owner, per_base in (data.get("receptors") or {}).items():
        RECEPTOR_LOCATION_SOURCES.setdefault(owner, {}).update(per_base)
    for owner, per_base in (data.get("targets") or {}).items():
        TARGET_LOCATION_SOURCES.setdefault(owner, {}).update(per_base)


_merge_external_location_sources()
_merge_external_density()
_merge_enzyme_variability()
_merge_external_classification_sources()


def _receptor_provenance(receptor_id: str) -> str:
    """Provenance grade for a receptor's classification claims (default ``llm``)."""
    return _lookup_provenance(
        RECEPTOR_PROVENANCE, receptor_id,
        f"receptor classification for {receptor_id!r}")


def _target_provenance(target_id: str) -> str:
    """Provenance grade for a non-receptor target's classification (default ``llm``)."""
    return _lookup_provenance(
        TARGET_PROVENANCE, target_id, f"target classification for {target_id!r}")


def _target_polarity_provenance(target_id: str) -> str:
    """Provenance grade for a target's tone-polarity claim (default ``llm``)."""
    return _lookup_provenance(
        TARGET_POLARITY_PROVENANCE, target_id,
        f"target polarity for {target_id!r}")


def _structure_provenance(base_id: str) -> str:
    """Provenance grade for a structure's anatomy claim (default ``llm``)."""
    return _lookup_provenance(
        STRUCTURE_PROVENANCE, base_id, f"structure anatomy for {base_id!r}")


def _location_sources(
        registry: dict[str, dict[str, list[dict[str, Any]]]], owner_id: str,
        regions: list[str], label: str) -> dict[str, list[dict[str, Any]]]:
    """Emitted per-region ``location_sources`` (``{base: [quote-source, ...]}``) for
    an owner whose "Found in" regions are each a separately-graded expression node: a
    receptor (:data:`RECEPTOR_LOCATION_SOURCES`) or a non-receptor drug target
    (:data:`TARGET_LOCATION_SOURCES`).

    Every cited base must be one of the owner's own ``regions`` (a stray base is a
    typo that would grade a region the owner does not claim), and each source is
    validated like any other quote-level source. Returns ``{}`` when nothing is
    sourced (the common case today), so the field is simply omitted and every region
    grades as ``llm``. ``label`` names the owner kind for error messages."""
    per_base = registry.get(owner_id)
    if not per_base:
        return {}
    known = set(regions)
    out: dict[str, list[dict[str, Any]]] = {}
    for base, sources in per_base.items():
        if base not in known:
            raise KeyError(
                f"{label} {owner_id!r} has location sources for {base!r}, "
                f"which is not one of its regions {sorted(known)}")
        out[base] = _quote_sources(
            sources, f"{label} {owner_id!r} location {base!r}")
    return out


def _density_node(registry: dict[str, dict[str, Any]], owner_id: str,
                  regions: list[str], label: str) -> dict[str, Any]:
    """Emitted ``density`` for an owner whose regions carry a *relative* expression
    profile (:data:`RECEPTOR_DENSITY` / :data:`TARGET_DENSITY`), or ``{}`` when it has none.

    ``{reliability, profile {base: z}, grade, sources}``: one graded node (see the registry
    comment for why it is one node and not one per region). ``reliability`` is the
    cross-donor agreement of the profile, carried so the viewer can show *how much to trust
    the shape* rather than presenting every profile as equally solid. Every ranked base must
    be one of the owner's own ``regions``, so a profile can never imply an expression site
    the owner does not claim."""
    entry = registry.get(owner_id)
    if not entry:
        return {}
    known = set(regions)
    profile = entry.get("profile") or {}
    stray = sorted(set(profile) - known)
    if stray:
        raise KeyError(
            f"{label} {owner_id!r} has a density profile for {stray}, "
            f"which is not among its regions {sorted(known)}")
    sources = _quote_sources(entry.get("sources") or [], f"{label} {owner_id!r} density")
    grade = DEFAULT_PROVENANCE
    if sources:
        grade = max((s["provenance"] for s in sources), key=lambda p: _GRADE_RANK[p])
    return {"reliability": entry["reliability"], "donors": entry["donors"],
            "profile": {b: profile[b] for b in sorted(profile, key=lambda k: -profile[k])},
            "grade": grade, "sources": sources}


# The constant source backing every drug record (the user-verified fair-use
# citation). Per-drug specifics (the binding profile) come from this single book;
# each drug additionally carries its own ``wikipedia`` link for quick reference.
# ``provenance`` grades the citation (see PROVENANCE_LEVELS): the drug bindings
# were extracted by an LLM given the Stahl dump but were not quote-verified, so
# they would warrant "sourced"; kept at the conservative "llm" default for now.


# Source corpora that the *per-claim* drug sources cite, keyed by a short id. A
# claim's source is ``{corpus, page, quote, provenance}``: ``quote`` is the
# verbatim snippet supporting the claim, ``page`` locates it inside the corpus,
# and ``tools/check_data.py`` confirms (when the corpus's pages are present) that
# the quote really appears on that page, which is what makes a ``"verified"``
# grade trustworthy. The design is source-agnostic: Stahl is the first corpus,
# more can be added here without touching the schema. ``pages_dir`` is an
# author-side path (relative to the repo root) holding one ``<page>.md`` per page
# (see ``data_sources/books/stahl/`` in CLAUDE.local.md); it is emitted into ``meta.json`` so the
# checker is data-driven, and is simply absent on a checkout without that
# (uncommitted, large) source material, in which case the quote-in-page check is
# skipped while the structural checks still run. ``url`` is *optional* and carried
# only by the web corpora that have a free landing page: a copyrighted book has no
# such link, and the provenance pill (not a link) is what conveys the grade, so the
# key is omitted rather than filled with a placeholder.
SOURCE_CORPORA: dict[str, dict[str, str]] = {
    "stahl": {
        # Label for the per-claim tooltip ref ("<ref>, p. N"). The full book title
        # + edition, not a bare "Stahl", so a page citation is unambiguous on its
        # own (which Stahl, which edition) without needing the full bibliographic
        # citation below.
        "ref": "Prescriber's Guide: Stahl's Essential Psychopharmacology, 8th ed.",
        "citation": "Stahl SM. Prescriber's Guide: Stahl's Essential "
                    "Psychopharmacology. 8th ed. Cambridge University Press; 2024.",
        "pages_dir": "data_sources/books/stahl/pages",
    },
    "kandel": {
        # Anatomy/pathway corpus (the projection claims, currently LLM-only, are
        # quote-verified against this). Full title + edition so a page citation is
        # unambiguous on its own.
        "ref": "Kandel, Principles of Neural Science, 6th ed.",
        "citation": "Kandel ER, Koester JD, Mack SH, Siegelbaum SA, eds. "
                    "Principles of Neural Science. 6th ed. McGraw Hill; 2021.",
        "pages_dir": "data_sources/books/eric_kandel/pages",
    },
    "stahl_essential": {
        # Mechanism/receptor corpus: the receptor + non-receptor-target
        # classification claims are quote-verified against this.
        "ref": "Stahl's Essential Psychopharmacology: Neuroscientific Basis, "
               "5th ed.",
        "citation": "Stahl SM. Stahl's Essential Psychopharmacology: "
                    "Neuroscientific Basis and Practical Applications. 5th ed. "
                    "Cambridge University Press; 2021.",
        "pages_dir": "data_sources/books/stahl_essential_pharmacology/pages",
    },
    "carlat": {
        # Second drug corpus: cross-sources drug bindings Stahl did not state.
        "ref": "Carlat Medication Fact Book for Psychiatric Practice, 7th ed.",
        "citation": "Carlat DJ. The Carlat Medication Fact Book for Psychiatric "
                    "Practice. 7th ed. Carlat Publishing; 2024.",
        "pages_dir": "data_sources/books/carlat_medication/pages",
    },
    "nieuwenhuys": {
        # Systematic neuroanatomy/connectivity corpus: backs region-anatomy +
        # projection claims Kandel does not state in prose (the claustrum, the
        # fornix, commissures). Page numbers are the PDF's 1-based pages (the .md
        # file names), which run a few ahead of the printed page numbers.
        "ref": "Nieuwenhuys, Voogd & van Huijzen, The Human Central Nervous "
               "System, 4th ed.",
        "citation": "Nieuwenhuys R, Voogd J, van Huijzen C. The Human Central "
                    "Nervous System. 4th ed. Springer; 2008.",
        "pages_dir": "data_sources/books/nieuwenhuys_atlas/pages",
    },
    "gtopdb": {
        # Expression/localization corpus: the IUPHAR/BPS Guide to Pharmacology
        # per-target "Tissue Distribution" statements, backing a receptor/target
        # expression-region claim ("R is found in region B"). Fetched from the GtoPdb
        # web service (tools/fetch/fetch_gtopdb.py) and cached author-side as one page per
        # target id: each `location_sources` quote is a verbatim `tissue` string and
        # its `page` is the GtoPdb target id, so the normal verbatim-quote gate
        # applies unchanged. Many entries are rat/mouse, so each source carries a
        # `species` (the viewer flags a non-human claim; see _quote_sources).
        "ref": "IUPHAR/BPS Guide to Pharmacology (GtoPdb), tissue distribution",
        "citation": "Harding SD, Armstrong JF, Faccenda E, et al. The IUPHAR/BPS "
                    "Guide to Pharmacology. Nucleic Acids Res. "
                    "guidetopharmacology.org.",
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "data_sources/gtopdb/pages",
        "machine": True,
    },
    "pdsp_ki": {
        # Binding-affinity corpus: measured Ki (nM) values backing a drug binding's
        # `ki` annotation. Unlike the book corpora this is a single CSV of assay
        # rows, not paged text, so it has no `pages_dir`; check_data confirms a
        # cited Ki id/value against the `csv` file instead (author-side, skipped on
        # a clone without it, like the quote gate). See tools/fetch/fetch_ki.py +
        # data_sources/books/pdsp_ki/README.md.
        "ref": "PDSP Ki Database (NIMH PDSP)",
        "citation": "NIMH Psychoactive Drug Screening Program (PDSP) Ki Database, "
                    "directed by Bryan L. Roth, University of North Carolina at "
                    "Chapel Hill.",
        "url": "https://pdspdb.unc.edu/databases/kidb.php",
        "csv": "data_sources/books/pdsp_ki/KiDatabase.csv",
        "machine": True,
    },
    "allen_ahba": {
        # Expression corpus: the Allen Human Brain Atlas microarray, backing a
        # receptor/target expression-region claim ("X is found in region B") the
        # GtoPdb tissue comments could not reach (esp. the non-receptor targets +
        # the deep nuclei). tools/fetch/fetch_allen.py aggregates Allen's PACall
        # present/absent boolean per (gene, region) across the 6 donors and writes one
        # cached page per gene (`page` = the HGNC gene symbol): each `location_sources`
        # quote is a verbatim presence line, so the normal verbatim-quote gate applies
        # unchanged. All 6 donors are human, so every quote carries `species: Human`.
        # Licence: copyright-reserved, non-commercial research use with required
        # citation; we vendor only the cited slice, never the atlas.
        "ref": "Allen Human Brain Atlas, microarray (Hawrylycz et al. 2012)",
        "citation": "Hawrylycz MJ, Lein ES, Guillozet-Bongaarts AL, et al. An "
                    "anatomically comprehensive atlas of the adult human brain "
                    "transcriptome. Nature. 2012;489(7416):391-399. "
                    "human.brain-map.org.",
        "url": "https://human.brain-map.org/",
        "pages_dir": "data_sources/allen/pages",
        "machine": True,
    },
    "wikipedia_pharm": {
        # Corpus #9: a drug's English Wikipedia article, stored whole (article text +
        # every table flattened to rows), so one corpus backs three different claims:
        # a binding `ki` where PDSP (corpus #5) has none (a fallback, never overriding
        # a measured assay), an active metabolite's own bindings, and a drug's
        # metabolising-enzyme roles for the 149 drugs outside Stahl's roster.
        # tools/fetch/fetch_wikipedia_pharmacology.py fetches the article pinned to a
        # revision id and writes the whole page as author-side text; a source's `page`
        # is the article slug and its `quote` is a verbatim line of it (a table row, a
        # prose sentence, the drugbox metabolism row), so the normal verbatim-quote
        # gate applies unchanged (author-side, skipped on a clone lacking
        # data_sources/wikipedia/, like the book corpora). Wikipedia is a tertiary
        # source citing the primary literature: the grade attests the quote is really
        # on the page, and this corpus label makes the source's tier explicit.
        "ref": "Wikipedia (English), drug article (pharmacology sections)",
        "citation": "Wikipedia contributors. Pharmacology sections of the cited drug "
                    "article. Wikipedia, The Free Encyclopedia. "
                    "en.wikipedia.org (revision pinned per citation).",
        "url": "https://en.wikipedia.org/",
        "pages_dir": "data_sources/wikipedia/pages",
    },
    "wikipedia_fr": {
        # Brand-name corpus #10: the French Wikipedia article, the source for a drug's
        # European / French commercial brands (`eu`/`fr` region). The FR infobox carries
        # only chemistry, so the trade names live in the prose ("commercialisée sous les
        # noms Xeroquel, Seroquel..."); tools/fetch/fetch_brand_names.py stores the whole
        # FR article author-side (pinned to a revision id) and an LLM reads the candidate
        # sentences, apply_brand_names.py quote-gating each returned brand verbatim on the
        # page. A brand source's `page` is the FR article slug, its `quote` the brand name,
        # so the normal verbatim-quote gate applies (author-side, skipped on a clone lacking
        # data_sources/wikipedia/pages_fr, like the book corpora). Tertiary source: the
        # grade attests the name is really on the page, the label makes the tier explicit.
        "ref": "Wikipedia (French), drug article (commercial names)",
        "citation": "Wikipedia contributors. Commercial names of the cited drug article. "
                    "Wikipedia, l'encyclopedie libre. fr.wikipedia.org (revision pinned "
                    "per citation).",
        "url": "https://fr.wikipedia.org/",
        "pages_dir": "data_sources/wikipedia/pages_fr",
    },
    "gtopdb_ki": {
        # Binding corpus #11: GtoPdb's *other* half. Where corpus #7 uses its tissue
        # API for expression regions, this uses its hand-curated ligand-interaction
        # table, which carries a measured affinity, a curated direction and a PubMed
        # id per row. It complements PDSP (#5) where a radioligand panel structurally
        # cannot reach: targets PDSP does not assay (GABA-A benzodiazepine site,
        # MAO-A/B, acetylcholinesterase, orexin, melatonin, SV2A) and the *direction*
        # of an affinity_only binding. PDSP still wins on a Ki both have.
        # tools/fetch/fetch_gtopdb_ki.py flattens each matched compound's rows into
        # one author-side page (`page` = the GtoPdb ligand slug, `quote` = one verbatim
        # row line), so the normal verbatim-quote gate applies unchanged (skipped on a
        # clone lacking data_sources/gtopdb/pages_ki, like the book corpora).
        # Licence: contents CC BY-SA 4.0, database ODbL; both need attribution, which
        # the citation below carries into every pill tooltip.
        "ref": "IUPHAR/BPS Guide to Pharmacology (GtoPdb), ligand interactions",
        "citation": "Harding SD, Armstrong JF, Faccenda E, et al. The IUPHAR/BPS "
                    "Guide to Pharmacology: ligand-target interaction table. "
                    "guidetopharmacology.org (CC BY-SA 4.0 / ODbL).",
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "data_sources/gtopdb/pages_ki",
        "machine": True,
    },
    "gtopdb_class": {
        # Classification corpus #12: GtoPdb's third slice (after #7 tissue distribution
        # and #11 ligand interactions). Two structured fields per target back a
        # *mechanism* node no book prose states uniformly: its `type` (gpcr / lgic /
        # vgic / enzyme), which is a receptor's `receptor_class` and a non-receptor
        # target's `type`; and its transduction table (transducer family + effectors),
        # from which a GPCR's `sign` is mapped under the narrow, confirm-only rule in
        # tools/sourcing/apply_classification_sources.py (GtoPdb states the
        # transduction, never a sign, so the quote carried into the pill is the
        # transduction line itself and the reader can see what backs it).
        # tools/fetch/fetch_gtopdb_class.py flattens both into one author-side page per
        # target id (`page` = the GtoPdb target id, `quote` = one verbatim line), so the
        # normal verbatim-quote gate applies unchanged (skipped on a clone lacking
        # data_sources/gtopdb/pages_class, like every other pages*/). GtoPdb has no
        # pre/post-synaptic field, so `synaptic` is out of this corpus's reach.
        # Licence: contents CC BY-SA 4.0, database ODbL, as for #7 and #11.
        "ref": "IUPHAR/BPS Guide to Pharmacology (GtoPdb), target classification",
        "citation": "Harding SD, Armstrong JF, Faccenda E, et al. The IUPHAR/BPS "
                    "Guide to Pharmacology: target type and transduction. "
                    "guidetopharmacology.org (CC BY-SA 4.0 / ODbL).",
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "data_sources/gtopdb/pages_class",
        "machine": True,
    },
    "pharmfreq": {
        # Enzyme variability corpus #13: how fast people clear a drug through one
        # enzyme, and how common each speed is per population group. The only corpus
        # here whose subject is *people* rather than molecules or anatomy, which is
        # why it backs its own node kind (`enzyme_variability`) instead of grading an
        # existing one: nothing else this dataset states about CYP2D6 varies by who
        # is taking the drug.
        # tools/fetch/fetch_pharmfreq.py reshapes the hand-downloaded "Metabolizer
        # status tool" export (`page` = the HGNC gene symbol, `quote` = the one line
        # carrying the whole profile, as in the Allen density profiles), so the gate
        # covers the numbers a reader judges the claim by. Deterministic, no judge:
        # PharmFreq publishes the aggregate and we only reshape it.
        # The one corpus with `tsv_dir` and no `pages_dir`, for two reasons that go
        # together. Its export is small and freely redistributable, so it is COMMITTED
        # rather than kept author-side, and the gate therefore runs on every clone
        # instead of being skipped-and-warned. And the sentence we quote is one we
        # compose out of that table, so looking for it on a page we also wrote would
        # be circular: `check_data.py` instead pins each file by sha256 and rebuilds
        # the sentence from it (see data_generators/pharmfreq.py).
        # Two isoforms this dataset leans on hardest, CYP3A4 and CYP1A2, have no
        # profile in the tool, so their absence is a gap in the source, not a claim
        # that they do not vary.
        "ref": "PharmFreq, metabolizer status by population",
        "citation": "PharmFreq: a global genetic variation database for "
                    "pharmacogenomics. pharmfreq.com, metabolizer status tool.",
        "url": "https://pharmfreq.com",
        "tsv_dir": pharmfreq.EXPORT_DIR,
        "export_sha256": dict(ENZYME_VARIABILITY_PINS),
        "machine": True,
    },
}


def build_enzymes(enzymes: dict[str, Any]) -> dict[str, Any]:
    """``ENZYMES`` with each isoform's metabolizer-status profile merged in.

    One node per enzyme, kind ``enzyme_variability`` (see :data:`ENZYME_VARIABILITY`).
    An isoform PharmFreq does not cover simply has no ``variability`` key, which the
    panel renders as an honest gap rather than as "does not vary": CYP3A4 and CYP1A2,
    the two this dataset leans on hardest, are exactly the two the tool omits.

    Returns a copy; ``ENZYMES`` stays the authored vocabulary it is.
    """
    out: dict[str, Any] = {}
    for eid, rec in enzymes.items():
        rec = dict(rec)
        var = ENZYME_VARIABILITY.get(eid)
        if var:
            rec["variability"] = {
                "gene": var["gene"],
                "profile": var["profile"],
                "sources": _quote_sources(var.get("sources"),
                                          f"Enzyme {rec['label']!r} variability"),
            }
        out[eid] = rec
    return out


def _quote_sources(sources: Any, what: str) -> list[dict[str, Any]]:
    """Validate + normalize a list of quote-level ``sources`` for any sourced claim.

    Each authored source is ``{corpus, page, quote, provenance}``: ``corpus`` must
    be a :data:`SOURCE_CORPORA` key and ``provenance`` a :data:`PROVENANCE_LEVELS`
    grade. ``"verified"`` is the quote-checked grade, so a verified source *must*
    carry a ``page`` and a non-empty ``quote`` (``check_data.py`` then confirms the
    quote is on that page); weaker grades may omit them. The full citation/url is
    *not* denormalized onto every claim: the viewer resolves it from
    ``meta.source_corpora`` by ``corpus``, keeping ``drugs.jsonl`` lean. ``what`` is
    a human label used in error messages (e.g. ``"Drug 'x' binding 'sert'"``).

    Returns the emitted source dicts (empty list when none are authored). Used for
    a drug's per-binding ``sources`` and its ``nbn_sources`` alike.
    """
    out: list[dict[str, Any]] = []
    for s in sources or []:
        corpus = s.get("corpus")
        if corpus not in SOURCE_CORPORA:
            raise KeyError(
                f"{what} cites unknown source corpus {corpus!r} "
                f"(not a SOURCE_CORPORA key)")
        prov = _provenance(s.get("provenance", DEFAULT_PROVENANCE), f"{what} source")
        rec: dict[str, Any] = {"corpus": corpus, "provenance": prov}
        if s.get("page") is not None:
            rec["page"] = s["page"]
        if s.get("quote"):
            rec["quote"] = s["quote"]
        # An expression/localization source (e.g. GtoPdb tissue distribution) may name
        # the assay species: many are rat/mouse, not human. It is carried through so the
        # viewer can flag a non-human claim (amber, like the non-human Ki chip); "Human"
        # or absent = no flag. The grade is independent of species (a rat quote is still
        # quote-verified), but the reader should see what was actually measured.
        if s.get("species"):
            rec["species"] = s["species"]
        # The model that sourced this verified quote (extract + judge). Optional metadata,
        # carried onto the quote node by quote_table.externalize_quotes; absence = "unknown".
        if s.get("llm"):
            if s["llm"] not in SOURCING_LLMS:
                raise ValueError(
                    f"{what} cites unknown sourcing llm {s['llm']!r} "
                    f"(not one of {SOURCING_LLMS})")
            rec["llm"] = s["llm"]
        # How the quote was found, when the pass that wrote the source says so (a drug's
        # North-American brands are grepped off Stahl's Brands line, its French ones
        # proposed by a model reading French prose). Left absent, the corpus answers for
        # it at emit time (see :func:`quote_extraction`); carried, never resolved here,
        # because plenty of sources reach the quote table without passing through this
        # function at all (a Ki annotation, a GtoPdb classification fact).
        if s.get("extraction"):
            rec["extraction"] = s["extraction"]
        if rec.get("extraction", DEFAULT_EXTRACTION) not in EXTRACTIONS:
            raise ValueError(f"{what} cites unknown extraction "
                             f"{rec['extraction']!r} (not one of {EXTRACTIONS})")

        if prov == "verified" and not (rec.get("page") is not None and rec.get("quote")):
            raise ValueError(
                f"{what} has a 'verified' source without a page + quote (verified "
                f"is the quote-checked grade; use 'sourced'/'llm' for an unquoted "
                f"claim)")
        out.append(rec)
    return out


def _binding_sources(drug_id: str, binding: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-binding ``sources`` (thin wrapper over :func:`_quote_sources`)."""
    return _quote_sources(
        binding.get("sources"),
        f"Drug {drug_id!r} binding {binding.get('target')!r}")


# The regions a brand's ``region`` tag may take, used ONLY to order a drug's brands
# per locale (fr -> eu -> na in French, na -> eu -> fr in English); the tag is never
# shown in the UI. na comes from Stahl, eu/fr from Wikipedia (see apply_brand_sources.py).
BRAND_REGIONS = ("na", "eu", "fr")


def _drug_brands(drug_id: str, brands: Any) -> list[dict[str, Any]]:
    """Validate + normalize a drug's commercial ``brands`` (one graded node each).

    Each authored brand is ``{name, region, sources}``: ``name`` a non-empty brand
    string (a proper noun, so NOT run through the FR table), ``region`` a
    :data:`BRAND_REGIONS` tag used only for per-locale ordering (never displayed),
    and ``sources`` the usual quote-level provenance (validated + quote-checked like
    an NbN source). List order is significant: the first brand of a region is its most
    iconic one (the one shown after the drug name in that locale). Returns the emitted
    brand nodes (empty list when none authored); each is its own graded node
    (kind ``drug_brands`` in the provenance tally).
    """
    out: list[dict[str, Any]] = []
    for br in brands or []:
        name = br.get("name")
        if not (isinstance(name, str) and name.strip()):
            raise ValueError(f"Drug {drug_id!r} has a brand with no non-empty 'name'")
        region = br.get("region")
        if region not in BRAND_REGIONS:
            raise ValueError(
                f"Drug {drug_id!r} brand {name!r} has region {region!r} "
                f"(not one of {BRAND_REGIONS})")
        rec: dict[str, Any] = {"name": name.strip(), "region": region}
        sources = _quote_sources(br.get("sources"), f"Drug {drug_id!r} brand {name!r}")
        if sources:
            rec["sources"] = sources
        out.append(rec)
    return out


def _half_life(hl: Any, *, what: str) -> dict[str, Any]:
    """Validate + normalize a half-life (T½) value into canonical hours.

    Authored as ``{hours, hours_max?}``: ``hours`` is the low/representative
    elimination half-life in **hours** (a positive number) and the optional
    ``hours_max`` closes a stated range (Stahl commonly prints "24-48 hours"). Hours
    is the single stored unit deliberately: the viewer formats the pair into a
    human-readable days/hours/minutes string (see js/data.js ``formatHalfLife``), so
    the data never carries a pre-rendered string that could drift from its number.
    ``what`` labels errors (the parent drug or a metabolite name).

    Parameters
    ----------
    hl
        The authored ``half_life`` object.
    what
        Human label for error messages.

    Returns
    -------
    dict
        ``{"hours": float}`` plus ``"hours_max": float`` when a range was authored.
    """
    if not isinstance(hl, dict):
        raise TypeError(f"{what} half_life must be an object with an 'hours' number")
    hours = hl.get("hours")
    # bool is an int subclass; reject it so a stray True/False can't pass as a value.
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours <= 0:
        raise ValueError(f"{what} half_life 'hours' must be a positive number")
    rec: dict[str, Any] = {"hours": float(hours)}
    hi = hl.get("hours_max")
    if hi is not None:
        if isinstance(hi, bool) or not isinstance(hi, (int, float)) or hi < hours:
            raise ValueError(
                f"{what} half_life 'hours_max' must be a number >= 'hours'")
        rec["hours_max"] = float(hi)
    return rec


def _ki_annotation(drug_id: str, binding: dict[str, Any]) -> dict[str, Any] | None:
    """Validate + normalize a binding's ``ki`` annotation (measured binding
    affinity), or ``None`` when absent.

    Shape: ``{median, min, max, n_human, n_nonhuman, source}``. Two source flavours,
    both graded ``verified`` and each verified by ``check_data.py`` in its own way:

    * a **PDSP CSV row** (``corpus:"pdsp_ki"``): ``{ki_id, value_nm, species,
      preparation, radioligand, reference, ...}`` plus, for a match recovered through
      the alias map (:data:`tools.fetch_ki.ALIAS`), ``mapped``/``measured_as``/
      ``relation``/``pdsp_names`` so the viewer warns *which* compound it was measured
      on. Checked by the ``ki_id`` row really being in the corpus CSV.
    * a **quote-gated page** (a ``pages_dir`` corpus, e.g. #9 ``wikipedia_pharm``):
      ``{page, quote, value_nm, reference}`` where ``quote`` is a verbatim affinity-
      table row on the cited page. Checked by the normal verbatim-quote gate.

    The Ki carries its **own** source (rendered as its own badge beside the binding),
    separate from the binding's quote ``sources``, because it is a distinct
    measurement (an affinity), not a source for the binding node.
    """
    ki = binding.get("ki")
    if not ki:
        return None
    what = f"Drug {drug_id!r} binding {binding.get('target')!r} ki"
    for k in ("median", "min", "max"):
        if not isinstance(ki.get(k), (int, float)):
            raise ValueError(f"{what} missing numeric {k!r}")
    src = ki.get("source") or {}
    corpus = src.get("corpus")
    if corpus not in SOURCE_CORPORA:
        raise KeyError(f"{what} source cites unknown corpus {corpus!r}")
    prov = _provenance(src.get("provenance", DEFAULT_PROVENANCE), f"{what} source")
    is_csv = bool(SOURCE_CORPORA[corpus].get("csv"))
    if prov == "verified":
        if is_csv and src.get("ki_id") is None:
            raise ValueError(f"{what} 'verified' PDSP source needs a ki_id (the row id)")
        if not is_csv and not (src.get("quote") and src.get("page") is not None):
            raise ValueError(f"{what} 'verified' quote-gated source needs a page + quote")
    out_src: dict[str, Any] = {"corpus": corpus, "provenance": prov}
    for f in ("ki_id", "value_nm", "species", "preparation", "radioligand",
              "reference", "note", "mapped", "measured_as", "relation", "pdsp_names",
              "page", "quote"):
        if src.get(f) not in (None, ""):
            out_src[f] = src[f]
    # A measured affinity is never read out of prose: both flavours are a parser copying
    # one machine-readable row (a PDSP CSV line, a wiki affinity table cell), so a Ki
    # quote's chain of custody carries no model even when its corpus otherwise does.
    if out_src.get("quote"):
        out_src["extraction"] = "code"
    out = {
        "median": ki["median"], "min": ki["min"], "max": ki["max"],
        "n_human": int(ki.get("n_human", 0)),
        "n_nonhuman": int(ki.get("n_nonhuman", 0)),
        "source": out_src,
    }
    # Count of assays excluded as "tested, essentially inactive" (>=10 uM ceiling),
    # so the panel can note the target was probed and found not to bind. Only present
    # when nonzero (fetch_ki writes it that way), so the field stays sparse.
    if ki.get("inactive"):
        out["inactive"] = int(ki["inactive"])
    return out


# Provenance ranks for the dataset-wide sourcing tally (meta.provenance_stats):
# a higher rank is a stronger grade, 0 = no source/grade at all. Mirrors
# PROVENANCE_LEVELS but as an order so a list of sources can be reduced to its best.
_GRADE_RANK = {"llm": 1, "sourced": 2, "verified": 3}


def _strongest_grade(sources: list[dict[str, Any]] | None) -> int:
    """The strongest provenance rank among a list of source objects (0 if none)."""
    best = 0
    for src in sources or []:
        best = max(best, _GRADE_RANK.get(src.get("provenance"), 0))
    return best


def _binding_grade(binding: dict[str, Any]) -> int:
    """A binding's grade = the strongest of its quote ``sources`` and its ``ki``
    source. A measured Ki (its own verified source) confirms the drug binds the
    target, so it backs the binding claim; an affinity_only binding is graded solely
    by its Ki."""
    best = _strongest_grade(binding.get("sources"))
    ki_src = (binding.get("ki") or {}).get("source")
    if ki_src:
        best = max(best, _GRADE_RANK.get(ki_src.get("provenance"), 0))
    return best


def _binding_action_grade(binding: dict[str, Any]) -> int:
    """A binding DIRECTION's grade = the strongest of its quote ``sources`` alone.

    A measured Ki attests that the ligand binds the target, never whether it
    activates or blocks it, so the Ki is deliberately excluded here: an
    ``affinity_only`` binding (a Ki with no known direction) scores 0 and reads as
    NOSOURCE, which is the whole point of splitting this claim out of
    ``_binding_grade``. A direction stated with no document behind it floors at
    ``llm`` (rank 1): it was authored from memory, which is weaker than a quote but
    stronger than nothing at all.
    """
    if not binding.get("action"):
        return 0
    return max(1, _strongest_grade(binding.get("sources")))


def _provenance_stats(structures: list[dict[str, Any]],
                      projections: list[dict[str, Any]],
                      circuits: list[dict[str, Any]],
                      projection_groups: list[dict[str, Any]],
                      receptors: list[dict[str, Any]],
                      drugs: list[dict[str, Any]],
                      drug_targets: dict[str, dict[str, Any]],
                      addons: list[dict[str, Any]],
                      enzymes: dict[str, Any] | None = None) -> dict[str, Any]:
    """Programmatic sourcing tally over the dataset's **nodes** (see the Nodes
    section of CLAUDE.md), emitted into ``meta.provenance_stats``.

    A *node* is any sourceable datum: a drug binding, a drug NbN label, a drug class
    classification, a neuron projection, a functional circuit, a projection group, a
    receptor classification, a receptor expression region, a non-receptor target
    classification, a target expression region, or a brain-region anatomy fact. Every
    node is bucketed by the strength of its source: ``verified`` (quote-checked),
    ``sourced`` (from a document, not quote-checked) or ``missing`` (no source
    document at all: an ``llm`` grade means "an LLM asserted this from memory", which
    is precisely *no document*, so it is missing, exactly like a node with no source
    object). The viewer's About panel and the README headline read these numbers, so
    the "% sourced" figure is always a real count of the shipped data, never
    hand-typed (the whole point: a programmatic count of source strength across every
    node).

    The knowledge nodes drive the headline ``pct_backed`` (emitted under the
    ``nodes`` key); Wikipedia ``references`` are tallied separately (read-more links,
    which point *at* a node but are not themselves a knowledge node).
    """
    def bucket(rank_or_grade: Any) -> str:
        # An "uncertain" node is a real quote-checked source that the audit flagged as
        # not attributing the claim (see quotes/uncertainty.py). It carries a document,
        # so it stays *backed* (the headline is unchanged), but it leaves the green
        # verified count: a flat check would overstate it.
        if isinstance(rank_or_grade, tuple):
            rank_or_grade, uncertain = rank_or_grade
            if uncertain:
                return "uncertain"
        rank = (rank_or_grade if isinstance(rank_or_grade, int)
                else _GRADE_RANK.get(rank_or_grade, 0))
        # rank 1 = a bare ``llm`` grade (asserted from memory), rank 0 = no source
        # object at all. Both are "missing" (no document), but the viewer renders them
        # differently (grey ``?`` vs orange NOSOURCE), so split them out here too.
        return ("verified" if rank == 3 else
                "sourced" if rank == 2 else
                "llm" if rank == 1 else "nosource")

    def tally(grades: list[Any]) -> dict[str, int]:
        # ``missing`` is kept as the llm+nosource sum (the headline / README / check_data
        # read it); ``llm`` and ``nosource`` are the finer split the sourcing bar renders
        # as distinct grey and red segments.
        counts = {"total": 0, "verified": 0, "uncertain": 0, "sourced": 0,
                  "llm": 0, "nosource": 0, "missing": 0}
        for g in grades:
            counts["total"] += 1
            b = bucket(g)
            counts[b] += 1
            if b in ("llm", "nosource"):
                counts["missing"] += 1
        return counts

    # (grade, is_uncertain) pairs: a flagged binding buckets as ``uncertain`` however
    # strong its quote is (see bucket()).
    binding_grades = [(_binding_grade(b), bool(b.get("uncertainty")))
                      for d in drugs for b in d.get("bindings", [])]
    # The binding's DIRECTION, split out as its own node (see _binding_action_grade):
    # "this drug binds this target" and "it does so as an agonist/antagonist" are two
    # claims with two different backings, and only the first one a Ki can attest. One
    # node per binding, so a Ki-only binding reads as a missing direction instead of
    # disappearing into a verified binding. It carries the SAME uncertainty flag as the
    # binding: those bullets are precisely about whether the quote attributes the
    # action to this drug, which is the direction claim and nothing else.
    binding_action_grades = [(_binding_action_grade(b), bool(b.get("uncertainty")))
                             for d in drugs for b in d.get("bindings", [])]
    # Measured-affinity (PDSP Ki) coverage: a SEPARATE data-quality signal from the
    # grade tally. A binding can be legitimately backed by a Stahl quote with no Ki
    # (the grade counts it as sourced), so "no Ki" is NOT "unsourced"; this figure
    # instead tracks how much of the corpus carries a *measured* affinity and names the
    # drugs where one was never looked up (the "we didn't even bother to look" case the
    # % sourced can't see). Combo drugs ("A + B") are Ki-exempt by design, so they are
    # excluded here, matching js/data.js's combo detection (a +/–/— in the name).
    def _is_combo(d: dict[str, Any]) -> bool:
        return bool(re.search(r"[+–—]", d.get("name", "")))
    ki_drugs = [d for d in drugs if d.get("bindings") and not _is_combo(d)]
    ki_bindings = [b for d in ki_drugs for b in d["bindings"]]
    with_ki = [b for b in ki_bindings if b.get("ki")]
    drugs_no_ki = [d for d in ki_drugs
                   if not any(b.get("ki") for b in d["bindings"])]
    ki_coverage = {
        "bindings_total": len(ki_bindings),
        "bindings_with_ki": len(with_ki),
        "pct_bindings_with_ki": (round(100 * len(with_ki) / len(ki_bindings))
                                 if ki_bindings else 0),
        "drugs_total": len(ki_drugs),
        "drugs_without_ki": len(drugs_no_ki),
        "drugs_without_ki_ids": sorted(d["id"] for d in drugs_no_ki),
    }
    nbn_grades = [_strongest_grade(d.get("nbn_sources"))
                  for d in drugs if d.get("nbn")]
    # Commercial-brand nodes ("this drug is marketed as <brand>"), one per authored
    # brand across all drugs, graded by that brand's own sources (Stahl for na,
    # Wikipedia for eu/fr; see apply_brand_sources.py).
    brand_grades = [_strongest_grade(br.get("sources"))
                    for d in drugs for br in d.get("brands", [])]
    # Drug class-classification nodes ("this drug is an SSRI/..."), one per drug that
    # has categories: the emitted category_provenance (llm unless overridden/sourced).
    category_grades = [d.get("category_provenance", DEFAULT_PROVENANCE)
                       for d in drugs if d.get("categories")]
    # Elimination half-life (T½) nodes, one per drug that carries a half_life, graded
    # by that drug's own half_life_sources (Stahl states it verbatim; see
    # apply_pharmacokinetics.py). A drug with no half_life is simply not a node here.
    half_life_grades = [_strongest_grade(d.get("half_life_sources"))
                        for d in drugs if d.get("half_life")]
    # Drug-metabolism nodes ("<drug> is a substrate of / inhibits / induces <enzyme>"),
    # one per (drug, enzyme, role) row. A pharmacokinetic claim, independent of the
    # drug's receptor bindings: it is what the derived drug -> drug interaction edges
    # in the viewer are built from, so it earns its own kind rather than riding along
    # with the class or half-life node.
    # A (grade, is_uncertain) pair like a binding's: a row another corpus denies buckets
    # as ``uncertain`` however strong its own quote is (quotes/contradictions.py).
    enzyme_grades = [(_strongest_grade(e.get("sources")), bool(e.get("uncertainty")))
                     for d in drugs for e in d.get("enzymes", [])]
    # Active-metabolite identity nodes ("<name> is an active metabolite of <drug>"),
    # one per authored metabolite across all drugs, graded by that metabolite's own
    # sources (the Stahl line naming it). The metabolite's optional T½ is an extra
    # sourced fact shown in the panel; its receptor BINDINGS are their own tally kind
    # below (each a graded graph edge appearing on the receptor's Interacting drugs).
    metabolite_grades = [_strongest_grade(m.get("sources"))
                         for d in drugs for m in d.get("metabolites", [])]
    # Which enzyme FORMS each active metabolite, one node per (parent, metabolite,
    # enzyme). The mirror of the enzyme nodes above (there the drug is the substrate,
    # here the metabolite is the product), and its own kind because it is separately
    # sourced and separately missing: only 14 of the metabolites have a corpus that
    # names their forming enzyme. Counted per PARENT, unlike the bindings below: "CYP2D6
    # makes X out of A" and "... out of B" are two different reactions, not one fact
    # about the molecule.
    metabolite_enzyme_grades = [_strongest_grade(f.get("sources"))
                                for d in drugs for m in d.get("metabolites", [])
                                for f in m.get("formed_by", [])]
    # Non-modeled-metabolite receptor bindings, graded exactly like a drug binding
    # (quote source or measured Ki). A separate kind from drug_bindings so the drug Ki
    # coverage figures are unperturbed; authored by apply_metabolite_bindings.py.
    #
    # A single metabolite can be produced by more than one modeled drug (e.g. mCPP by
    # nefazodone and trazodone), so it appears once under EACH parent in the data with
    # identical bindings (the applier keys by metabolite name -> writes the same list to
    # each parent; check_data guards that they stay identical). Those bindings are a
    # property of the metabolite molecule, not of the parent relationship, so the tally
    # counts them ONCE per unique metabolite (deduped by folded name), never once per
    # parent -- else a shared metabolite would inflate the coverage denominator. (The
    # identity node above legitimately stays per-parent: "X is a metabolite of A" and
    # "X is a metabolite of B" are two distinct, separately sourced claims.)
    metabolite_binding_grades = []
    _seen_metab_bindings = set()
    for d in drugs:
        for m in d.get("metabolites", []):
            key = re.sub(r"[^a-z0-9]", "", (m.get("name") or "").lower())
            if key in _seen_metab_bindings:
                continue
            _seen_metab_bindings.add(key)
            metabolite_binding_grades.extend(_binding_grade(b)
                                             for b in m.get("bindings", []))
            # A metabolite's binding direction is the same claim as a drug's, so it is
            # counted in the SAME drug_binding_action kind (it is a ligand's binding
            # direction either way), deduped by the same folded name.
            binding_action_grades.extend(_binding_action_grade(b)
                                         for b in m.get("bindings", []))
    # (grade, is_uncertain) pairs, like the bindings above: a pathway the book states
    # only as a blanket sweep buckets as ``uncertain`` however strong its quote is.
    projection_grades = [(_strongest_grade(p.get("sources")), bool(p.get("uncertainty")))
                         for p in projections]
    # Functional-circuit + projection-group nodes: each a "these structures / pathways
    # form a system" claim, graded by its own sources (rank 0 => missing when unsourced,
    # matching the viewer's NOSOURCE pill). All missing today (no circuit/group is
    # document-backed yet).
    circuit_grades = [_strongest_grade(c.get("sources")) for c in circuits]
    projection_group_grades = [_strongest_grade(g.get("sources"))
                               for g in projection_groups]
    # Receptor classification is FOUR independent nodes per receptor, one per
    # attribute (family / receptor_class / sign / synaptic), each graded on its own
    # so an unsourced GPCR/sign/site claim shows honestly instead of borrowing a
    # neighbouring quote's grade. A pure stub (no CNS role: no locations, not
    # ubiquitous, no description) is not a node, so it is skipped. The receptor's
    # *expression regions* are a separate node kind (receptor_locations), one node
    # per region, not folded in here.
    scored_receptors = [r for r in receptors
                        if r.get("ubiquitous") or r.get("locations")
                        or r.get("description")]

    def _attr_grade(r: dict[str, Any], attr: str) -> str:
        entry = (r.get("classification") or {}).get(attr)
        return entry["grade"] if entry else DEFAULT_PROVENANCE
    receptor_family_grades = [_attr_grade(r, "family") for r in scored_receptors]
    receptor_class_grades = [_attr_grade(r, "receptor_class") for r in scored_receptors]
    receptor_sign_grades = [_attr_grade(r, "sign") for r in scored_receptors]
    receptor_synaptic_grades = [_attr_grade(r, "synaptic") for r in scored_receptors]
    # Expression-region nodes ("Found in"), one node PER (owner, region): the claim
    # "owner O is expressed in region B", distinct from O's classification node. Each
    # region's grade = the strongest of that region's location_sources (default llm
    # when unsourced). A ubiquitous receptor is one "throughout the brain" node (its
    # "ALL"-keyed sources). Shared by receptors and their non-receptor-target mirror.
    _llm_rank = _GRADE_RANK[DEFAULT_PROVENANCE]

    def location_grades(owner: dict[str, Any], regions_key: str) -> list[int]:
        loc_sources = owner.get("location_sources", {})
        if owner.get("ubiquitous"):
            return [max(_strongest_grade(loc_sources.get("ALL")), _llm_rank)]
        return [max(_strongest_grade(loc_sources.get(base)), _llm_rank)
                for base in owner.get(regions_key, [])]

    receptor_location_grades = [g for r in receptors
                                for g in location_grades(r, "locations")]
    # Expression-DENSITY nodes ("and it is concentrated in these regions"), ONE per owner
    # that carries a measured profile (an owner without one is simply not a node here,
    # like a drug with no half-life). Distinct from the presence nodes above: presence and
    # concentration are different claims and can be sourced independently.
    receptor_density_grades = [r["density"]["grade"] for r in receptors if r.get("density")]
    # Non-receptor drug target classifications (type / system), graded per target.
    # Receptor-linked targets are skipped (already counted as receptors, not twice).
    target_grades = [t.get("classification_provenance", DEFAULT_PROVENANCE)
                     for t in drug_targets.values() if t.get("type") != "receptor"]
    # Target expression-region nodes: the mirror of receptor_locations (a target never
    # sets ubiquitous, so only the per-region branch runs; receptor-linked targets are
    # skipped, their regions counted as the receptor's).
    target_location_grades = [g for t in drug_targets.values()
                              if t.get("type") != "receptor"
                              for g in location_grades(t, "regions")]
    target_density_grades = [t["density"]["grade"] for t in drug_targets.values()
                             if t.get("type") != "receptor" and t.get("density")]
    # Target tone-polarity sub-claims: one graded node per non-receptor target that
    # carries a direction-flipping flag (vesicular / sign / synaptic). Kept distinct
    # from the target's type/system classification so a wrong direction shows honestly.
    target_polarity_grades = [t["polarity_provenance"]
                              for t in drug_targets.values()
                              if t.get("type") != "receptor"
                              and "polarity_provenance" in t]
    # Brain-region anatomy (existence / group / position), graded per emitted
    # structure record (both hemispheres of a pair count, one line each).
    structure_grades = [s.get("classification_provenance", DEFAULT_PROVENANCE)
                        for s in structures]
    # Wikipedia reference links across every owner kind. Non-receptor targets only
    # (a receptor is already counted via the receptor records, not twice); a missing
    # link is a rank-0 "missing" so the gap shows in the coverage.
    ref_grades: list[int] = []
    for rec in (*structures, *receptors, *drugs):
        ref_grades.append(_GRADE_RANK.get(rec.get("wikipedia_provenance"), 0)
                          if rec.get("wikipedia") else 0)
    for tgt in drug_targets.values():
        if tgt.get("type") == "receptor":
            continue
        ref_grades.append(_GRADE_RANK.get(tgt.get("wikipedia_provenance"), 0)
                          if tgt.get("wikipedia") else 0)

    # Addon nodes (see data_generators/addons.py): one node per authored annotation,
    # graded by its own quote sources. Its *slot* is where it draws, not what it
    # claims, so it tallies like any other claim: the whole point of the kind is that
    # a panel-placed caveat is held to the same sourcing bar as a binding.
    addon_grades = [_strongest_grade(a.get("sources")) for a in addons]

    # Enzyme variability (kind ``enzyme_variability``): one node per isoform carrying a
    # metabolizer-status profile. An isoform PharmFreq does not cover is not a node at
    # all rather than an unsourced one, because "we have no frequencies for CYP3A4" is
    # a gap in the corpus, not an unbacked claim we made.
    variability_grades = [_strongest_grade((e.get("variability") or {}).get("sources"))
                          for e in (enzymes or {}).values() if e.get("variability")]

    by_kind = {
        "addons": tally(addon_grades),
        "enzyme_variability": tally(variability_grades),
        "drug_bindings": tally(binding_grades),
        "drug_binding_action": tally(binding_action_grades),
        "drug_nbn": tally(nbn_grades),
        "drug_brands": tally(brand_grades),
        "drug_categories": tally(category_grades),
        "drug_half_life": tally(half_life_grades),
        "drug_enzymes": tally(enzyme_grades),
        "drug_metabolites": tally(metabolite_grades),
        "drug_metabolite_enzyme": tally(metabolite_enzyme_grades),
        "drug_metabolite_bindings": tally(metabolite_binding_grades),
        "projections": tally(projection_grades),
        "circuits": tally(circuit_grades),
        "projection_groups": tally(projection_group_grades),
        "receptors": tally(receptor_family_grades),
        "receptor_class": tally(receptor_class_grades),
        "receptor_sign": tally(receptor_sign_grades),
        "receptor_synaptic": tally(receptor_synaptic_grades),
        "receptor_locations": tally(receptor_location_grades),
        "receptor_density": tally(receptor_density_grades),
        "targets": tally(target_grades),
        "target_polarity": tally(target_polarity_grades),
        "target_locations": tally(target_location_grades),
        "target_density": tally(target_density_grades),
        "structures": tally(structure_grades),
        "references": tally(ref_grades),
    }
    # The knowledge-node kinds (every node that carries a claim + a grade) are every
    # by_kind entry except "references" (a reference points *at* a node, so it is
    # tallied but excluded from the headline). Derived from the one by_kind dict above,
    # so adding a node kind is a single-line edit (add it to by_kind) with no second
    # list to keep in sync.
    node_kinds = tuple(k for k in by_kind if k != "references")
    nodes = {"total": 0, "verified": 0, "uncertain": 0, "sourced": 0,
             "llm": 0, "nosource": 0, "missing": 0}
    for kind in node_kinds:
        for key in nodes:
            nodes[key] += by_kind[kind][key]
    # ``uncertain`` counts as backed: the claim does rest on a real, quote-checked
    # document, and the badge says what is doubtful about it. Moving it out of
    # ``verified`` is the honest part; moving it out of ``backed`` would not be.
    backed = nodes["verified"] + nodes["uncertain"] + nodes["sourced"]
    nodes["backed"] = backed
    nodes["pct_backed"] = (
        round(100 * backed / nodes["total"]) if nodes["total"] else 0)
    return {"by_kind": by_kind, "nodes": nodes, "ki_coverage": ki_coverage}
