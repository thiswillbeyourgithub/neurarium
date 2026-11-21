"""The shared shape of a drug-level effect kind: one node per (drug, effect) from a closed
vocabulary, read off quotes, e.g. ``drug_seizure_threshold`` ("lowers the seizure
threshold") and ``drug_sleep`` ("lengthens REM latency").

A kind is a :class:`DrugEffectKind`: its emitted field, its cache, and its vocabulary
``{effect: {en, fr, requires}}`` where ``requires`` lists patterns a quote must ALL match
(the applier's gate, so a pick cannot attach a sentence to an effect it never states).
``exclusive`` lists effect pairs a drug may not carry together (the stronger and the
hedged form of one claim). The generator, the applier and the meta labels all read it,
so a new kind is a vocabulary plus a fetcher, never a copy of this logic.

Built with the help of Claude Code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import caches


@dataclass
class DrugEffectKind:
    kind: str                       # node kind, e.g. "drug_sleep"
    field: str                      # emitted drug field, e.g. "sleep"
    label: str                      # human name in error messages
    cache: Path
    effects: dict[str, dict[str, Any]]
    exclusive: tuple[tuple[str, str], ...] = ()
    _data: dict | None = field(default=None, repr=False)

    def says(self, effect: str, *texts: str | None) -> bool:
        """Whether one of ``texts`` matches every pattern ``effect`` requires."""
        pats = (self.effects.get(effect) or {}).get("requires") or ()
        return bool(pats) and any(
            t and all(re.search(p, t, re.IGNORECASE) for p in pats) for t in texts)

    def meta_labels(self) -> dict[str, dict[str, str]]:
        """effect -> ``{en, fr}`` (patterns stay author-side)."""
        return {k: {"en": v["en"], "fr": v["fr"]} for k, v in self.effects.items()}

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
            out.append({"effect": effect, "sources": quote_sources(r["sources"], what)})
        for a, b in self.exclusive:
            if {a, b} <= seen:
                raise ValueError(f"Drug {drug_id!r}: both {a} and {b} (keep the stronger)")
        order = {k: i for i, k in enumerate(self.effects)}
        out.sort(key=lambda r: order[r["effect"]])
        return {self.field: out} if out else {}
