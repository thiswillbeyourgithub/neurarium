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


def _merge_external_location_sources() -> None:
    """Merge author-side sourced expression locations from ``tools/generated_cache/location_sources.json``
    into the two registries above.

    That file is machine-written by the expression-sourcing pipeline (fetch ->
    judge -> ``tools/apply_location_sources.py``, e.g. from GtoPdb tissue
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
# skipped while the structural checks still run.
SOURCE_CORPORA: dict[str, dict[str, str]] = {
    "stahl": {
        # Label for the per-claim tooltip ref ("<ref>, p. N"). The full book title
        # + edition, not a bare "Stahl", so a page citation is unambiguous on its
        # own (which Stahl, which edition) without needing the full bibliographic
        # citation below.
        "ref": "Prescriber's Guide: Stahl's Essential Psychopharmacology, 8th ed.",
        "citation": "Stahl SM. Prescriber's Guide: Stahl's Essential "
                    "Psychopharmacology. 8th ed. Cambridge University Press; 2024.",
        "url": "TODO",
        "pages_dir": "data_sources/books/stahl/pages",
    },
    "kandel": {
        # Anatomy/pathway corpus (the projection claims, currently LLM-only, are
        # quote-verified against this). Full title + edition so a page citation is
        # unambiguous on its own.
        "ref": "Kandel, Principles of Neural Science, 6th ed.",
        "citation": "Kandel ER, Koester JD, Mack SH, Siegelbaum SA, eds. "
                    "Principles of Neural Science. 6th ed. McGraw Hill; 2021.",
        "url": "TODO",
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
        "url": "TODO",
        "pages_dir": "data_sources/books/stahl_essential_pharmacology/pages",
    },
    "carlat": {
        # Second drug corpus: cross-sources drug bindings Stahl did not state.
        "ref": "Carlat Medication Fact Book for Psychiatric Practice, 7th ed.",
        "citation": "Carlat DJ. The Carlat Medication Fact Book for Psychiatric "
                    "Practice. 7th ed. Carlat Publishing; 2024.",
        "url": "TODO",
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
        "url": "TODO",
        "pages_dir": "data_sources/books/nieuwenhuys_atlas/pages",
    },
    "gtopdb": {
        # Expression/localization corpus: the IUPHAR/BPS Guide to Pharmacology
        # per-target "Tissue Distribution" statements, backing a receptor/target
        # expression-region claim ("R is found in region B"). Fetched from the GtoPdb
        # web service (tools/fetch_gtopdb.py) and cached author-side as one page per
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
    },
    "pdsp_ki": {
        # Binding-affinity corpus: measured Ki (nM) values backing a drug binding's
        # `ki` annotation. Unlike the book corpora this is a single CSV of assay
        # rows, not paged text, so it has no `pages_dir`; check_data confirms a
        # cited Ki id/value against the `csv` file instead (author-side, skipped on
        # a clone without it, like the quote gate). See tools/fetch_ki.py +
        # data_sources/books/pdsp_ki/README.md.
        "ref": "PDSP Ki Database (NIMH PDSP)",
        "citation": "NIMH Psychoactive Drug Screening Program (PDSP) Ki Database, "
                    "directed by Bryan L. Roth, University of North Carolina at "
                    "Chapel Hill.",
        "url": "https://pdspdb.unc.edu/databases/kidb.php",
        "csv": "data_sources/books/pdsp_ki/KiDatabase.csv",
    },
    "allen_ahba": {
        # Expression corpus: the Allen Human Brain Atlas microarray, backing a
        # receptor/target expression-region claim ("X is found in region B") the
        # GtoPdb tissue comments could not reach (esp. the non-receptor targets +
        # the deep nuclei). tools/fetch_allen.py aggregates Allen's PACall
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
    },
}


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


def _ki_annotation(drug_id: str, binding: dict[str, Any]) -> dict[str, Any] | None:
    """Validate + normalize a binding's PDSP ``ki`` annotation (measured binding
    affinity), or ``None`` when absent.

    Shape: ``{median, min, max, n_human, n_nonhuman, source}`` where ``source`` is
    one specific PDSP CSV row: ``{corpus:"pdsp_ki", ki_id, value_nm, species,
    preparation, radioligand, reference, provenance}`` plus, for a match recovered
    through the alias map (:data:`tools.fetch_ki.ALIAS`), ``mapped``/``measured_as``/
    ``relation``/``pdsp_names`` so the viewer warns *which* compound the Ki was
    measured on. The Ki carries its **own** ``verified`` source (rendered as its own
    badge beside the binding), separate from the binding's quote ``sources``, because
    it is a distinct measurement (an affinity), not a source for the binding node.
    ``check_data.py`` confirms the ``ki_id`` row is really in the corpus CSV.
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
    if prov == "verified" and src.get("ki_id") is None:
        raise ValueError(f"{what} 'verified' source needs a ki_id (the PDSP row id)")
    out_src: dict[str, Any] = {"corpus": corpus, "provenance": prov}
    for f in ("ki_id", "value_nm", "species", "preparation", "radioligand",
              "reference", "note", "mapped", "measured_as", "relation", "pdsp_names"):
        if src.get(f) not in (None, ""):
            out_src[f] = src[f]
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


def _provenance_stats(structures: list[dict[str, Any]],
                      projections: list[dict[str, Any]],
                      circuits: list[dict[str, Any]],
                      projection_groups: list[dict[str, Any]],
                      receptors: list[dict[str, Any]],
                      drugs: list[dict[str, Any]],
                      drug_targets: dict[str, dict[str, Any]]) -> dict[str, Any]:
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
        rank = (rank_or_grade if isinstance(rank_or_grade, int)
                else _GRADE_RANK.get(rank_or_grade, 0))
        # rank <= 1 (no source object, or a bare ``llm`` grade) => no document => missing.
        return ("verified" if rank == 3 else
                "sourced" if rank == 2 else "missing")

    def tally(grades: list[Any]) -> dict[str, int]:
        counts = {"total": 0, "verified": 0, "sourced": 0, "missing": 0}
        for g in grades:
            counts["total"] += 1
            counts[bucket(g)] += 1
        return counts

    binding_grades = [_binding_grade(b)
                      for d in drugs for b in d.get("bindings", [])]
    nbn_grades = [_strongest_grade(d.get("nbn_sources"))
                  for d in drugs if d.get("nbn")]
    # Drug class-classification nodes ("this drug is an SSRI/..."), one per drug that
    # has categories: the emitted category_provenance (llm unless overridden/sourced).
    category_grades = [d.get("category_provenance", DEFAULT_PROVENANCE)
                       for d in drugs if d.get("categories")]
    projection_grades = [_strongest_grade(p.get("sources")) for p in projections]
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

    by_kind = {
        "drug_bindings": tally(binding_grades),
        "drug_nbn": tally(nbn_grades),
        "drug_categories": tally(category_grades),
        "projections": tally(projection_grades),
        "circuits": tally(circuit_grades),
        "projection_groups": tally(projection_group_grades),
        "receptors": tally(receptor_family_grades),
        "receptor_class": tally(receptor_class_grades),
        "receptor_sign": tally(receptor_sign_grades),
        "receptor_synaptic": tally(receptor_synaptic_grades),
        "receptor_locations": tally(receptor_location_grades),
        "targets": tally(target_grades),
        "target_polarity": tally(target_polarity_grades),
        "target_locations": tally(target_location_grades),
        "structures": tally(structure_grades),
        "references": tally(ref_grades),
    }
    # The knowledge-node kinds (every node that carries a claim + a grade) are every
    # by_kind entry except "references" (a reference points *at* a node, so it is
    # tallied but excluded from the headline). Derived from the one by_kind dict above,
    # so adding a node kind is a single-line edit (add it to by_kind) with no second
    # list to keep in sync.
    node_kinds = tuple(k for k in by_kind if k != "references")
    nodes = {"total": 0, "verified": 0, "sourced": 0, "missing": 0}
    for kind in node_kinds:
        for key in nodes:
            nodes[key] += by_kind[kind][key]
    backed = nodes["verified"] + nodes["sourced"]
    nodes["backed"] = backed
    nodes["pct_backed"] = (
        round(100 * backed / nodes["total"]) if nodes["total"] else 0)
    return {"by_kind": by_kind, "nodes": nodes}
