"""Whether a drug lowers or raises the seizure threshold, or causes seizures when stopped.

Node kind ``drug_seizure_threshold`` (BETA): ONE node per (drug, effect), a claim about
the drug itself (not a receptor: a label or a trial says "bupropion lowers the seizure
threshold" without naming a mechanism). Three effects, a closed vocabulary:

* ``lowers``: the drug can lower the seizure threshold / provoke seizures at use
  (French RCP 4.4 "peut abaisser le seuil épileptogène", Pisani 2002's "relatively high
  seizurogenic potential", Alper 2007's higher seizure incidence than placebo);
* ``withdrawal``: stopping it, abruptly, can cause seizures (benzodiazepines,
  anticonvulsants: "l'arrêt brutal ... peut entraîner des convulsions");
* ``raises``: it raises the seizure threshold (an anticonvulsant effect).

Read off the French RCP sections 4.2-4.4 (corpus #24 ``bdpm_rcp``) and a few Europe PMC
abstracts that rank drugs (corpus #17, ``fetch_seizure_threshold.SEIZURE_PAPERS``). Each
effect carries patterns its quote must ALL match (``requires``), so the applier
(``tools/sourcing/apply_seizure_threshold.py``) refuses a pick whose sentence does not
itself speak of seizures (and, for ``withdrawal``, of stopping), and the fetcher
(``tools/fetch/fetch_seizure_threshold.py``) offers lines on the same seizure pattern.
Labels are bilingual inline, emitted into meta ``seizure_threshold_effects``. Data lives
in the committed ``tools/generated_cache/seizure_threshold.json`` (applier-written).

Built with the help of Claude Code.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from . import caches

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


def says(effect: str, *texts: str | None) -> bool:
    """Whether one of ``texts`` matches every pattern ``effect`` requires."""
    pats = (EFFECTS.get(effect) or {}).get("requires") or ()
    return bool(pats) and any(
        t and all(re.search(p, t, re.IGNORECASE) for p in pats) for t in texts)


def about_seizures(text: str) -> bool:
    """Whether ``text`` speaks of seizures at all (what the fetcher offers)."""
    return bool(re.search(SEIZURE, text or "", re.IGNORECASE))


def meta_labels() -> dict[str, dict[str, str]]:
    """The ``seizure_threshold_effects`` meta map: effect -> ``{en, fr}``."""
    return {k: {"en": v["en"], "fr": v["fr"]} for k, v in EFFECTS.items()}


_DATA = caches.load(CACHE.name, required=False)


def drug_seizure_threshold(drug_id: str, quote_sources: Callable, data: dict | None = None
                           ) -> dict[str, Any]:
    """The emitted ``seizure_threshold`` field of one drug: ``[{effect, sources}]`` in
    vocabulary order, or ``{}``. ``quote_sources`` is ``provenance._quote_sources``.
    Validates against the vocabulary so a hand edit of the cache fails the build."""
    rows = ((data if data is not None else _DATA).get("drugs") or {}).get(drug_id) or []
    out, seen = [], set()
    for r in rows:
        effect = r.get("effect")
        what = f"Drug {drug_id!r} seizure threshold {effect!r}"
        if effect not in EFFECTS:
            raise KeyError(f"{what}: not in seizure_threshold.EFFECTS")
        if effect in seen:
            raise ValueError(f"{what}: duplicate effect node")
        seen.add(effect)
        if not r.get("sources"):
            raise ValueError(f"{what}: no source")
        out.append({"effect": effect, "sources": quote_sources(r["sources"], what)})
    order = {k: i for i, k in enumerate(EFFECTS)}
    out.sort(key=lambda r: order[r["effect"]])
    return {"seizure_threshold": out} if out else {}
