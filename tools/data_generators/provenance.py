"""Source provenance: grades, corpora registry, and the source validators.

Every source / reference the viewer shows carries a ``provenance`` grade (llm /
sourced / verified). This module holds the grade vocabulary, the per-id override
registries, the ``SOURCE_CORPORA`` citation registry, and the validators that
normalize + check every quote-level source (drug bindings, Ki annotations,
expression locations). Kept dependency-free so any data module can import it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from drugs_io import is_combination
from page_file import page_file

from . import clinpgx, cpic, pharmfreq
from . import node_kinds as node_kinds_mod

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
# skipped while the structural checks still run. ``url`` is the corpus's landing page
# (a book's DOI, else its ISBN on WorldCat), the link a cited page falls back to when
# neither a ``page_url`` template (``{page}`` filled in) nor a per-page ``page_urls``
# entry (data_generators/page_links.py, added at emit time) names that exact page. ``editable`` marks a corpus
# whose pages can change upstream (a wiki, a live database): each of its cited pages
# carries its download date and must be refetched within a year (see
# data_generators/freshness.py); a book omits the key.
# GtoPdb's "How to cite" page (guidetopharmacology.org/citing.jsp, read 2026-10-12
# from its 2026-07-31 snapshot while the live site was down for maintenance) asks a
# general citation of its current Nucleic Acids Research database paper, plus the
# relevant section of the Concise Guide to PHARMACOLOGY for work on target data, and
# its contents are CC BY-SA 4.0. Shared by corpora #7, #11 and #12 as
# ``required_citations``: a corpus's own request to be cited, which the viewer prints
# under its source pills + in the Sources popup and the README lists under its table.
GTOPDB_NAR_CITATION = (
    "Harding SD, Armstrong JF, Faccenda E, Southan C, Alexander SPH, Davenport AP, "
    "Spedding M, Davies JA. The IUPHAR/BPS Guide to PHARMACOLOGY in 2026. Nucleic "
    "Acids Res. 2026;54(D1):D1446-D1456. doi:10.1093/nar/gkaf1067. PMID 41160876.")
GTOPDB_CONCISE_GUIDE_CITATION = (
    "Alexander SPH, Davenport AP, Kelly E, et al. The Concise Guide to PHARMACOLOGY "
    "2025/26: G protein-coupled receptors. Br J Pharmacol. 2025;182:S24-S151 (and the "
    "matching 2025/26 chapter for each other target family).")
GTOPDB_LICENCE = ("IUPHAR/BPS Guide to PHARMACOLOGY content licensed under CC BY-SA 4.0 "
                  "(database ODbL).")
GTOPDB_TARGET_CITATIONS = [GTOPDB_NAR_CITATION, GTOPDB_CONCISE_GUIDE_CITATION, GTOPDB_LICENCE]
GTOPDB_LIGAND_CITATIONS = [GTOPDB_NAR_CITATION, GTOPDB_LICENCE]


SOURCE_CORPORA: dict[str, dict] = {
    "stahl": {
        # Label for the per-claim tooltip ref ("<ref>, p. N"). The full book title
        # + edition, not a bare "Stahl", so a page citation is unambiguous on its
        # own (which Stahl, which edition) without needing the full bibliographic
        # citation below.
        "ref": "Prescriber's Guide: Stahl's Essential Psychopharmacology, 8th ed.",
        "citation": "Stahl SM. Prescriber's Guide: Stahl's Essential "
                    "Psychopharmacology. 8th ed. Cambridge University Press; 2024.",
        "url": "https://doi.org/10.1017/9781009464772",
        "pages_dir": "data_sources/books/stahl/pages",
    },
    "kandel": {
        # Anatomy/pathway corpus (the projection claims, currently LLM-only, are
        # quote-verified against this). Full title + edition so a page citation is
        # unambiguous on its own.
        "ref": "Kandel, Principles of Neural Science, 6th ed.",
        "citation": "Kandel ER, Koester JD, Mack SH, Siegelbaum SA, eds. "
                    "Principles of Neural Science. 6th ed. McGraw Hill; 2021.",
        # No DOI: the print ISBN 978-1-25-964223-4, via WorldCat.
        "url": "https://search.worldcat.org/search?q=bn:9781259642234",
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
        "url": "https://doi.org/10.1017/9781108975292",
        "pages_dir": "data_sources/books/stahl_essential_pharmacology/pages",
    },
    "carlat": {
        # Second drug corpus: cross-sources drug bindings Stahl did not state.
        "ref": "Carlat Medication Fact Book for Psychiatric Practice, 7th ed.",
        "citation": "Carlat DJ. The Carlat Medication Fact Book for Psychiatric "
                    "Practice. 7th ed. Carlat Publishing; 2024.",
        # No DOI: the print ISBN 979-8-9873354-8-2, via WorldCat.
        "url": "https://search.worldcat.org/search?q=bn:9798987335482",
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
        "url": "https://doi.org/10.1007/978-3-540-34686-9",
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
        "citation": GTOPDB_NAR_CITATION,
        "required_citations": GTOPDB_TARGET_CITATIONS,
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "data_sources/gtopdb/pages",
        "machine": True,
        "editable": True,
        "page_kind": "target",
        "page_url": "https://www.guidetopharmacology.org/GRAC/ObjectDisplayForward?objectId={page}",
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
        "editable": True,
        "page_kind": "row",
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
        "editable": True,
        "page_kind": "gene",
    },
    "wikipedia_pharm": {
        # Corpus #9: a drug's English Wikipedia article, stored whole (article text +
        # every table flattened to rows), so one corpus backs three different claims:
        # a binding `ki` where PDSP (corpus #5) has none (a fallback, never overriding
        # a measured assay), an active metabolite's own bindings, and a drug's
        # metabolising-enzyme roles for the 149 drugs outside Stahl's roster. It also
        # backs a drug's originator (its own article) and that company's country and
        # current name (the company's own article, same pages/ tree).
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
        "editable": True,
        "page_kind": "article",
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
        "editable": True,
        "page_kind": "article",
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
        "citation": GTOPDB_NAR_CITATION,
        "required_citations": GTOPDB_LIGAND_CITATIONS,
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "data_sources/gtopdb/pages_ki",
        "machine": True,
        "editable": True,
        "page_kind": "ligand",
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
        "citation": GTOPDB_NAR_CITATION,
        "required_citations": GTOPDB_TARGET_CITATIONS,
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "data_sources/gtopdb/pages_class",
        "machine": True,
        "editable": True,
        "page_kind": "target",
        "page_url": "https://www.guidetopharmacology.org/GRAC/ObjectDisplayForward?objectId={page}",
    },
    "gtopdb_function": {
        # Function corpus #23: GtoPdb's fourth slice, the curated per-target prose of
        # three target-page sections, "Physiological Functions", "Clinically-Relevant
        # Mutations and Pathophysiology" and "Physiological Consequences of Altering
        # Gene Expression" (+ their comments), backing receptor_effect nodes.
        # tools/fetch/fetch_gtopdb_function.py flattens them into one author-side page
        # per target id (`page`), one statement per line naming its section and the
        # species GtoPdb records; a row with a stated non-human species is never offered
        # as a candidate. An LLM picks the line (not `machine`), so a judge must follow.
        # Licence: contents CC BY-SA 4.0, database ODbL, as #7 / #11 / #12.
        "ref": "IUPHAR/BPS Guide to Pharmacology (GtoPdb), target function",
        "citation": GTOPDB_NAR_CITATION,
        "required_citations": GTOPDB_TARGET_CITATIONS,
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "data_sources/gtopdb/pages_function",
        "editable": True,
        "page_kind": "target",
        "page_url": "https://www.guidetopharmacology.org/GRAC/ObjectDisplayForward?objectId={page}",
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
        "export_sha256": {},  # filled by load_external_registries()
        "machine": True,
        "editable": True,
        "page_kind": "gene",
    },
    "dailymed": {
        # Pharmacokinetics corpus #14: the US prescribing label (DailyMed / NLM
        # Structured Product Labels). It exists for one fact the roster could not
        # otherwise source: a drug's time to peak plasma concentration, which the
        # already-stored corpora state for only a third of the drugs (Wikipedia prose
        # 102, Stahl 13, 190 nowhere) while a label's section 12.3 states it for
        # essentially every oral drug marketed in the US.
        # tools/fetch/fetch_dailymed.py picks ONE label per drug (plain-oral forms
        # preferred: a modified-release product states a real Tmax for a different
        # product) and stores its pharmacokinetics sections as an author-side page;
        # `page` is the label's **setid**, which is a stable public identifier, so a
        # citation resolves to dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=<page>.
        # The quote is a verbatim line of that page, gated exactly like a book page
        # (author-side, skipped on a clone lacking data_sources/dailymed/, like every
        # other pages*/). A primary regulatory source, unlike the tertiary #9.
        # Licence: SPL content is submitted by manufacturers and published by the US
        # National Library of Medicine as a government work under no copyright
        # restriction; the citation below carries the attribution it asks for.
        "ref": "DailyMed (U.S. NLM), prescribing label, clinical pharmacology",
        "citation": "U.S. National Library of Medicine. DailyMed Structured Product "
                    "Label, Pharmacokinetics section of the cited label. "
                    "dailymed.nlm.nih.gov (label set id pinned per citation).",
        "url": "https://dailymed.nlm.nih.gov/",
        "pages_dir": "data_sources/dailymed/pages",
        "editable": True,
        "page_kind": "setid",
        "page_url": "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={page}",
    },
    "bdpm": {
        # Pharmacokinetics + brand corpus #16: the French public drug database (ANSM
        # "Base de donnees publique des medicaments"), the French counterpart of #14. Its
        # summary of product characteristics (RCP) section 5.2 states a time to peak and
        # an elimination half-life for most products authorised in France, including the
        # European-only drugs no US label exists for, and its product table names every
        # French commercial brand.
        # tools/fetch/fetch_bdpm.py joins each drug to its single-active products through
        # the French INN (exact, accent-folded, stereo-aware via tools/chirality.py) and
        # picks ONE plain-oral RCP per drug (a prolonged-release "LP" product states a
        # different product's peak, the Seroquel XR gotcha). `page` is the product's CIS
        # code, a stable public identifier, so a citation resolves to
        # base-donnees-publique.medicaments.gouv.fr/medicament/<page>/extrait.
        # Tmax / half-life quotes are French sentences picked by a model and judged like
        # any prose (four-step pipeline); a brand quote is the denomination's brand word,
        # copied by code from the product table (`extraction: "code"`, no judge), and its
        # page is that product's header page; a current French holder is that header's
        # `holder:` line, copied the same way. Author-side pages, like #14.
        # Licence: Licence Ouverte / Open Licence (Etalab); the citation names the source
        # and the database as the licence asks.
        "ref": "Base de données publique des médicaments (ANSM), RCP",
        "citation": "ANSM / Ministère de la Santé. Base de données publique des "
                    "médicaments, résumé des caractéristiques du produit (RCP) of the "
                    "cited product, section 5.2. base-donnees-publique.medicaments.gouv.fr "
                    "(Licence Ouverte; CIS code pinned per citation).",
        "url": "https://base-donnees-publique.medicaments.gouv.fr/",
        "pages_dir": "data_sources/bdpm/pages",
        "editable": True,
        "page_kind": "cis",
        "page_url": "https://base-donnees-publique.medicaments.gouv.fr/extrait.php?specid={page}",
    },
    "bdpm_rcp": {
        # Workup corpus #24: the same official French RCPs as #16, read for sections
        # 4.2 / 4.3 / 4.4 (posology, contraindications, warnings and precautions):
        # the tests the label asks for before starting a drug and while it is taken
        # (kind drug_workup, data_generators/workup.py). A sibling corpus rather than
        # more lines on #16's pages because a corpus has ONE pages_dir keyed by `page`:
        # the same CIS is cited by both (Teralithe's 5.2 half-life and its 4.4 workup)
        # with different text and a different download date, and the quote gate and
        # the freshness ledger both resolve `<pages_dir>/<page>.md`.
        # tools/fetch/fetch_bdpm_rcp.py builds one page per chosen product (princeps
        # first) from an RCP copy already on disk (#16's own download, or the
        # justelesRCP re-scrape of the live ANSM site), the freshest copy winning; the
        # page header names the copy and how its date was read. `page` = the CIS, or
        # for a drug with no French product at all the EMA product number of its EPAR
        # found by name (`EMEA-H-C-003759`, fetch_ema_epar.py), linked at EMA's SmPC
        # PDF through page_links. An LLM picks the line (not `machine`), so a judge
        # must follow.
        # Licence: Licence Ouverte / Open Licence (Etalab), as #16; an EMA SmPC is
        # "reproduction authorised, source acknowledged".
        "ref": "Base de données publique des médicaments (ANSM) or EMA EPAR, RCP sections 4.2-4.4",
        "citation": "ANSM / Ministère de la Santé. Base de données publique des "
                    "médicaments, résumé des caractéristiques du produit (RCP) of the "
                    "cited product, sections 4.2, 4.3 and 4.4. "
                    "base-donnees-publique.medicaments.gouv.fr (Licence Ouverte; CIS "
                    "code pinned per citation). For a centrally authorised product, the "
                    "European Medicines Agency's EPAR product information (SmPC, French "
                    "version), ema.europa.eu (EMA product number pinned per citation).",
        "url": "https://base-donnees-publique.medicaments.gouv.fr/",
        "pages_dir": "data_sources/bdpm/pages_rcp4",
        "editable": True,
        "page_kind": "product",
        "page_url": "https://base-donnees-publique.medicaments.gouv.fr/medicament/{page}/extrait",
    },
    "cpic": {
        # Pharmacogenomic guidance corpus #15: what a metabolizer phenotype *means* for
        # one prescription. The third layer over #13 (how common each clearance speed
        # is) and the enzyme nodes (which isoform clears the drug), and the only corpus
        # here that states a clinical action rather than a fact about a molecule.
        # tools/fetch/fetch_cpic.py pulls CPIC's structured recommendation rows for the
        # gene-drug pairs this roster covers; `page` is the guideline's ClinPGx id, so a
        # citation resolves to clinpgx.org/guideline/<page>. Two quotes per node (the
        # implication, then the recommendation): one claim, two sentences, both CPIC's
        # own words. Deterministic, no judge, `extraction: "code"`.
        # Committed with the repo like #13 (CC0 content, 64 KB) and pinned by sha256
        # instead of kept author-side, so the gate runs on every clone; unlike #13 the
        # quote is not one we compose, so it is checked verbatim against the export.
        # Scope limits that are gaps in the source, not judgements: only genes with a
        # metabolizer-frequency profile here (so HLA-B with carbamazepine, SCN1A, and
        # the urea-cycle genes with valproate are out), only CPIC's `general`/`adults`/
        # treatment-naive populations, and only phenotypes a frequency exists for.
        # Licence: CPIC curated content is CC0 1.0; the citation below carries the
        # attribution CPIC's terms ask of an API consumer (primary source, guideline
        # publication, version, date accessed).
        "ref": "CPIC, clinical pharmacogenetics dosing guideline",
        "citation": "Clinical Pharmacogenetics Implementation Consortium (CPIC®). "
                    "Gene-drug recommendation, cited guideline. clinpgx.org (CC0 1.0); "
                    "guideline content is subject to update, so the export is dated.",
        "url": "https://cpicpgx.org/",
        "tsv_dir": cpic.EXPORT_DIR,
        "export_sha256": {},  # filled by load_external_registries()
        "machine": True,
        "editable": True,
        "page_kind": "guideline",
        "page_url": "https://www.clinpgx.org/guidelineAnnotation/{page}",
    },
    "europepmc": {
        # Primary-literature corpus #17: paper abstracts for the claims only a study
        # measures (lithium's brain half-life, from 7Li MRS, being longer than its serum
        # one: no book, label or article on disk says so), plus Europe PMC's own
        # open-access full text where the record has one (a Ki that lives only in a
        # paper's table: viloxazine's 5-HT2B / 5-HT2C). tools/fetch/fetch_europepmc.py
        # stores one page per paper (abstract one sentence per line, then the OA body and
        # every table as `cell | cell` rows, licence in the header); `page` is the PubMed
        # id, so a citation resolves to europepmc.org/article/MED/<page>. Papers are
        # hand-listed (PAPERS, each with its claim) or a Wikipedia-cited paper the Ki
        # pass followed, so the corpus never grows into a crawl. Quotes are picked by a
        # model and judged like any other (no `extraction: "code"`). Author-side pages
        # like #14/#16 (a short verbatim sentence is a citation, the page is never
        # shipped); a full-text Ki source carries the paper's `licence` for credit.
        "ref": "Europe PMC, journal article",
        "citation": "Europe PMC (EMBL-EBI). Abstract, or open-access full text, of the "
                    "cited journal article, PubMed id pinned per citation. europepmc.org.",
        "url": "https://europepmc.org/",
        "pages_dir": "data_sources/europepmc/pages",
        "page_kind": "pmid",
        "page_url": "https://europepmc.org/article/MED/{page}",
        # Not editable: a published abstract does not change under a citation, so
        # its pages carry no freshness deadline (see data_generators/freshness.py).
        "editable": False,
    },
    "drugsfda": {
        # Regulatory register corpus #18: Drugs@FDA, the FDA's own list of approved
        # applications, read from openFDA's bulk drug/drugsfda export (www.fda.gov
        # refuses scripted downloads). It exists for two facts: a drug's first US
        # approval, as the fallback where Wikipedia (#9/#10) states no first approval,
        # and the sponsor holding that NDA today (`holders`, the page title).
        # tools/fetch/fetch_drugsfda.py takes, per drug, the earliest original (ORIG)
        # approval among the NDAs whose single active ingredient is that drug (never an
        # ANDA, never a combination), and only when that NDA's own FDA class is "new
        # molecular entity" (a "new dosage form" NDA says an older approval exists, and
        # the export misses some old applications). `page` is the application number
        # (NDA019839), resolving at accessdata.fda.gov/scripts/cder/daf/ (ApplNo); the
        # quote is the product row copied by code (`extraction: "code"`, no judge).
        # Author-side pages like #14. Licence: openFDA data is public domain (CC0).
        "ref": "Drugs@FDA (U.S. FDA), approved application history",
        "citation": "U.S. Food and Drug Administration. Drugs@FDA: FDA-approved drugs, "
                    "cited application's original approval (openFDA drug/drugsfda "
                    "export, public domain; application number pinned per citation).",
        "url": "https://www.accessdata.fda.gov/scripts/cder/daf/",
        "pages_dir": "data_sources/drugsfda/pages",
        "editable": True,
        "page_kind": "application",
    },
    "clinpgx": {
        # Pharmacogenomic-association corpus #20: ClinPGx's (formerly PharmGKB) clinical
        # annotations for the genes of the modeled receptors and targets ("patients with
        # the AA genotype may have ..."), one node per annotation (kind receptor_variant).
        # tools/fetch/fetch_clinpgx.py filters the bulk download to our genes at levels
        # 1A-3 (level 4 dropped); `page` is the clinical annotation id, so a citation
        # resolves to clinpgx.org/clinicalAnnotation/<page>. One quote per genotype,
        # ClinPGx's own sentence, copied by code (`extraction: "code"`, no judge).
        # Committed and pinned by sha256 like #15, re-derived by check_data family 12.
        # Licence: CC BY-SA 4.0 (licence text beside the export; ShareAlike covers it).
        "ref": "ClinPGx (PharmGKB), clinical annotation",
        "citation": "ClinPGx (formerly PharmGKB). Clinical annotation, cited id. "
                    "clinpgx.org (CC BY-SA 4.0); annotations are revised, so the export "
                    "is dated.",
        "url": "https://www.clinpgx.org/",
        "tsv_dir": clinpgx.EXPORT_DIR,
        "export_sha256": clinpgx.load_pins(),
        "machine": True,
        "editable": True,
        "page_kind": "annotation",
        "page_url": "https://www.clinpgx.org/clinicalAnnotation/{page}",
    },
    "pubchem": {
        # Physicochemical corpus #21: PubChem's computed properties of a drug's compound
        # (kinds drug_lipophilicity / drug_polar_surface): XLogP3 and the topological
        # polar surface area, computed estimates, not measurements. The compound is the
        # CID on the drug's stored English Wikipedia drugbox; tools/fetch/fetch_physchem.py
        # stores one page per CID (one `Label: value` line per property, the quote, copied
        # by code, no judge). PubChem recomputes, so the page is dated (editable).
        # Licence: PubChem data is public domain.
        "ref": "PubChem (NCBI), computed compound properties",
        "citation": "Kim S, Chen J, Cheng T, et al. PubChem 2025 update. Nucleic Acids "
                    "Res. 2025;53(D1):D1516-D1525. doi:10.1093/nar/gkae1059. Computed "
                    "properties of the cited compound (CID), public domain.",
        "url": "https://pubchem.ncbi.nlm.nih.gov/",
        "pages_dir": "data_sources/pubchem/pages",
        "machine": True,
        "editable": True,
        "page_kind": "cid",
        "page_url": "https://pubchem.ncbi.nlm.nih.gov/compound/{page}",
    },
    "b3db": {
        # Brain-entry corpus #22: B3DB, a curated database of measured blood-brain
        # barrier permeability compiled from 50 published sources (kind drug_bbb): a
        # BBB+ / BBB- label per compound and, for about 1,000 of them, a measured logBB.
        # One bulk TSV from the B3DB GitHub repository, joined by CID (else exact name,
        # chirality-guarded, and always by InChI formula + connectivity) in
        # tools/fetch/fetch_physchem.py, which flattens the matched rows into one page per
        # CID (`page`); the quote is one row line, copied by code (no judge). The
        # repository is updated now and then, so the download is dated (editable).
        # Licence: CC0 1.0.
        "ref": "B3DB, blood-brain barrier permeability database",
        "citation": "Meng F, Xi Y, Huang J, Ayers PW. A curated diverse molecular "
                    "database of blood-brain barrier permeability with chemical "
                    "descriptors. Sci Data. 2021;8:289. doi:10.1038/s41597-021-01069-5. "
                    "github.com/theochem/B3DB (CC0 1.0).",
        "url": "https://github.com/theochem/B3DB",
        "pages_dir": "data_sources/b3db/pages",
        "machine": True,
        "editable": True,
        "page_kind": "cid",
    },
    "agnp_tdm": {
        # Consensus-guideline corpus #19: the AGNP TDM task force's 2026 update of its
        # therapeutic drug monitoring guidelines (Pharmacopsychiatry, open access, a
        # published article, so a book-like corpus: no `editable`, no freshness). Its
        # Table 5 gives each drug's therapeutic reference range, laboratory alert level
        # and level of recommendation to use TDM; Table 1 the CYP isoforms metabolising
        # it. tools/fetch/fetch_agnp_tdm.py reads both tables by cell rectangle off the
        # PDF and copies each row verbatim (`extraction: "code"`, no judge); `page` is
        # the PDF page, matching pages/<page>.md split by tools/fetch/pdf_to_pages.py.
        "ref": "AGNP Consensus Guidelines for TDM in Neuropsychopharmacology, 2026",
        "citation": "Hart XM, Gründer G, Hiemke C, et al. Consensus Guidelines for "
                    "Therapeutic Drug Monitoring in Neuropsychopharmacology: Update 2026. "
                    "Pharmacopsychiatry. 2026;59:166-295. doi:10.1055/a-2860-7861.",
        "url": "https://doi.org/10.1055/a-2860-7861",
        "pages_dir": "data_sources/books/agnp_tdm_2026/pages",
    },
}


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
        if not (isinstance(name, str) and name.strip()):
            raise ValueError(f"Drug {drug_id!r} has a brand with no non-empty 'name'")
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


def _binding_action_grade(binding: dict[str, Any]) -> int | str:
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
        # Searched everywhere, nothing states it (data_generators/unknown.py): its own
        # bucket, outside the headline denominator.
        return "unknown" if binding.get("unknown") else 0
    return max(1, _strongest_grade(binding.get("sources")))


def _provenance_stats(structures: list[dict[str, Any]],
                      projections: list[dict[str, Any]],
                      circuits: list[dict[str, Any]],
                      projection_groups: list[dict[str, Any]],
                      receptors: list[dict[str, Any]],
                      drugs: list[dict[str, Any]],
                      metabolites: list[dict[str, Any]],
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
        uncertain = False
        if isinstance(rank_or_grade, tuple):
            rank_or_grade, uncertain = rank_or_grade
        if rank_or_grade == "unknown":
            return "unknown"
        rank = (rank_or_grade if isinstance(rank_or_grade, int)
                else _GRADE_RANK.get(rank_or_grade, 0))
        # Only a node resting on a document can be "uncertain": a bare llm claim that
        # another corpus denies (quotes/contradictions.py) is still missing its own
        # source, and the denial must not lift it into the backed headline.
        if uncertain and rank >= _GRADE_RANK["sourced"]:
            return "uncertain"
        # rank 1 = a bare ``llm`` grade (asserted from memory), rank 0 = no source
        # object at all. Both are "missing" (no document), but the viewer renders them
        # differently (grey ``?`` vs orange NOSOURCE), so split them out here too.
        return ("verified" if rank == 3 else
                "sourced" if rank == 2 else
                "llm" if rank == 1 else "nosource")

    def _node_grade(node: dict[str, Any], grade: Any = None) -> tuple[Any, bool]:
        # A (grade, is_uncertain) pair for a node-shaped claim, so a bullet on it (a
        # ``contradicted`` entry can name any node site, quotes/contradictions.py)
        # buckets ``uncertain`` like a binding's. ``grade`` defaults to its sources'.
        return (_strongest_grade(node.get("sources")) if grade is None else grade,
                bool(node.get("uncertainty")))

    def tally(grades: list[Any]) -> dict[str, int]:
        # ``missing`` is kept as the llm+nosource sum (the headline / README / check_data
        # read it); ``llm`` and ``nosource`` are the finer split the sourcing bar renders
        # as distinct grey and red segments.
        # ``unknown`` (searched everywhere, nothing states it; data_generators/unknown.py)
        # is counted beside the total, never in it: it is neither backed nor missing, so
        # it must not move the headline % either way.
        counts = {"total": 0, "verified": 0, "uncertain": 0, "sourced": 0,
                  "llm": 0, "nosource": 0, "missing": 0, "unknown": 0}
        for g in grades:
            b = bucket(g)
            if b == "unknown":
                counts["unknown"] += 1
                continue
            counts["total"] += 1
            counts[b] += 1
            if b in ("llm", "nosource"):
                counts["missing"] += 1
        return counts

    # (grade, is_uncertain) pairs: a flagged binding buckets as ``uncertain`` however
    # strong its quote is (see bucket()).
    binding_grades = [_node_grade(b, _binding_grade(b))
                      for d in drugs for b in d.get("bindings", [])]
    # The binding's DIRECTION, split out as its own node (see _binding_action_grade):
    # "this drug binds this target" and "it does so as an agonist/antagonist" are two
    # claims with two different backings, and only the first one a Ki can attest. One
    # node per binding, so a Ki-only binding reads as a missing direction instead of
    # disappearing into a verified binding. It carries the SAME uncertainty flag as the
    # binding: those bullets are precisely about whether the quote attributes the
    # action to this drug, which is the direction claim and nothing else.
    binding_action_grades = [_node_grade(b, _binding_action_grade(b))
                             for d in drugs for b in d.get("bindings", [])]
    # Measured-affinity (PDSP Ki) coverage: a SEPARATE data-quality signal from the
    # grade tally. A binding can be legitimately backed by a Stahl quote with no Ki
    # (the grade counts it as sourced), so "no Ki" is NOT "unsourced"; this figure
    # instead tracks how much of the corpus carries a *measured* affinity and names the
    # drugs where one was never looked up (the "we didn't even bother to look" case the
    # % sourced can't see). Combo drugs ("A + B") are Ki-exempt by design, so they are
    # excluded here (``drugs_io.is_combination``, which js/data.js's +/–/— test mirrors).
    ki_drugs = [d for d in drugs if d.get("bindings") and not is_combination(d)]
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
    # A formulation (drug_formulations) holds the brands / Tmax / T½ a source tied
    # to one release type, in the molecule's own shape: they are the same kinds,
    # tallied wherever they sit (see data_generators/formulations.py).
    holders = [h for d in drugs for h in product_holders(d)]
    brand_grades = [_node_grade(br) for d in holders for br in d.get("brands", [])]
    # Drug class-classification nodes ("this drug is an SSRI/..."), one per drug that
    # has categories: the emitted category_provenance (llm unless overridden/sourced).
    category_grades = [d.get("category_provenance", DEFAULT_PROVENANCE)
                       for d in drugs if d.get("categories")]
    # Elimination half-life (T½) nodes, one per drug that carries a half_life, graded
    # by that drug's own half_life_sources (Stahl states it verbatim; see
    # apply_pharmacokinetics.py). A drug with no half_life is simply not a node here.
    half_life_grades = [_strongest_grade(d.get("half_life_sources"))
                        for d in holders if d.get("half_life")]
    # Time-to-peak (Tmax) nodes, one per drug that carries a tmax, graded by that
    # drug's own tmax_sources. Its own kind rather than a field of the T½ node: the
    # two are separately sourced (a Wikipedia prose sentence for the peak, a Stahl
    # bullet for the half-life) and separately missing, and the simulation reads them
    # at the two ends of the same curve. See apply_tmax.py.
    tmax_grades = [_strongest_grade(d.get("tmax_sources"))
                   for d in holders if d.get("tmax")]
    # Formulation nodes ("this drug is sold as an extended-release product"), ONE per
    # formulation, graded by the source naming its release type.
    formulation_grades = [_strongest_grade(f.get("release_sources"))
                          for d in drugs for f in d.get("formulations", [])]
    # Regulatory history: ONE first-approval node per drug that carries one, and ONE
    # node per market withdrawal (a drug never withdrawn has none: absence is not a
    # claim). Both graded by their own quotes; see apply_drug_history.py.
    first_approval_grades = [_strongest_grade(d.get("first_approval_sources"))
                             for d in drugs if d.get("first_approval")]
    withdrawal_grades = [_node_grade(w) for d in drugs for w in d.get("withdrawals", [])]
    # Who the drug comes from (data_generators/origin.py): ONE holder node per (drug,
    # market), ONE originator and ONE originator-country node per drug carrying one.
    holder_grades = [_node_grade(h) for d in drugs for h in d.get("holders", [])]
    originator_grades = [_strongest_grade(d.get("originator_sources"))
                         for d in drugs if d.get("originator")]
    originator_country_grades = [_strongest_grade(d.get("originator_country_sources"))
                                 for d in drugs if d.get("originator_country")]
    # ONE node per prodrug ("inactive until metabolised into X"); a drug active itself
    # carries no claim. See apply_prodrug.py.
    prodrug_grades = [_strongest_grade(d.get("prodrug_sources"))
                      for d in drugs if d.get("prodrug")]
    # ONE node per salt / combination declaring its `constituents` (what the viewer
    # lends it the bindings of); a combo named after its parts carries no such claim.
    constituents_grades = [_strongest_grade(d.get("constituents_sources"))
                           for d in drugs if d.get("constituents")]
    # Therapeutic drug monitoring (AGNP, corpus #19): ONE therapeutic-range node and
    # ONE alert-level node per drug carrying them (see data_generators/tdm.py).
    trr_grades = [_strongest_grade(d.get("therapeutic_range_sources"))
                  for d in drugs if d.get("therapeutic_range")]
    alert_grades = [_strongest_grade(d.get("alert_level_sources"))
                    for d in drugs if d.get("alert_level")]
    # Physicochemistry and brain entry (data_generators/physchem.py): ONE node per drug
    # for each of its computed XLogP3, its computed polar surface and its B3DB label.
    physchem_grades = {f: [_strongest_grade(d.get(f"{f}_sources")) for d in drugs if f in d]
                       for f in ("xlogp", "tpsa", "bbb")}
    # Pre-prescription workup (data_generators/workup.py, BETA): ONE node per (drug,
    # test, timing) row the French RCP asks for.
    workup_grades = [_node_grade(r) for d in drugs for r in d.get("workup", []) or []]
    # Drug-metabolism nodes ("<drug> is a substrate of / inhibits / induces <enzyme>"),
    # one per (drug, enzyme, role) row. A pharmacokinetic claim, independent of the
    # drug's receptor bindings: it is what the derived drug -> drug interaction edges
    # in the viewer are built from, so it earns its own kind rather than riding along
    # with the class or half-life node.
    # A (grade, is_uncertain) pair like a binding's: a row another corpus denies buckets
    # as ``uncertain`` however strong its own quote is (quotes/contradictions.py).
    enzyme_grades = [_node_grade(e)
                     for d in drugs for e in d.get("enzymes", [])]
    # HOW MUCH of the clearing that isoform does (major/minor, strong/weak), split out of
    # the row for the same reason a pathway's transmitter is (quotes/attestation.py): the
    # CYP quote gate checks the isoform is named, never the tier. A row stating no tier
    # makes no claim and contributes no node.
    enzyme_strength_grades = [_node_grade(entry, entry["grade"])
                              for d in drugs
                              for e in d.get("enzymes", [])
                              if (entry := (e.get("claims") or {}).get("strength"))]
    # CPIC prescribing guidance (corpus #15), one node per (drug, gene, phenotype) row.
    # Its own kind, not a sub-claim of the enzyme row above, because it is a different
    # kind of statement: the enzyme row says who clears the drug, this says what a
    # person who clears it slowly should expect. Two citations per node (implication,
    # recommendation), so the grade is the strongest of the two, as everywhere else.
    pgx_grades = [_strongest_grade(r.get("sources"))
                  for d in drugs for block in d.get("pgx", [])
                  for r in block.get("rows", [])]
    # Active-metabolite identity nodes ("<name> is an active metabolite of <drug>"),
    # one per authored metabolite across all drugs, graded by that metabolite's own
    # sources (the Stahl line naming it). The metabolite's optional T½ is an extra
    # sourced fact shown in the panel; its receptor BINDINGS are their own tally kind
    # below (each a graded graph edge appearing on the receptor's Interacting drugs).
    # A (grade, is_uncertain) pair: a link another corpus denies is active buckets as
    # ``uncertain`` however strong its own quote (CONTRADICTIONS).
    metabolite_grades = [_node_grade(m) for d in drugs for m in d.get("metabolites", [])]
    # Which enzyme FORMS each active metabolite, one node per (parent, metabolite,
    # enzyme). The mirror of the enzyme nodes above (there the drug is the substrate,
    # here the metabolite is the product), and its own kind because it is separately
    # sourced and separately missing: only 14 of the metabolites have a corpus that
    # names their forming enzyme. Counted per PARENT, unlike the bindings below: "CYP2D6
    # makes X out of A" and "... out of B" are two different reactions, not one fact
    # about the molecule.
    metabolite_enzyme_grades = [_node_grade(f) for d in drugs for m in d.get("metabolites", [])
                                for f in m.get("formed_by", [])]
    # Non-modeled-metabolite receptor bindings, graded exactly like a drug binding
    # (quote source or measured Ki). A separate kind from drug_bindings so the drug Ki
    # coverage figures are unperturbed; authored by apply_metabolite_bindings.py.
    # Walked over the one-per-molecule metabolite store, not the parents: mCPP's
    # bindings are a property of the molecule, so nefazodone AND trazodone listing it
    # count them once. (The identity node above legitimately stays per-parent: "X is a
    # metabolite of A" and "X is a metabolite of B" are two separately sourced claims.)
    metabolite_binding_grades = [_node_grade(b, _binding_grade(b))
                                 for m in metabolites for b in m.get("bindings", [])]
    # A metabolite's binding direction is the same claim as a drug's, so it is counted
    # in the SAME drug_binding_action kind (a ligand's binding direction either way).
    binding_action_grades.extend(_binding_action_grade(b) for m in metabolites
                                 for b in m.get("bindings", []))
    # (grade, is_uncertain) pairs, like the bindings above: a pathway the book states
    # only as a blanket sweep buckets as ``uncertain`` however strong its quote is.
    projection_grades = [_node_grade(p)
                         for p in projections]
    # The two sub-claims split out of that same arrow (see quotes/attestation.py): what
    # transmitter it carries, and, for the glutamate/GABA ones, its excitatory/inhibitory
    # sign. Each is its own node for the same reason a receptor's four classification
    # attributes are: one sentence rarely attests all of them, and the sign in particular
    # colours every arrow in the viewer's Potential mode. A modulatory system makes no
    # sign claim at all, so it contributes no ``projection_sign`` node (not an unsourced
    # one). The uncertainty flag stays on the pathway node: a blanket sweep is doubt about
    # which regions the arrow reaches, not about what it releases.
    def _claim_grades(name: str) -> list[tuple[str, bool]]:
        return [_node_grade(entry, entry["grade"]) for p in projections
                if (entry := (p.get("claims") or {}).get(name))]
    projection_transmitter_grades = _claim_grades("transmitter")
    projection_sign_grades = _claim_grades("sign")
    # Functional-circuit + projection-group nodes: each a "these structures / pathways
    # form a system" claim, graded by its own sources (rank 0 => missing when unsourced,
    # matching the viewer's NOSOURCE pill). All missing today (no circuit/group is
    # document-backed yet).
    circuit_grades = [_node_grade(c) for c in circuits]
    projection_group_grades = [_node_grade(g) for g in projection_groups]
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

    # A (grade, is_uncertain) pair: an attribute another corpus denies buckets
    # ``uncertain`` however strong its own quote (quotes/contradictions.py).
    def _attr_grade(r: dict[str, Any], attr: str) -> tuple[str, bool]:
        entry = (r.get("classification") or {}).get(attr)
        if not entry:
            return (DEFAULT_PROVENANCE, False)
        return _node_grade(entry, entry["grade"])
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

    # A (grade, is_uncertain) pair, a region its animal-only evidence flags
    # (quotes/animal_evidence.py, ``location_uncertainty``) bucketing ``uncertain``.
    def location_grades(owner: dict[str, Any], regions_key: str) -> list[tuple[int, bool]]:
        loc_sources = owner.get("location_sources", {})
        doubted = owner.get("location_uncertainty") or {}
        bases = ["ALL"] if owner.get("ubiquitous") else owner.get(regions_key, [])
        return [(max(_strongest_grade(loc_sources.get(base)), _llm_rank), base in doubted)
                for base in bases]

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
    # Clinical-effect nodes (kind receptor_effect, BETA): one per (owner, mode, effect),
    # on receptors and non-receptor targets alike. Like a density profile, a node exists
    # only once sourced, and it is a stored quoted claim, so it sits in the headline.
    # An owner whose effects were searched everywhere with no hit (``effects_unknown``,
    # data_generators/unknown.py) adds one UNKNOWN, outside the denominator.
    effect_owners = (*receptors, *(t for t in drug_targets.values()
                                   if t.get("type") != "receptor"))
    # A (grade, is_uncertain) pair: an effect backed by isolated tissue only buckets
    # ``uncertain`` however strong its quote (receptor_effects.EFFECT_EVIDENCE).
    receptor_effect_grades = [_node_grade(e, e["grade"]) for o in effect_owners
                              for e in o.get("effects", [])] + [
        "unknown" for o in effect_owners if o.get("effects_unknown")]
    # Release-modulation nodes (kind receptor_release_modulation, BETA): one per (receptor,
    # kind, site, transmitter, direction); exists only once sourced, so in the headline.
    release_modulation_grades = [_node_grade(n, n["grade"]) for r in receptors
                                 for n in r.get("release_modulation", [])]
    # Availability-across-age/sex nodes (kind receptor_demographic, BETA): one per (owner,
    # factor, direction, structure), receptors and non-receptor targets alike.
    gene_owners = (*receptors, *(t for t in drug_targets.values()
                                 if t.get("type") != "receptor"))
    demographic_grades = [_node_grade(n, n["grade"]) for o in gene_owners
                          for n in o.get("demographics", [])]
    # Gene-variant associations (kind receptor_variant, ClinPGx #20): one per (owner,
    # clinical annotation), receptors and non-receptor targets alike.
    variant_grades = [n["grade"] for o in gene_owners for n in o.get("variants", [])]
    # Brain-region anatomy (existence / group / position), graded per emitted
    # structure record (both hemispheres of a pair count, one line each).
    structure_grades = [_node_grade(s, s.get("classification_provenance", DEFAULT_PROVENANCE))
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
    # A ``dataset`` addon is a statement about this dataset, not knowledge (see
    # addons.ADDON_BASES), so it is not a node of the tally at all.
    addon_grades = [_strongest_grade(a.get("sources")) for a in addons
                    if a.get("basis", "claim") != "dataset"]

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
        "drug_tmax": tally(tmax_grades),
        "drug_formulations": tally(formulation_grades),
        "drug_first_approval": tally(first_approval_grades),
        "drug_withdrawals": tally(withdrawal_grades),
        "drug_holders": tally(holder_grades),
        "drug_originator": tally(originator_grades),
        "drug_originator_country": tally(originator_country_grades),
        "drug_prodrug": tally(prodrug_grades),
        "drug_constituents": tally(constituents_grades),
        "drug_therapeutic_range": tally(trr_grades),
        "drug_alert_level": tally(alert_grades),
        "drug_lipophilicity": tally(physchem_grades["xlogp"]),
        "drug_polar_surface": tally(physchem_grades["tpsa"]),
        "drug_bbb": tally(physchem_grades["bbb"]),
        "drug_workup": tally(workup_grades),
        "drug_enzymes": tally(enzyme_grades),
        "drug_enzyme_strength": tally(enzyme_strength_grades),
        "drug_pgx": tally(pgx_grades),
        "drug_metabolites": tally(metabolite_grades),
        "drug_metabolite_enzyme": tally(metabolite_enzyme_grades),
        "drug_metabolite_bindings": tally(metabolite_binding_grades),
        "projections": tally(projection_grades),
        "projection_transmitter": tally(projection_transmitter_grades),
        "projection_sign": tally(projection_sign_grades),
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
        "receptor_effect": tally(receptor_effect_grades),
        "receptor_release_modulation": tally(release_modulation_grades),
        "receptor_demographic": tally(demographic_grades),
        "receptor_variant": tally(variant_grades),
        "structures": tally(structure_grades),
        "references": tally(ref_grades),
    }
    # The headline sums over the one roster (node_kinds.py); a by_kind key outside it
    # would be tallied yet silently left out of the headline, so refuse the drift.
    drift = set(by_kind) ^ set(node_kinds_mod.NODE_KINDS + node_kinds_mod.TALLY_ONLY_KINDS)
    if drift:
        raise ValueError(f"by_kind keys out of sync with node_kinds.py: {sorted(drift)}")
    node_kinds = node_kinds_mod.NODE_KINDS
    nodes = {"total": 0, "verified": 0, "uncertain": 0, "sourced": 0,
             "llm": 0, "nosource": 0, "missing": 0, "unknown": 0}
    for kind in node_kinds:
        for key in nodes:
            nodes[key] += by_kind[kind][key]
    # ``uncertain`` counts as backed: the claim does rest on a real, quote-checked
    # document, and the badge says what is doubtful about it. Moving it out of
    # ``verified`` is the honest part; moving it out of ``backed`` would not be.
    backed = node_kinds_mod.backed(nodes)
    nodes["backed"] = backed
    nodes["pct_backed"] = (
        round(100 * backed / nodes["total"]) if nodes["total"] else 0)
    return {"by_kind": by_kind, "nodes": nodes, "ki_coverage": ki_coverage}
