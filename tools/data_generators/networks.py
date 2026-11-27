"""Large-scale brain networks (BETA): sets of functional areas that fluctuate together at rest.

Node kind ``networks`` (one node per network, ``networks.jsonl``). The six canonical
networks of the Uddin, Yeo & Spreng (2019) taxonomy, which names them by their anatomy
("occipital", "pericentral", "dorsal frontoparietal", "lateral frontoparietal",
"midcingulo-insular", "medial frontoparietal") next to the common names used here.
Each network lists the Brodmann areas it spans (ids from
``data_generators/functional_areas.py``) plus any extra modeled structure (base ids);
the viewer lights the union of their structures and overlays the drawn areas.

Sources: Kandel (#2) states the anatomy of the default mode, salience and cognitive
control networks; the Uddin 2019 abstract (Europe PMC #17, PMID 31707621) backs the
taxonomy's anatomical names for all six. The area lists are the conventional mapping
(a network is a resting-state map, coarser than any one area), so they are what the
quotes place, not a cytoarchitectonic claim.

Built with the help of Claude Code.
"""
from __future__ import annotations

from typing import Any

from .provenance import _kandel

WIKI = "https://en.wikipedia.org/wiki/"

# The taxonomy sentence, one quote object cited by all six networks.
_UDDIN = dict(corpus="europepmc", page="31707621", provenance="verified",
              quote='A logical starting point in this endeavor might delineate systems that '
                    'we refer to here as "occipital", "pericentral", "dorsal frontoparietal", '
                    '"lateral frontoparietal", "midcingulo-insular", and "medial '
                    'frontoparietal" networks.')


def _n(nid: str, en: str, fr: str, title: str, areas: list[str], sources: list[dict],
       structures: list[str] | None = None) -> dict[str, Any]:
    return {"id": nid, "name": {"en": en, "fr": fr}, "areas": areas,
            "structures": structures or [], "wikipedia": WIKI + title,
            "sources": sources}


NETWORKS: list[dict[str, Any]] = [
    _n("default_mode", "Default mode network (medial frontoparietal)",
       "Réseau du mode par défaut (frontopariétal médian)", "Default_mode_network",
       ["ba10", "ba23", "ba31", "ba39"],
       [_kandel(166, "The most widely studied of these networks is referred to as the "
                     "default mode network, which includes the posterior medial cortex, "
                     "lateral parietal cortex, and medial prefrontal cortex."), _UDDIN]),
    _n("salience", "Salience network (midcingulo-insular)",
       "Réseau de saillance (cingulo-insulaire moyen)", "Salience_network",
       ["ba24", "ba32", "ba16"],
       [_kandel(1557, "The emotional salience network links dorsal anterior cingulate "
                      "cortex (dACC) and frontoinsular cortex (FI) with subcortical "
                      "structures involved in emotion."), _UDDIN]),
    _n("central_executive", "Central executive network (lateral frontoparietal)",
       "Réseau exécutif central (frontopariétal latéral)", "Central_executive_network",
       ["ba9", "ba46", "ba40"],
       [_kandel(1557, "The cognitive control network links the dorsolateral prefrontal "
                      "(DLPFC) and parietal cortices and several subcortical structures."),
        _UDDIN]),
    _n("dorsal_attention", "Dorsal attention network (dorsal frontoparietal)",
       "Réseau attentionnel dorsal (frontopariétal dorsal)", "Dorsal_attention_network",
       ["ba8", "ba7"], [_UDDIN]),
    _n("sensorimotor", "Sensorimotor network (pericentral)",
       "Réseau sensorimoteur (péricentral)", "Sensorimotor_network",
       ["ba4", "ba3_1_2", "ba6"], [_UDDIN]),
    _n("visual", "Visual network (occipital)", "Réseau visuel (occipital)",
       "Large-scale_brain_network", ["ba17", "ba18", "ba19"], [_UDDIN]),
]
