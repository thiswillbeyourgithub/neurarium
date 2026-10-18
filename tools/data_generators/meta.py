"""data_generators.meta: the ``meta.json`` object.

Presentation metadata (its own file) so a consumer reading the dataset is
self-contained: arrow colours, legend headings, every closed vocabulary the viewer
renders and the programmatic sourcing tally live in the data, not only in the
viewer's JS. Called by ``generate_data.build_records`` once every record is built
and validated (it calls ``_t()``, so it runs after the missing-translation guard).
"""

from __future__ import annotations

from typing import Any

from data_generators import clinpgx as CLINPGX
from data_generators import demographics as DEMOG
from data_generators import formulations, history, provenance, workup
from data_generators import receptor_effects as REFFECTS
from data_generators import release_modulation as RELMOD
from data_generators.addons import (
    ADDON_BASES,
    ADDON_DISPLAYS,
    ADDON_SECTIONS,
    ADDON_SLOTS,
    ADDON_TONES,
)
from data_generators.drugs import (
    DRUG_ACTIONS,
    DRUG_CATEGORY_LABELS,
    DRUG_EFFECT_COLORS,
    DRUG_EFFECT_LABELS,
    ENZYME_REACTIONS,
    ENZYME_ROLES,
    ENZYME_STRENGTHS,
    ENZYMES,
    METABOLIZER_GROUPS,
    METABOLIZER_PHENOTYPES,
    TARGET_TYPE_COLORS,
    TARGET_TYPE_LABELS,
    TONE_FACTORS,
    TONE_RULES,
)
from data_generators.i18n import _t
from data_generators.presentation import (
    GROUP_LABELS,
    KIND_TO_SIGN,
    PROJECTION_COLORS,
    RECEPTOR_CLASS_LABELS,
    RECEPTOR_FAMILY_COLORS,
    RECEPTOR_FAMILY_LABELS,
    SIGN_COLORS,
    SIGN_LABELS,
    SYNAPTIC_LABELS,
    SYSTEM_FLOW_KINDS,
)
from data_generators.corpora import SOURCE_CORPORA
from data_generators.provenance import (
    QUOTE_PIPELINES,
    _provenance_stats,
    build_enzymes,
)
from data_generators.quotes import UNCERTAINTY_REASONS


def build_meta(*, structures, projections, circuits, projection_groups, receptors,
                drug_targets, drugs, metabolites, addons) -> dict[str, Any]:
    """The ``meta.json`` object: presentation maps, vocabularies and the tally."""
    # Presentation metadata (its own meta.json) so a consumer reading the dataset
    # is self-contained: arrow colours + legend headings live in the data, not
    # only in the viewer's JS.
    enzymes = build_enzymes(ENZYMES)

    meta = {
        # Both presentation maps are emitted bilingually: the kind->arrow colour
        # map is language-neutral, but kind_labels/group_labels carry {en, fr}
        # display strings the viewer resolves via window.__I18N__.pick.
        "projection_colors": PROJECTION_COLORS,
        "kind_labels": {kind: _t(kind) for kind in PROJECTION_COLORS},
        "group_labels": {g: _t(label) for g, label in GROUP_LABELS.items()},
        # Sign (excitatory / inhibitory) colour mode: kind->sign fold, sign->colour
        # swatch (language-neutral) and sign->{en,fr} legend heading. The viewer's
        # colour toggle reads these so neither palette nor labels are hardcoded.
        "kind_signs": KIND_TO_SIGN,
        "sign_colors": SIGN_COLORS,
        "sign_labels": {sign: _t(label) for sign, label in SIGN_LABELS.items()},
        # Drug target system -> projection kind, for the per-drug flow overlay (see
        # SYSTEM_FLOW_KINDS). Language-neutral keys both sides.
        "system_flow_kinds": SYSTEM_FLOW_KINDS,
        # Which bindings set a transmitter's tone, and which way (see TONE_RULES).
        # Emitted rather than transcribed because two consumers need the same rule:
        # the viewer animates it and check_data cross-checks it.
        "tone_rules": TONE_RULES,
        "tone_factors": TONE_FACTORS,
        # Receptor legend maps: family -> heading, mechanism class -> label, and
        # pre/post-synaptic -> label (all bilingual). The per-receptor sign reuses
        # sign_colors / sign_labels above, so the receptor legend needs no extra
        # colour map. Object key order is the legend's family display order.
        "receptor_family_labels": {
            f: _t(label) for f, label in RECEPTOR_FAMILY_LABELS.items()},
        # Family -> swatch colour (language-neutral), the transmitter's own colour
        # wherever a view colours by transmitter rather than by drug effect.
        "receptor_family_colors": dict(RECEPTOR_FAMILY_COLORS),
        "receptor_class_labels": {
            c: _t(label) for c, label in RECEPTOR_CLASS_LABELS.items()},
        "synaptic_labels": {
            s: _t(label) for s, label in SYNAPTIC_LABELS.items()},
        # Drug legend + animation maps (already bilingual; see the drug schema
        # block near the top). drug_targets merges DRUG_TARGETS with every
        # receptor id so a binding can target either.
        "drug_category_labels": DRUG_CATEGORY_LABELS,
        # Regulatory history vocabularies (first approval + withdrawals): id -> {en,fr}.
        "drug_releases": formulations.labels(),
        "drug_history_countries": history.labels(history.COUNTRIES),
        "drug_history_scopes": list(history.SCOPES),
        "drug_history_agencies": history.labels(history.AGENCIES),
        "drug_withdrawal_reasons": history.labels(history.WITHDRAWAL_REASONS),
        # Pre-prescription workup vocabularies (BETA, data_generators/workup.py).
        "workup_tests": workup.labels(workup.TESTS),
        "workup_timings": workup.labels(workup.TIMINGS),
        # Merged binding-target map (DRUG_TARGETS + every receptor id), plus the
        # non-receptor target type -> {en,fr} tag and type -> swatch colour the
        # merged "Receptors & targets" legend reads (receptors keep their sign
        # swatch, so target_type_colors omits "receptor").
        "drug_targets": drug_targets,
        "target_type_labels": {
            ty: _t(label) for ty, label in TARGET_TYPE_LABELS.items()},
        "target_type_colors": TARGET_TYPE_COLORS,
        "drug_actions": DRUG_ACTIONS,
        "drug_effect_colors": DRUG_EFFECT_COLORS,
        "drug_effect_labels": DRUG_EFFECT_LABELS,
        # Drug metabolism vocabularies (see ENZYMES in data_generators.drugs): the
        # enzyme id -> {label, wikipedia} map the Metabolism rows and the Enzymes
        # browse section read, plus the role and strength labels. Self-describing so
        # the viewer never hardcodes an isoform name or a role heading.
        "enzymes": enzymes,
        # How fast a person clears a drug through one enzyme, and the population
        # groups PharmFreq (corpus #13) aggregates that over. Ordered vocabularies,
        # emitted so the panel never hardcodes a phenotype letter or a group name.
        "metabolizer_phenotypes": METABOLIZER_PHENOTYPES,
        "metabolizer_groups": METABOLIZER_GROUPS,
        "enzyme_roles": ENZYME_ROLES,
        "enzyme_strengths": ENZYME_STRENGTHS,
        "enzyme_reactions": ENZYME_REACTIONS,
        # receptor_effect vocabularies (BETA): mode -> {label, actions the drug-panel
        # join lets inherit it}, effect -> label. See data_generators/receptor_effects.py.
        **REFFECTS.meta_vocab(),
        # receptor_release_modulation vocabularies (BETA): kinds, cells, transmitters
        # (+ the receptor-system name each joins on). See data_generators/release_modulation.py.
        **RELMOD.meta_vocab(),
        # receptor_demographic vocabularies (BETA): factor -> {label, directions}.
        # See data_generators/demographics.py.
        **DEMOG.meta_vocab(),
        # receptor_variant vocabularies: evidence levels, categories, populations.
        **CLINPGX.meta_vocab(),
        # Source corpora the per-binding (and later per-field) drug sources cite,
        # keyed by id (see SOURCE_CORPORA). The viewer reads citation/url to render
        # each binding's source; check_data.py reads pages_dir to confirm quotes.
        # Self-describing so a port needs no hardcoded citation.
        "source_corpora": SOURCE_CORPORA,
        # Addon-node hook registry (see data_generators/addons.py): the slots the
        # viewer offers (slot -> the node kind whose panel it is in), the display
        # forms it can draw, and the tone -> glyph vocabulary. Emitted rather than
        # hardcoded in JS for the usual reason: an addon says where it goes, so the
        # set of legal answers is part of the data contract, and check_data.py reads
        # the same list the generator validated against.
        "addon_slots": ADDON_SLOTS,
        # The browse sections an addon may anchor instead of a node (section key ->
        # its label): the one owner kind with no panel to open, for a caveat about a
        # whole view rather than about one datum.
        "addon_sections": ADDON_SECTIONS,
        "addon_displays": list(ADDON_DISPLAYS),
        "addon_tones": ADDON_TONES,
        # What an addon is a claim about (see addons.ADDON_BASES): a `dataset`
        # statement draws its own neutral pill and stays out of the tally.
        "addon_bases": list(ADDON_BASES),
        # The closed vocabulary of "uncertain" reason kinds (see quotes/uncertainty.py).
        # Emitted so the viewer knows which i18n sentence a bullet takes and check_data.py
        # can reject a kind that is not one of these, from one list rather than three.
        "uncertainty_reasons": UNCERTAINTY_REASONS,
        # How a quote came to be cited: pipeline key -> its chain of custody, as ordered
        # step keys (i18n `quotechain.<step>`). Every green pill looks the same, but a
        # quote a parser copied out of a table and a quote a model read off a book page
        # are different evidence, so each source tooltip ends with the chain that
        # produced it. Emitted rather than hardcoded in JS for the usual reason: adding a
        # pipeline is a data edit plus its translations, never a viewer edit.
        "quote_pipelines": {k: list(v) for k, v in QUOTE_PIPELINES.items()},
        # Cross-donor-agreement floor a relative-expression profile had to clear to be
        # published (see the density pass in tools/fetch/fetch_allen.py). Emitted so the
        # panel can state the real threshold instead of restating the constant. Absent
        # when no density has been applied.
        **({"density_min_reliability": provenance.DENSITY_MIN_RELIABILITY}
           if provenance.DENSITY_MIN_RELIABILITY is not None else {}),
        # Programmatic sourcing tally over the shipped data (per-kind + headline);
        # the About panel + README read it so the "% sourced" figure is a real
        # count, never hand-typed. See _provenance_stats.
        "provenance_stats": _provenance_stats(
            structures, projections, circuits, projection_groups,
            receptors, drugs, metabolites, drug_targets, addons, enzymes),
    }
    return meta
