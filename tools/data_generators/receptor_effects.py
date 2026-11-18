"""data_generators.receptor_effects: the ``receptor_effect`` node kind (BETA).

One node = one sourced sentence-level claim "acting on this receptor (or target) in this
**mode** can cause this clinical **effect**" (H1 antagonism -> sedation, D2 antagonism ->
prolactin elevation). It is a statement about the receptor, never about a drug: the
viewer only *derives* a drug's possible effects by joining its directional bindings with
these nodes, worded conditionally, and stores nothing per drug.

The two vocabularies below are closed and emitted into ``meta`` (``receptor_effect_modes``
/ ``receptor_effect_labels``) so the viewer and ``check_data.py`` read them instead of
restating them. Grow :data:`EFFECTS` only when a source states a new effect.

The nodes themselves are written by ``tools/sourcing/apply_receptor_effects.py`` (sole
writer) into ``tools/generated_cache/receptor_effects.json``; :func:`effect_nodes` turns
that cache into the ``effects`` list a receptor record / target entry carries.

Built with the help of Claude Code.
"""
from __future__ import annotations

from typing import Any

from . import caches
from .provenance import _quote_sources
from .quotes.uncertainty import _uncertainty_bullet

CACHE = caches.CACHE_DIR / "receptor_effects.json"

# mode -> label + the binding actions that inherit it in the drug-panel join. The join is
# direction-aware: an antagonist inherits only antagonism effects, an affinity_only
# binding (no action) inherits nothing. ``both`` = the source says either direction
# causes it. ``inhibition`` is the mode of a non-receptor target (a transporter, an
# enzyme), whose drugs are inhibitors, not antagonists.
RECEPTOR_EFFECT_MODES: dict[str, dict[str, Any]] = {
    "agonism": {"label": {"en": "Agonism", "fr": "Agonisme"},
                "actions": ["agonist", "partial_agonist", "pam"]},
    "antagonism": {"label": {"en": "Antagonism", "fr": "Antagonisme"},
                   "actions": ["antagonist", "inverse_agonist", "nam", "blocker"]},
    "both": {"label": {"en": "Agonism or antagonism", "fr": "Agonisme ou antagonisme"},
             "actions": ["agonist", "partial_agonist", "pam",
                         "antagonist", "inverse_agonist", "nam", "blocker"]},
    "inhibition": {"label": {"en": "Inhibition", "fr": "Inhibition"},
                   "actions": ["reuptake_inhibitor", "enzyme_inhibitor",
                               "vesicular_inhibitor", "synthesis_inhibitor", "blocker"]},
}

# effect -> bilingual label. Human / clinical effects only (no knockout phenotype).
RECEPTOR_EFFECTS: dict[str, dict[str, str]] = {
    "sedation": {"en": "Sedation", "fr": "Sédation"},
    "weight_gain": {"en": "Weight gain", "fr": "Prise de poids"},
    "appetite_increase": {"en": "Increased appetite", "fr": "Augmentation de l'appétit"},
    "orthostatic_hypotension": {"en": "Orthostatic hypotension",
                                "fr": "Hypotension orthostatique"},
    "dizziness": {"en": "Dizziness", "fr": "Vertiges"},
    "hallucinations": {"en": "Hallucinations", "fr": "Hallucinations"},
    "prolactin_elevation": {"en": "Prolactin elevation", "fr": "Élévation de la prolactine"},
    "extrapyramidal_symptoms": {"en": "Extrapyramidal symptoms (parkinsonism)",
                                "fr": "Symptômes extrapyramidaux (parkinsonisme)"},
    "tardive_dyskinesia": {"en": "Tardive dyskinesia", "fr": "Dyskinésie tardive"},
    "akathisia": {"en": "Akathisia", "fr": "Akathisie"},
    "anticholinergic_cognitive": {"en": "Memory / cognitive impairment",
                                  "fr": "Troubles mnésiques / cognitifs"},
    "dry_mouth": {"en": "Dry mouth", "fr": "Sécheresse buccale"},
    "hypersalivation": {"en": "Hypersalivation (sialorrhea)",
                        "fr": "Hypersalivation (sialorrhée)"},
    "constipation": {"en": "Constipation", "fr": "Constipation"},
    "blurred_vision": {"en": "Blurred vision", "fr": "Vision trouble"},
    "mydriasis": {"en": "Mydriasis (pupil dilation)", "fr": "Mydriase (pupille dilatée)"},
    "miosis": {"en": "Miosis (pupil constriction)", "fr": "Myosis (pupille contractée)"},
    "urinary_retention": {"en": "Urinary retention", "fr": "Rétention urinaire"},
    "nausea": {"en": "Nausea / vomiting", "fr": "Nausées / vomissements"},
    "sexual_dysfunction": {"en": "Sexual dysfunction", "fr": "Dysfonction sexuelle"},
    "insomnia": {"en": "Insomnia / activation", "fr": "Insomnie / activation"},
    "anxiety": {"en": "Anxiety / agitation", "fr": "Anxiété / agitation"},
    "euphoria": {"en": "Euphoria / reward", "fr": "Euphorie / récompense"},
    "dysphoria": {"en": "Dysphoria", "fr": "Dysphorie"},
    "respiratory_depression": {"en": "Respiratory depression",
                               "fr": "Dépression respiratoire"},
    "seizures": {"en": "Seizures", "fr": "Convulsions"},
    "psychosis": {"en": "Psychosis", "fr": "Psychose"},
    "cardiovascular": {"en": "Raised heart rate / blood pressure",
                       "fr": "Hausse de la fréquence cardiaque / tension"},
    "cardiac_valvulopathy": {"en": "Cardiac valvulopathy", "fr": "Valvulopathie cardiaque"},
    # Therapeutic / non-adverse effects: the drug-panel join is direction-aware, so a
    # 5-HT3 antagonist inherits "antiemetic" without the viewer inverting "nausea".
    "antiemetic": {"en": "Antiemetic effect", "fr": "Effet antiémétique"},
    "anticonvulsant": {"en": "Anticonvulsant effect", "fr": "Effet anticonvulsivant"},
    "anxiolytic": {"en": "Anxiolytic effect", "fr": "Effet anxiolytique"},
    "antidepressant": {"en": "Antidepressant effect", "fr": "Effet antidépresseur"},
    "antipsychotic": {"en": "Antipsychotic effect", "fr": "Effet antipsychotique"},
    "antiparkinsonian": {"en": "Antiparkinsonian effect", "fr": "Effet antiparkinsonien"},
    "analgesia": {"en": "Pain relief (analgesia)", "fr": "Soulagement de la douleur (analgésie)"},
    "antimigraine": {"en": "Migraine relief", "fr": "Soulagement de la migraine"},
    "appetite_decrease": {"en": "Decreased appetite / satiety",
                          "fr": "Diminution de l'appétit / satiété"},
    "pro_cognitive": {"en": "Improved cognition", "fr": "Amélioration cognitive"},
    "sleep_promotion": {"en": "Sleep promotion", "fr": "Induction du sommeil"},
    "circadian_shift": {"en": "Circadian rhythm shift", "fr": "Recalage du rythme circadien"},
    "wakefulness": {"en": "Wakefulness / alertness", "fr": "Éveil / vigilance"},
    "hypothermia": {"en": "Lowered body temperature", "fr": "Baisse de la température corporelle"},
    "bradycardia": {"en": "Slowed heart rate", "fr": "Ralentissement de la fréquence cardiaque"},
    "bronchodilation": {"en": "Bronchodilation", "fr": "Bronchodilatation"},
    "bronchoconstriction": {"en": "Bronchoconstriction", "fr": "Bronchoconstriction"},
    "gastric_acid_reduction": {"en": "Reduced gastric acid secretion",
                               "fr": "Diminution de la sécrétion acide gastrique"},
    "gastric_acid_increase": {"en": "Increased gastric acid secretion",
                              "fr": "Augmentation de la sécrétion acide gastrique"},
    "vasoconstriction": {"en": "Vasoconstriction", "fr": "Vasoconstriction"},
    "vasodilation": {"en": "Vasodilation", "fr": "Vasodilatation"},
    "bladder_relaxation": {"en": "Bladder relaxation", "fr": "Relâchement de la vessie"},
    "gi_motility": {"en": "Increased gut motility (prokinetic)",
                    "fr": "Augmentation de la motilité digestive (prokinétique)"},
    # Effects of losing a receptor's function (a loss-of-function variant or a blocking
    # autoantibody, stated by the source in humans): named as the effect, never the disease.
    "muscle_weakness": {"en": "Muscle weakness / paralysis",
                        "fr": "Faiblesse musculaire / paralysie"},
    "exaggerated_startle": {"en": "Exaggerated startle reflex",
                            "fr": "Réflexe de sursaut exagéré"},
    "night_blindness": {"en": "Night blindness", "fr": "Cécité nocturne"},
    "itch": {"en": "Itch (pruritus)", "fr": "Démangeaisons (prurit)"},
    "antipruritic": {"en": "Itch relief (antipruritic)",
                     "fr": "Soulagement des démangeaisons (antiprurigineux)"},
    "ataxia": {"en": "Ataxia (loss of coordination)", "fr": "Ataxie (perte de coordination)"},
}


# How a picked sentence's evidence was obtained, read by the picker at judge time and
# stored per source by the applier: ``isolated_tissue`` = an isolated human tissue
# preparation only (a vessel ring, a mucosa strip), ``in_vivo`` = anything stated of a
# living person or clinical use. A node whose EVERY source is ``isolated_tissue`` wears
# the derived ``isolated_tissue`` uncertainty bullet (:func:`effect_nodes`).
EFFECT_EVIDENCE: tuple[str, ...] = ("in_vivo", "isolated_tissue")


def _key(mode: str, effect: str) -> str:
    """The cache key of one node under its owner (``<mode>:<effect>``)."""
    return f"{mode}:{effect}"


def load_cache() -> dict[str, dict[str, list]]:
    """``{owner id: {"<mode>:<effect>": [source, ...]}}`` (empty when not built yet)."""
    return caches.load(CACHE.name, required=False)


def effect_nodes(owner: str, cache: dict[str, dict[str, list]],
                 owner_kind: str) -> list[dict[str, Any]]:
    """The ``effects`` list one receptor record / target entry carries, sorted.

    Each item ``{mode, effect, sources, grade, uncertainty?}`` is ONE node (kind
    ``receptor_effect``); ``uncertainty`` holds the derived ``isolated_tissue`` bullet.
    An unknown mode or effect in the cache fails the build: the vocabularies are closed.
    """
    out: list[dict[str, Any]] = []
    for key, srcs in sorted((cache.get(owner) or {}).items()):
        mode, _, effect = key.partition(":")
        if mode not in RECEPTOR_EFFECT_MODES or effect not in RECEPTOR_EFFECTS:
            raise KeyError(f"{owner_kind} {owner!r} effect {key!r}: mode or effect not "
                           f"in RECEPTOR_EFFECT_MODES / RECEPTOR_EFFECTS")
        what = f"{owner_kind} {owner!r} effect {key!r}"
        sources = _quote_sources(srcs, what)
        if not sources:
            continue
        node = {"mode": mode, "effect": effect, "sources": sources,
                "grade": "verified" if any(s["provenance"] == "verified"
                                           for s in sources) else "sourced"}
        if all(s.get("evidence") == "isolated_tissue" for s in srcs):
            node["uncertainty"] = [_uncertainty_bullet("isolated_tissue", what=what,
                                                       node=node, source=sources)]
        out.append(node)
    return out


def meta_vocab() -> dict[str, Any]:
    """The two closed vocabularies, emitted into ``meta`` (labels stay bilingual: the
    serialization-time ``externalize`` pass collapses them like every other ``{en,fr}``)."""
    return {
        "receptor_effect_modes": {m: {"label": dict(v["label"]), "actions": list(v["actions"])}
                                  for m, v in RECEPTOR_EFFECT_MODES.items()},
        "receptor_effect_labels": {e: dict(v) for e, v in RECEPTOR_EFFECTS.items()},
    }
