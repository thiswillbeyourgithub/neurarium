"""data_generators.integrity: referential-integrity checks on the hand-authored tables.

A key that names a thing that does not exist (a typo'd receptor id, a projection that
was renamed, a region that was merged) is silently inert: its quote grades nothing, its
alias finds nothing, its addon is drawn nowhere. Every check here turns that silent loss
into a build failure. They are pure (read the authored tables, plus whatever built
records a check needs as arguments, and raise), so ``generate_data.build_records`` calls
each at the point its inputs exist and the first failure a broken dataset reports is
always the same one.
"""

from __future__ import annotations

from typing import Any, Iterable

from data_generators.addons import ADDON_SECTIONS
from data_generators.connectivity import PROJECTIONS
from data_generators.drugs import (
    DRUG_ACTIONS,
    DRUG_ALIASES,
    DRUG_NAME_QUALIFIERS,
    DRUG_STEREO_FORMS,
    DRUG_TARGETS,
    TARGET_TYPE_LABELS,
    TONE_FACTORS,
    TONE_RULES,
)
from data_generators.genes import RECEPTOR_GENES, TARGET_GENES
from data_generators.presentation import GROUP_LABELS, PROJECTION_COLORS, WIKIPEDIA
from data_generators.provenance import TARGET_POLARITY_PROVENANCE
from data_generators.quotes import (
    CLASSIFICATION_ATTRS,
    METABOLITE_ENZYME_QUOTES,
    PROJECTION_QUOTES,
    PROJECTION_SOURCES,
    RECEPTOR_ATTR_QUOTES,
    RECEPTOR_CLASSIFICATION_COVERAGE,
    STAHL_ESSENTIAL_RECEPTOR_QUOTES,
    STAHL_ESSENTIAL_TARGET_QUOTES,
    STRUCTURE_QUOTES,
    TARGET_POLARITY_QUOTES,
)
from data_generators.receptors import RECEPTORS
from data_generators.regions import STRUCTURE_ALIASES, structure_bases


def validate_quote_registries() -> None:
    """Every quote / coverage registry key must address a real authored node."""
    # Typo guard: every PROJECTION_QUOTES key must address a real PROJECTIONS entry,
    # else its quote silently sources nothing.
    unmatched = set(PROJECTION_QUOTES) - {(p["from"], p["to"]) for p in PROJECTIONS}
    if unmatched:
        raise KeyError(
            f"PROJECTION_QUOTES keys match no PROJECTIONS entry: {sorted(unmatched)}")
    unmatched = set(PROJECTION_SOURCES) - {(p["from"], p["to"]) for p in PROJECTIONS}
    if unmatched:
        raise KeyError(
            f"projection_sources.json keys match no PROJECTIONS entry: {sorted(unmatched)}")
    unmatched_bases = set(STRUCTURE_QUOTES) - structure_bases()
    if unmatched_bases:
        raise KeyError(
            f"STRUCTURE_QUOTES keys are not structure bases: "
            f"{sorted(unmatched_bases)}")
    unmatched_rq = set(STAHL_ESSENTIAL_RECEPTOR_QUOTES) - {r["id"] for r in RECEPTORS}
    if unmatched_rq:
        raise KeyError(
            f"STAHL_ESSENTIAL_RECEPTOR_QUOTES keys are not receptor ids: "
            f"{sorted(unmatched_rq)}")
    # Every quoted receptor needs a coverage entry (else its quote would grade
    # nothing) and vice-versa (a coverage entry with no quote grades nothing), and
    # each covered attribute must be a real classification attribute. This keeps the
    # per-attribute grading honest: a quote can only lift the attributes it names.
    cov_no_quote = set(RECEPTOR_CLASSIFICATION_COVERAGE) - set(STAHL_ESSENTIAL_RECEPTOR_QUOTES)
    quote_no_cov = set(STAHL_ESSENTIAL_RECEPTOR_QUOTES) - set(RECEPTOR_CLASSIFICATION_COVERAGE)
    if cov_no_quote or quote_no_cov:
        raise KeyError(
            "RECEPTOR_CLASSIFICATION_COVERAGE must match the receptor-quote keys "
            f"(coverage without quote: {sorted(cov_no_quote)}; quote without "
            f"coverage: {sorted(quote_no_cov)})")
    bad_attrs = {a for attrs in RECEPTOR_CLASSIFICATION_COVERAGE.values()
                 for a in attrs if a not in CLASSIFICATION_ATTRS}
    if bad_attrs:
        raise KeyError(
            f"RECEPTOR_CLASSIFICATION_COVERAGE has unknown attributes: "
            f"{sorted(bad_attrs)} (valid: {CLASSIFICATION_ATTRS})")
    # Per-attribute quote overrides must key real receptors and real attributes.
    aq_no_receptor = set(RECEPTOR_ATTR_QUOTES) - {r["id"] for r in RECEPTORS}
    if aq_no_receptor:
        raise KeyError(
            f"RECEPTOR_ATTR_QUOTES keys are not receptor ids: {sorted(aq_no_receptor)}")
    bad_aq_attrs = {a for m in RECEPTOR_ATTR_QUOTES.values()
                    for a in m if a not in CLASSIFICATION_ATTRS}
    if bad_aq_attrs:
        raise KeyError(
            f"RECEPTOR_ATTR_QUOTES has unknown attributes: {sorted(bad_aq_attrs)} "
            f"(valid: {CLASSIFICATION_ATTRS})")
    unmatched_tq = set(STAHL_ESSENTIAL_TARGET_QUOTES) - set(DRUG_TARGETS)
    if unmatched_tq:
        raise KeyError(
            f"STAHL_ESSENTIAL_TARGET_QUOTES keys are not DRUG_TARGETS ids: "
            f"{sorted(unmatched_tq)}")
    # A polarity quote must key a target that actually carries a polarity flag,
    # else it grades a direction claim that is never emitted.
    polarity_ids = {tid for tid, spec in DRUG_TARGETS.items()
                    if any(f in spec for f in ("vesicular", "sign", "synaptic"))}
    unmatched_pq = set(TARGET_POLARITY_QUOTES) - polarity_ids
    if unmatched_pq:
        raise KeyError(
            f"TARGET_POLARITY_QUOTES keys have no polarity flag in DRUG_TARGETS: "
            f"{sorted(unmatched_pq)}")
    unmatched_pp = set(TARGET_POLARITY_PROVENANCE) - polarity_ids
    if unmatched_pp:
        raise KeyError(
            f"TARGET_POLARITY_PROVENANCE keys have no polarity flag in "
            f"DRUG_TARGETS: {sorted(unmatched_pp)}")


def validate_drug_targets() -> None:
    """Every DRUG_TARGETS entry: a non-receptor type, an http(s) link, known regions.

    A region must be a known structure base (typo guard), like a receptor location.
    """
    bases = structure_bases()
    for tid, spec in DRUG_TARGETS.items():
        if spec["type"] not in TARGET_TYPE_LABELS or spec["type"] == "receptor":
            raise KeyError(
                f"DRUG_TARGETS[{tid!r}] type {spec['type']!r} is not a "
                f"non-receptor TARGET_TYPE_LABELS key")
        wiki = spec.get("wikipedia")
        if wiki is not None and not str(wiki).startswith(("http://", "https://")):
            raise ValueError(
                f"DRUG_TARGETS[{tid!r}] wikipedia must be an http(s) URL or absent")
        for base in spec["regions"]:
            if base not in bases:
                raise KeyError(
                    f"DRUG_TARGETS[{tid!r}] region {base!r} is not a known "
                    f"structure base")


def validate_drug_aliases(drug_ids: set[str]) -> None:
    """Fail loud if a search alias is keyed on a drug id that does not exist.

    An alias keyed on a typo is silently inert (nothing ever looks it up), which
    would read as "GHB still doesn't find it" with nothing to grep for.
    """
    stereo = {d for group in DRUG_STEREO_FORMS for d in group}
    for name, table in (("DRUG_ALIASES", DRUG_ALIASES),
                        ("DRUG_NAME_QUALIFIERS", DRUG_NAME_QUALIFIERS),
                        ("DRUG_STEREO_FORMS", stereo)):
        unknown = sorted(set(table) - drug_ids)
        if unknown:
            raise SystemExit(
                f"{name} keys are not drug ids: {unknown}; "
                f"fix the id or drop the entry"
            )


def validate_metabolite_enzyme_quotes(seen: set[tuple[str, str]]) -> None:
    """A hand-curated formed_by row whose (drug, metabolite) key matched nothing.

    The metabolite was renamed or dropped by an applier re-run, so the node silently
    vanished. Raise rather than publish a quieter dataset than the author wrote.
    ``seen`` is every key the drug build consumed.
    """
    orphans = sorted(set(METABOLITE_ENZYME_QUOTES) - seen)
    if orphans:
        raise KeyError(
            "METABOLITE_ENZYME_QUOTES keys match no metabolite in drugs_data.jsonl: "
            + ", ".join(f"{d}/{n}" for d, n in orphans))


def validate_addon_owners(addons: Iterable[dict[str, Any]], *, drug_ids: set[str],
                          receptor_ids: set[str], target_ids: set[str]) -> None:
    """Every addon must anchor a node that exists.

    Each addon carries its own insertion point, so the only cross-check its module
    cannot do on its own is whether the anchored node exists. A typo'd owner would
    emit a node the viewer never draws (it looks up addons by owner id), which is
    exactly the silent loss the fail-loud rule exists for.
    """
    pools = {
        "drug": drug_ids,
        "receptor": receptor_ids,
        "target": target_ids,
        # A structure addon anchors the *base* (both hemispheres show it), matching
        # how a receptor location or a density profile keys its regions.
        "structure": structure_bases(),
        # A section addon anchors a view, not a node, so its pool is the closed
        # section vocabulary itself (see addons.ADDON_SECTIONS).
        "section": set(ADDON_SECTIONS),
    }
    for addon in addons:
        pool = pools[addon["owner_kind"]]
        if addon["owner"] not in pool:
            raise KeyError(
                f"Addon {addon['id']!r} anchors {addon['owner_kind']} "
                f"{addon['owner']!r}, which is not a known "
                f"{addon['owner_kind']} id")


def validate_presentation_maps(projections: Iterable[dict[str, Any]],
                               structures: Iterable[dict[str, Any]]) -> None:
    """Fail loudly if the data uses a kind or group with no presentation-map entry."""
    kinds = {r["kind"] for r in projections}
    missing_kinds = kinds - PROJECTION_COLORS.keys()
    if missing_kinds:
        raise KeyError(
            f"Projection kind(s) with no PROJECTION_COLORS entry: "
            f"{sorted(missing_kinds)}")
    groups = {r["group"] for r in structures}
    missing_groups = groups - GROUP_LABELS.keys()
    if missing_groups:
        raise KeyError(
            f"Structure group(s) with no GROUP_LABELS entry: "
            f"{sorted(missing_groups)}")
    unknown_wiki = WIKIPEDIA.keys() - structure_bases()
    if unknown_wiki:
        raise KeyError(
            f"WIKIPEDIA entry for unknown structure base(s): "
            f"{sorted(unknown_wiki)}")


def validate_translations(missing: set[str]) -> None:
    """Every translatable string went through _t(); fail loudly (listing them all)
    if any had no FR entry, so the data can't ship half-translated."""
    if missing:
        raise KeyError(
            "Missing FR translation for: "
            + "; ".join(repr(s) for s in sorted(missing)))


# --- write-time checks (run by generate_data.write_artifacts, before any file is written)

def validate_structure_aliases() -> None:
    """Fail loud when a STRUCTURE_ALIASES key is not a region base id (a typo would
    be silently inert, exactly like a DRUG_ALIASES one)."""
    unknown = sorted(set(STRUCTURE_ALIASES) - structure_bases())
    if unknown:
        raise SystemExit(
            f"STRUCTURE_ALIASES keys are not region base ids: {unknown}; "
            f"fix the id or drop the entry"
        )


def validate_genes() -> None:
    """Fail loud if a modeled receptor / target has no gene symbol.

    The maps live with the fetchers (see data_generators.genes), so a rename on
    either side would otherwise drop the gene silently: the panel would just stop
    offering the gene-keyed ClinPGx link for that node, with nothing to grep for.
    Checked in this direction (coverage, not key validity) because the fetcher maps
    deliberately also bucket a few receptor *families* that are not target ids.
    """
    missing = sorted(tid for tid in DRUG_TARGETS if tid not in TARGET_GENES)
    if missing:
        raise SystemExit(
            f"drug target(s) with no gene symbol: {missing}; add them to "
            f"TARGET_GENES in tools/lib/gene_maps.py")
    # A receptor carrying regions is one a reader can look up; the stubs (no regions,
    # e.g. the rodent-only alpha2d) have no human gene and are exempt.
    missing = sorted(r["id"] for r in RECEPTORS
                     if r["locations"] and r["id"] not in RECEPTOR_GENES)
    if missing:
        raise SystemExit(
            f"receptor(s) with no gene symbol: {missing}; add them to RECEPTOR_GENES "
            f"(or EXTRA_RECEPTOR_GENES) in tools/lib/gene_maps.py")


def validate_tone_rules() -> None:
    """Fail loud if a tone rule names an action the drug vocabulary does not have.

    A rule keyed on a typo is invisible at runtime: the action simply never matches,
    the binding contributes no tone, and the drug quietly loses its flow overlay. So
    the keys are confirmed against :data:`DRUG_ACTIONS` at generation instead, where a
    mistake stops the build (the same fail-loud rule the rest of the generator uses).
    """
    for bucket, rules in TONE_RULES.items():
        for action, rule in rules.items():
            if action not in DRUG_ACTIONS:
                raise SystemExit(
                    f"TONE_RULES[{bucket!r}] names unknown action {action!r}; "
                    f"add it to DRUG_ACTIONS or fix the typo"
                )
            if len(rule) != 2 or rule[0] not in (1, -1):
                raise SystemExit(
                    f"TONE_RULES[{bucket!r}][{action!r}] must be [+1|-1, mechanism]"
                )
    for bucket, factor in TONE_FACTORS.items():
        if bucket not in TONE_RULES or not 0 < factor <= 1:
            raise SystemExit(f"TONE_FACTORS[{bucket!r}] must name a TONE_RULES bucket, 0 < factor <= 1")
