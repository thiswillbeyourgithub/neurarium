"""What a drug does to sleep: total sleep, sleep onset, sleep stages, sedation.

Node kind ``drug_sleep`` (BETA): ONE node per (drug, effect), a claim about the drug
itself as a review states it ("Doxepin strongly increases total sleep time and SWS"),
never about a receptor (that is ``receptor_effect``'s ``rem_suppression`` & co). A closed
vocabulary, :data:`EFFECTS`:

* ``total_sleep_increase`` / ``sleep_latency_decrease``: better sleep (more total sleep,
  better efficiency or continuity) / falling asleep faster;
* ``sleep_disruption``: insomnia, less total sleep, poorer continuity (caffeine, the
  activating antidepressants);
* ``sedation``: daytime somnolence, sleepiness as a side effect;
* ``sws_increase`` / ``sws_decrease`` and ``rem_suppression`` / ``rem_increase`` /
  ``rem_latency_increase`` / ``rem_unchanged``: sleep architecture on polysomnography;
* ``restless_legs``, ``nightmares``: what a drug provokes during sleep.

Read only off the full-text reviews of corpus #25 ``papers`` (``lib.corpora.papers``),
a sentence offered to a drug only when it names that drug by its INN (a class sentence,
"SSRIs suppress REM sleep", is never offered). A statement about animals carries its
``species`` so the animal_evidence flag shows (``DrugEffectKind.drug_nodes``). Each
effect lists patterns its quote must ALL match (``requires``, the applier's gate).
Fetcher ``tools/fetch/fetch_sleep.py``, applier ``tools/sourcing/apply_sleep.py``, data in
the committed ``tools/generated_cache/sleep.json``.

Built with the help of Claude Code.
"""
from __future__ import annotations

import re
from typing import Any

from . import caches
from .drug_effects import DrugEffectKind
from .receptor_effects import RECEPTOR_EFFECTS

CACHE = caches.CACHE_DIR / "sleep.json"

# A sentence about sleep at all (what the fetcher offers).
SLEEP = (r"sleep|\bREMS?\b|NREM|insomni|somnolen|sedat|hypnot|wakeful|drows|nightmare|"
         r"dream|restless legs|periodic limb|slow[- ]wave|\bSWS\b")
REM = r"\bREMS?\b|paradoxical sleep"  # Monti writes "REMS"
SWS = r"slow[- ]wave|\bSWS\b|deep sleep|delta (?:sleep|power|activity)|\bN3\b|stages? (?:3|4|III|IV)"
TOTAL = (r"total sleep|sleep (?:time|efficiency|continuity|maintenance|quality|duration)|"
         r"improv\w*[^.]{0,60}sleep|sleep[^.]{0,60}improv")


def _shared(effect: str) -> dict[str, str]:
    """The ``{en, fr}`` label a receptor effect already words (one wording per effect)."""
    return {"en": RECEPTOR_EFFECTS[effect]["en"], "fr": RECEPTOR_EFFECTS[effect]["fr"]}


# Effect -> {en, fr, requires}. Order is display order.
EFFECTS: dict[str, dict[str, Any]] = {
    "total_sleep_increase": {"en": "Improves sleep (more total sleep, better efficiency)",
                             "fr": "Améliore le sommeil (plus de sommeil total, meilleure efficacité)",
                             "requires": (TOTAL,)},
    "sleep_latency_decrease": {"en": "Falls asleep faster", "fr": "Endormissement plus rapide",
                               "requires": (r"sleep (?:onset )?latenc|sleep onset|sleep induction|fall\w* asleep",)},
    "sleep_disruption": {"en": "Disrupts sleep (insomnia, less or more broken sleep)",
                         "fr": "Perturbe le sommeil (insomnie, sommeil plus court ou haché)",
                         "requires": (r"insomni|disrupt|impair\w*[^.]{0,40}sleep|awaken|"
                                      r"wakefulness|sleep (?:latency|efficiency|continuity)|"
                                      r"total sleep|fragment",)},
    "sedation": {"en": "Daytime sleepiness / sedation", "fr": "Somnolence / sédation",
                 "requires": (r"sedat|somnolen|drows|sleepiness",)},
    "sws_increase": {**_shared("sws_increase"), "requires": (SWS,)},
    "sws_decrease": {**_shared("sws_decrease"), "requires": (SWS,)},
    "rem_suppression": {**_shared("rem_suppression"), "requires": (REM,)},
    "rem_latency_increase": {"en": "Delays the first REM sleep (longer REM latency)",
                             "fr": "Retarde le premier sommeil paradoxal (latence du REM allongée)",
                             "requires": (r"REMS? (?:sleep )?(?:onset )?latenc",)},
    "rem_increase": {**_shared("rem_increase"), "requires": (REM,)},
    "rem_unchanged": {"en": "Leaves REM sleep unchanged",
                      "fr": "Ne modifie pas le sommeil paradoxal (REM)",
                      "requires": (REM,)},
    "restless_legs": {"en": "Restless legs / periodic limb movements",
                      "fr": "Jambes sans repos / mouvements périodiques des membres",
                      "requires": (r"restless legs|periodic limb|\bRLS\b|\bPLMS?\b",)},
    "nightmares": {"en": "Nightmares / vivid dreams", "fr": "Cauchemars / rêves intenses",
                   "requires": (r"nightmare|dream",)},
}

KIND = DrugEffectKind("drug_sleep", "sleep", "sleep effect", CACHE, EFFECTS,
                      exclusive=(("rem_suppression", "rem_increase"),
                                 ("rem_suppression", "rem_unchanged"),
                                 ("rem_increase", "rem_unchanged"),
                                 ("sws_increase", "sws_decrease")),
                      section="sleep")


def about_sleep(text: str) -> bool:
    """Whether ``text`` speaks of sleep at all (what the fetcher offers)."""
    return bool(re.search(SLEEP, text or "", re.IGNORECASE))
