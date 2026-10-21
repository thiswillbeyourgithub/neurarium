"""Source provenance: grades, corpora registry, and the source validators.

Every source / reference the viewer shows carries a ``provenance`` grade (llm /
sourced / verified). This module holds the grade vocabulary, the per-id override
registries, and the validators that normalize + check every quote-level source
(drug bindings, Ki annotations, expression locations). The ``SOURCE_CORPORA``
citation registry lives in data_generators.corpora and the sourcing tally in
data_generators.provenance_stats. Kept dependency-free so any data module can
import it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.page_file import page_file
from lib.placeholder import is_placeholder

from . import cpic, pharmfreq
from .corpora import SOURCE_CORPORA

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

# Per-region provenance for a receptor's *expression locations* ("Locations"): the
# claim "receptor R is expressed in region B" is distinct from R's mechanism
# classification and is authored from general knowledge, so every location defaults
# to ``"llm"`` (unsourced). This registry upgrades an individual (receptor, region)
# to a quote-source: ``{receptor_id: {base: [ {corpus, page, quote, provenance} ]}}``.
# ``_receptor_record`` validates each base is one of that receptor's own locations
# and emits the sources; the viewer shows a per-region pill and the coverage tally
# counts each region separately. Empty for now: no expression atlas is wired yet, so
# every "Locations" region is honestly ``"llm"``. Add entries as regions are sourced.
RECEPTOR_LOCATION_SOURCES: dict[str, dict[str, list[dict[str, Any]]]] = {}

# The same, for a non-receptor drug target's *expression regions* ("Locations"): the
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


# Machine-written CPIC prescribing guidance: ``{drug id: [{"gene", "enzyme", "level",
# "guideline", "rows": [...]}]}``. One node per (drug, gene, phenotype) row (kind
# ``drug_pgx``), carrying two citations rather than splitting in two, because CPIC's
# implication and its recommendation are two sentences backing one claim. Written by
# ``tools/fetch/fetch_cpic.py`` (corpus #15); empty when that file is absent, in which
# case no drug carries guidance.
CPIC_GUIDANCE: dict[str, list[dict[str, Any]]] = {}


# ``{file name: sha256}`` for the committed CPIC export the cache above was built from,
# emitted onto the corpus record so `check_data.py` can re-derive every row from it.
CPIC_GUIDANCE_PINS: dict[str, str] = {}


def _merge_cpic_guidance() -> None:
    """Merge ``tools/generated_cache/cpic_guidance.json`` into the registry above.

    Same bargain as the PharmFreq merge above: the export is committed, so the pin can
    be cashed in here and a drifted recommendation is a generation-time failure rather
    than clinical text nobody can trace to a guideline.
    """
    src = Path(__file__).resolve().parent.parent / "generated_cache" / "cpic_guidance.json"
    if not src.exists():
        return
    cache = json.loads(src.read_text(encoding="utf-8"))
    CPIC_GUIDANCE.update(cache.get("guidance") or {})
    pins = cache.get("export_sha256") or {}
    root = Path(__file__).resolve().parent.parent.parent
    for name, want in sorted(pins.items()):
        path = root / Path(cpic.EXPORT_DIR) / name
        if not path.exists():
            raise ValueError(f"cpic_guidance.json pins {name}, which is not in "
                             f"{cpic.EXPORT_DIR}: re-run tools/fetch/fetch_cpic.py")
        got = pharmfreq.sha256(str(path))
        if got != want:
            raise ValueError(f"{cpic.EXPORT_DIR}/{name} has changed since the CPIC "
                             f"guidance cache was built ({got[:12]} != {want[:12]}): "
                             f"re-run tools/fetch/fetch_cpic.py")
    CPIC_GUIDANCE_PINS.update(pins)


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


_REGISTRIES_LOADED = False


def load_external_registries() -> None:
    """Fill the machine-written registries above from their ``generated_cache`` files.

    Called by ``generate_data.build_records`` (and by anything else that reads those
    registries), never at import time: the PharmFreq and CPIC merges re-hash their pinned
    exports and raise on drift, so loading at import made every importer of this module
    (a fetch script, a unit test that only wants a quote constructor) pay that disk I/O
    and fail on an unrelated stale cache. Idempotent, so a second call (a second
    ``build_records`` run in one process) does not append the classification sources
    twice.
    """
    global _REGISTRIES_LOADED
    if _REGISTRIES_LOADED:
        return
    _merge_external_location_sources()
    _merge_external_density()
    _merge_enzyme_variability()
    _merge_cpic_guidance()
    _merge_external_classification_sources()
    # SOURCE_CORPORA is a module-level literal built before any load, so the two corpus
    # records that publish their export pins take the loaded values here.
    SOURCE_CORPORA["pharmfreq"]["export_sha256"] = dict(ENZYME_VARIABILITY_PINS)
    SOURCE_CORPORA["cpic"]["export_sha256"] = dict(CPIC_GUIDANCE_PINS)
    _REGISTRIES_LOADED = True


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
    an owner whose "Locations" regions are each a separately-graded expression node: a
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


# The source corpora registry (SOURCE_CORPORA, imported above) lives in
# data_generators.corpora.


def corpus_page_path(corpus: str, page: Any) -> Path | None:
    """The author-side page file ``<pages_dir>/<page>.md`` a ``(corpus, page)`` citation
    names, or None when the corpus has no ``pages_dir`` or the page is empty.

    The one resolver every applier / freshness pass uses (``check_data.py`` resolves
    the same rule from the *emitted* registry, since it checks what shipped). Whether
    the file exists is the caller's question: the tree is author-side.

    >>> corpus_page_path("bdpm", "69071035").parts[-3:]
    ('bdpm', 'pages', '69071035.md')
    """
    pages_dir = SOURCE_CORPORA.get(corpus, {}).get("pages_dir")
    rel = page_file(pages_dir, page)   # None for an empty or path-like page too
    return Path(__file__).resolve().parent.parent.parent / rel if rel else None


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


def brand_regions(region: str | list[str]) -> list[str]:
    """A brand's ``region`` as a list: authored as one tag, or a list when one name
    is sold in several regions. Shared with ``apply_brand_names.merge_duplicate_brands``."""
    return list(region) if isinstance(region, list) else [region]


def _drug_brands(drug_id: str, brands: Any) -> list[dict[str, Any]]:
    """Validate + normalize a drug's commercial ``brands`` (one graded node each).

    Each authored brand is ``{name, region, sources}``: ``name`` a non-empty brand
    string (a proper noun, so NOT run through the FR table), ``region`` a
    :data:`BRAND_REGIONS` tag used only for per-locale ordering (never displayed), or a
    list of them when one name is sold in several regions (one node, its sources merged:
    Stahl's US "Tranxene" is also the French "Tranxène"),
    and ``sources`` the usual quote-level provenance (validated + quote-checked like
    an NbN source). List order is significant: the first brand of a region is its most
    iconic one (the one shown after the drug name in that locale). Returns the emitted
    brand nodes (empty list when none authored); each is its own graded node
    (kind ``drug_brands`` in the provenance tally).
    """
    out: list[dict[str, Any]] = []
    for br in brands or []:
        name = br.get("name")
        if is_placeholder(name):
            raise ValueError(f"Drug {drug_id!r} has a brand with no real 'name' ({name!r}: "
                             f"empty or a placeholder word, see lib.placeholder)")
        region = br.get("region")
        regions = brand_regions(region)
        if not regions or len(set(regions)) != len(regions) or any(
                r not in BRAND_REGIONS for r in regions):
            raise ValueError(
                f"Drug {drug_id!r} brand {name!r} has region {region!r} "
                f"(not one of {BRAND_REGIONS})")
        rec: dict[str, Any] = {"name": name.strip(), "region": region}
        sources = _quote_sources(br.get("sources"), f"Drug {drug_id!r} brand {name!r}")
        if sources:
            rec["sources"] = sources
        out.append(rec)
    return out


def product_holders(drug: dict[str, Any]) -> list[dict[str, Any]]:
    """The drug itself, then each of its ``formulations``: everything that can hold a
    ``brands`` / ``tmax`` / ``half_life`` claim, in the one shape both share. Every walk
    over those three fields goes through here so a formulation's claims are never
    skipped (see data_generators/formulations.py)."""
    return [drug, *(drug.get("formulations") or [])]


def _hours_value(hl: Any, *, what: str, field: str = "half_life") -> dict[str, Any]:
    """Validate + normalize a duration value into canonical hours.

    Shared by the two per-drug pharmacokinetic durations, which have the same authored
    shape and the same reason for it: the elimination ``half_life`` (T½) and the
    ``tmax`` (time to peak plasma concentration). ``field`` only names the one being
    validated in the error messages.

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
        The authored duration object.
    what
        Human label for error messages.
    field
        The authored key's name, used only in the error messages.

    Returns
    -------
    dict
        ``{"hours": float}`` plus ``"hours_max": float`` when a range was authored.
    """
    if not isinstance(hl, dict):
        raise TypeError(f"{what} {field} must be an object with an 'hours' number")
    hours = hl.get("hours")
    # bool is an int subclass; reject it so a stray True/False can't pass as a value.
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours <= 0:
        raise ValueError(f"{what} {field} 'hours' must be a positive number")
    rec: dict[str, Any] = {"hours": float(hours)}
    hi = hl.get("hours_max")
    if hi is not None:
        if isinstance(hi, bool) or not isinstance(hi, (int, float)) or hi < hours:
            raise ValueError(
                f"{what} {field} 'hours_max' must be a number >= 'hours'")
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
              "page", "quote", "param", "licence"):
        if src.get(f) not in (None, ""):
            out_src[f] = src[f]
    # A table-copied Ki (a PDSP CSV line, a wiki affinity table cell) is a parser copying
    # one machine-readable row, so its quote's chain of custody carries no model even
    # when its corpus otherwise does. The one exception states itself: a Ki a model
    # picked out of a paper (tools/sourcing/apply_ki_prose.py, corpus #17) is stamped
    # `extraction: "llm"` by its applier and so needs a judge like any picked quote.
    if out_src.get("quote"):
        out_src["extraction"] = src.get("extraction") or "code"
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
