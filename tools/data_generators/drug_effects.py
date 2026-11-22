"""The shared shape of a drug-level effect kind: one node per (drug, effect) from a closed
vocabulary, read off quotes, e.g. ``drug_seizure_threshold`` ("lowers the seizure
threshold") and ``drug_sleep`` ("lengthens REM latency").

A kind is a :class:`DrugEffectKind`: its emitted field, its cache, and its vocabulary
``{effect: {en, fr, requires}}`` where ``requires`` lists patterns a quote must ALL match
(the applier's gate, so a pick cannot attach a sentence to an effect it never states).
``exclusive`` lists effect pairs a drug may not carry together (the stronger and the
hedged form of one claim). ``section`` names its drug panel section: the tour anchor, the
section icon and the ``drug.<section>*`` i18n keys (heading, ``Sub``, ``Hint``,
``Caveat``, ``Short``). Every consumer (generator, meta, tally, check walk, citation
sites, claim walk, viewer panel, node browser, /api pages) loops over the registry
``data_generators.drug_effect_kinds.KINDS``, so a new kind is a vocabulary plus a
fetcher and a registry line, never a copy of this logic.

Built with the help of Claude Code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import caches
from .quotes.uncertainty import _uncertainty_bullet
from lib.species import is_primate, species_key


@dataclass
class DrugEffectKind:
    kind: str                       # node kind, e.g. "drug_sleep"
    field: str                      # emitted drug field, e.g. "sleep"
    label: str                      # human name in error messages
    cache: Path
    effects: dict[str, dict[str, Any]]
    exclusive: tuple[tuple[str, str], ...] = ()
    section: str = ""               # panel section id, e.g. "sleep" (keys drug.sleep*)
    _data: dict | None = field(default=None, repr=False)

    def says(self, effect: str, *texts: str | None) -> bool:
        """Whether one of ``texts`` matches every pattern ``effect`` requires."""
        pats = (self.effects.get(effect) or {}).get("requires") or ()
        return bool(pats) and any(
            t and all(re.search(p, t, re.IGNORECASE) for p in pats) for t in texts)

    def meta_labels(self) -> dict[str, dict[str, str]]:
        """effect -> ``{en, fr}`` (patterns stay author-side)."""
        return {k: {"en": v["en"], "fr": v["fr"]} for k, v in self.effects.items()}

    @property
    def cache_files(self) -> tuple[str, ...]:
        """The applier's cache plus the fetcher's worklist and the picker's judged file."""
        stem = self.cache.stem
        return (self.cache.name, f"{stem}_judged.json", f"{stem}_worklist.json")

    def meta_entry(self) -> dict[str, Any]:
        """What the viewer needs to render the kind (meta ``drug_effect_kinds``)."""
        return {"kind": self.kind, "field": self.field, "section": self.section,
                "effects": self.meta_labels()}

    def data(self) -> dict:
        if self._data is None:
            self._data = caches.load(self.cache.name, required=False)
        return self._data

    def drug_nodes(self, drug_id: str, quote_sources: Callable,
                   data: dict | None = None) -> dict[str, Any]:
        """The emitted field of one drug: ``[{effect, sources}]`` in vocabulary order, or
        ``{}``. Validates against the vocabulary so a hand edit of the cache fails."""
        rows = ((data if data is not None else self.data()).get("drugs") or {}).get(drug_id) or []
        out, seen = [], set()
        for r in rows:
            effect = r.get("effect")
            what = f"Drug {drug_id!r} {self.label} {effect!r}"
            if effect not in self.effects:
                raise KeyError(f"{what}: not in the {self.kind} vocabulary")
            if effect in seen:
                raise ValueError(f"{what}: duplicate effect node")
            seen.add(effect)
            if not r.get("sources"):
                raise ValueError(f"{what}: no source")
            node = {"effect": effect, "sources": quote_sources(r["sources"], what)}
            # Every source names a non-primate species (a rat study in a review): the
            # animal_evidence flag, as on receptor effects.
            kinds = [species_key(s.get("species")) for s in r["sources"]]
            if kinds and all(k and not is_primate(k) for k in kinds):
                node["uncertainty"] = [_uncertainty_bullet(
                    "animal_evidence", what=what, node=node, source=node["sources"][0],
                    args={"species": sorted(set(kinds))})]
            out.append(node)
        for a, b in self.exclusive:
            if {a, b} <= seen:
                raise ValueError(f"Drug {drug_id!r}: both {a} and {b} (keep the stronger)")
        order = {k: i for i, k in enumerate(self.effects)}
        out.sort(key=lambda r: order[r["effect"]])
        return {self.field: out} if out else {}
