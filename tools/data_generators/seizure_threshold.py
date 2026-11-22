"""Whether a drug lowers or raises the seizure threshold, or causes seizures when stopped.

Node kind ``drug_seizure_threshold`` (BETA): ONE node per (drug, effect), a claim about
the drug itself (not a receptor: a label or a trial says "bupropion lowers the seizure
threshold" without naming a mechanism). Three effects, a closed vocabulary:

* ``lowers``: the source states, for this drug and without hedging, that it lowers the
  seizure threshold / provokes seizures at use
  (French RCP 4.4 "peut abaisser le seuil épileptogène", Pisani 2002's "relatively high
  seizurogenic potential", Alper 2007's higher seizure incidence than placebo);
* ``possibly_lowers``: a hedged statement ("risque potentiel", "possibilité", isolated
  reported cases) or one only about the drug's class (fluoxetine's "comme avec d'autres
  antidépresseurs"); a drug with a ``lowers`` node never also carries this one;
* ``withdrawal``: stopping it, abruptly, can cause seizures (benzodiazepines,
  anticonvulsants: "l'arrêt brutal ... peut entraîner des convulsions");
* ``raises``: it raises the seizure threshold (an anticonvulsant effect).

Read off the French RCP sections 4.2-4.4 (corpus #24 ``bdpm_rcp``) and a few Europe PMC
abstracts that rank drugs (corpus #17, ``fetch_seizure_threshold.SEIZURE_PAPERS``). Each
effect carries patterns its quote must ALL match (``requires``), so the applier
(``tools/sourcing/apply_seizure_threshold.py``) refuses a pick whose sentence does not
itself speak of seizures (and, for ``withdrawal``, of stopping), and the fetcher
(``tools/fetch/fetch_seizure_threshold.py``) offers lines on the same seizure pattern.
Labels are bilingual inline, emitted into meta ``drug_effect_kinds``. Data lives
in the committed ``tools/generated_cache/seizure_threshold.json`` (applier-written).

Built with the help of Claude Code.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from . import caches
from .drug_effects import DrugEffectKind

CACHE = caches.CACHE_DIR / "seizure_threshold.json"

# A sentence about seizures, in either language (the RCPs are French, the papers English).
# A bare "crise" is not enough ("crise hypertensive", "contrôle des crises" dosing).
SEIZURE = r"convuls|seizur|[ée]pilep|comitial|seuil [ée]pileptog|seuil convuls"

# Stopping the drug: what a ``withdrawal`` quote must also say.
STOPPING = r"sevrage|arr[êe]t|interrup|withdraw|discontinu|brutal|abrupt"

# Effect -> {en, fr, requires}. Order is display order.
EFFECTS: dict[str, dict[str, Any]] = {
    "lowers": {"en": "Lowers the seizure threshold", "fr": "Abaisse le seuil épileptogène",
               "requires": (SEIZURE,)},
    # Hedged ("risque potentiel", "possibilité d'abaissement", isolated reported cases) or
    # only a statement about the drug's class ("comme les autres antidépresseurs").
    "possibly_lowers": {"en": "May lower the seizure threshold",
                        "fr": "Pourrait abaisser le seuil épileptogène",
                        "requires": (SEIZURE,)},
    "withdrawal": {"en": "Seizures when stopped abruptly",
                   "fr": "Convulsions à l'arrêt brutal",
                   "requires": (SEIZURE, STOPPING)},
    "raises": {"en": "Raises the seizure threshold (anticonvulsant)",
               "fr": "Élève le seuil épileptogène (anticonvulsivant)",
               # An indication counts: "traitement des épilepsies partielles" (RCP 4.1).
               "requires": (r"anticonvuls|anti-?[ée]pilep|antiepilep|anticomitial|"
                            r"(?:traitement|indiqu|treatment|indicated)\w*\b[^.]{0,80}"
                            r"(?:[ée]pilep|convuls|crises|seizures)|"
                            r"(?:raises?|increases?|[ée]l[èe]ve|augmente)\w* (?:the |le )?"
                            r"(?:seizure )?(?:threshold|seuil)",)},
}


KIND = DrugEffectKind("drug_seizure_threshold", "seizure_threshold", "seizure threshold",
                      CACHE, EFFECTS, exclusive=(("lowers", "possibly_lowers"),),
                      section="seizure")
says, meta_labels = KIND.says, KIND.meta_labels


def about_seizures(text: str) -> bool:
    """Whether ``text`` speaks of seizures at all (what the fetcher offers)."""
    return bool(re.search(SEIZURE, text or "", re.IGNORECASE))


def drug_seizure_threshold(drug_id: str, quote_sources: Callable, data: dict | None = None
                           ) -> dict[str, Any]:
    """The emitted ``seizure_threshold`` field of one drug (see ``DrugEffectKind``)."""
    return KIND.drug_nodes(drug_id, quote_sources, data)
