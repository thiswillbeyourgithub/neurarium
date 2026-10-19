"""The ``animal_evidence`` flag: a claim only ever measured in non-primate animals.

A rat Ki or a rat tissue-distribution line is real, quote-gated evidence, so it keeps its
grade. What it does not say is that the same holds in a human brain, which is what this
dataset draws. So a claim whose **every** species-recording source names a non-primate
animal (rat, guinea pig, cat ...) and **none** a human or a monkey wears an
``animal_evidence`` uncertainty bullet ("animal evidence only (rat, cat)") citing one of
that evidence.

Derived, never authored per site (see ``uncertainty.py``): the species comes off the data
itself, folded to one vocabulary by ``tools/species.py``:

- a quote node's own ``species`` (GtoPdb #7 tissue lines, GtoPdb #11 interactions);
- a measured Ki: ``n_human`` > 0 is human evidence, else its row's ``species`` (PDSP #5);
- a Europe PMC (#17) paper's MeSH species, from the committed
  ``tools/generated_cache/europepmc_species.json`` (``fetch_europepmc.py --species``).

A source that records no species (a textbook, Wikipedia, Stahl) is **unknown**, and one
unknown source is enough to leave the claim unflagged: the flag says "nothing here is
human", which an unread species cannot support. Covers drug and metabolite bindings,
projections (the route and its transmitter / sign sub-claims), and every receptor /
target "Found in" region (``location_uncertainty``, keyed like ``location_sources``).

Built with the help of Claude Code.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.species import is_primate, species_key

from ..provenance_stats import own_targets
from .uncertainty import _uncertainty_bullet

_EPMC_LEDGER = (Path(__file__).resolve().parents[2] / "generated_cache"
                / "europepmc_species.json")
KIND = "animal_evidence"


def _epmc_species() -> dict[str, list[str]]:
    return json.loads(_EPMC_LEDGER.read_text("utf-8")) if _EPMC_LEDGER.exists() else {}


def _species(src: dict[str, Any], epmc: dict[str, list[str]]) -> set[str]:
    """Species keys one source records (empty = unknown)."""
    if src.get("species"):
        key = species_key(src["species"])
        return {key} if key else set()
    if src.get("corpus") == "europepmc":
        page = str(src.get("page"))
        if page not in epmc:
            raise KeyError(f"Europe PMC paper {page} has no entry in {_EPMC_LEDGER.name}: "
                           f"run python tools/fetch/fetch_europepmc.py --species")
        return set(epmc[page])
    return set()


def _ki_evidence(ki: dict[str, Any] | None) -> list[tuple[dict[str, Any], set[str]]]:
    """The Ki as one piece of evidence, or none when the node carries no Ki."""
    if not ki or not ki.get("source"):
        return []
    if int(ki.get("n_human", 0)) > 0:
        return [(ki["source"], {"human"})]
    key = species_key(ki["source"].get("species"))
    return [(ki["source"], {key} if key else set())]


def animal_only(evidence: list[tuple[dict[str, Any], set[str]]]):
    """``(species keys, cited source)`` when every piece is animal-only, else None."""
    if not evidence:
        return None
    found: set[str] = set()
    for _src, keys in evidence:
        if not keys or any(is_primate(k) for k in keys):
            return None
        found |= keys
    return sorted(found), evidence[0][0]


def _bullet(node: dict[str, Any] | None, evidence, what: str):
    hit = animal_only(evidence)
    if not hit:
        return None
    species, cited = hit
    return _uncertainty_bullet(KIND, what=what, node=node, source=cited,
                               args={"species": species})


def _append(node: dict[str, Any], bullet: dict[str, Any] | None) -> int:
    """Add the bullet keeping evidence before absences (the order bullets read in)."""
    if not bullet:
        return 0
    node["uncertainty"] = sorted([*(node.get("uncertainty") or []), bullet],
                                 key=lambda b: bool(b.get("absence")))
    return 1


def _sources_evidence(sources, epmc):
    return [(s, _species(s, epmc)) for s in sources or []]


def apply_animal_evidence(*, drugs: list[dict[str, Any]],
                          metabolites: list[dict[str, Any]],
                          projections: list[dict[str, Any]],
                          receptors: list[dict[str, Any]],
                          targets: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Attach the flag everywhere it applies, in place; returns flagged nodes per kind.

    Runs after every other uncertainty pass, since those assign their bullets and this
    one appends.
    """
    epmc = _epmc_species()
    counts = {"drug_bindings": 0, "drug_metabolite_bindings": 0, "projections": 0,
              "projection_transmitter": 0, "projection_sign": 0,
              "receptor_locations": 0, "target_locations": 0}

    def bindings(owner, kind):
        for b in owner.get("bindings") or []:
            ev = _sources_evidence(b.get("sources"), epmc) + _ki_evidence(b.get("ki"))
            counts[kind] += _append(b, _bullet(
                b, ev, f"{owner['id']!r} binding {b['target']!r}"))

    for d in drugs:
        bindings(d, "drug_bindings")
    for m in metabolites:
        bindings(m, "drug_metabolite_bindings")
    for p in projections:
        what = f"projection {p['from']}->{p['to']}"
        counts["projections"] += _append(p, _bullet(
            p, _sources_evidence(p.get("sources"), epmc), what))
        for claim, entry in (p.get("claims") or {}).items():
            kind = f"projection_{claim}"
            counts[kind] = counts.get(kind, 0) + _append(entry, _bullet(
                entry, _sources_evidence(entry.get("sources"), epmc), f"{what} {claim}"))
    owners = [("receptor_locations", r["id"], r) for r in receptors]
    owners += [("target_locations", tid, t) for tid, t in own_targets(targets).items()]
    for kind, oid, owner in owners:
        flags = {}
        for region, sources in (owner.get("location_sources") or {}).items():
            b = _bullet(None, _sources_evidence(sources, epmc),
                        f"{oid!r} location {region!r}")
            if b:
                flags[region] = [b]
        if flags:
            owner["location_uncertainty"] = flags
            counts[kind] += len(flags)
    return counts
