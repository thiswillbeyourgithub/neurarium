"""data_generators.unknown: the **UNKNOWN** grade, "we searched and nothing states it".

A red ✕ (NOSOURCE) says *nobody has found a source yet*; it is a to-do. UNKNOWN says
something stronger and narrower: every reachable source this dataset draws on was
searched for this one claim, on a recorded date, and none of them states it. That is
a finding about the literature, not a gap in our work, so it gets its own pill (∅)
and leaves the headline "% sourced" denominator (it is neither backed nor missing).

A node earns UNKNOWN **only through a recorded search log**, never by hand: one entry
in :data:`UNKNOWN_LOG_PATH` (committed), keyed by the claim's citation site
(``tools/sourcing/citation_site.py`` grammar), listing every source searched, the
lookup key or query run against it, how many hits it gave, the date, and who ran it::

    "drug:clozapine/bindings[5ht1d]": {
        "kind": "drug_binding_action",
        "searched": "2026-10-12",
        "by": {"harness": "Claude Code", "model": "opus"},
        "sources": [
            {"corpus": "pdsp_ki", "lookup": "Clozapine / HTR1D", "hits": 0},
            {"corpus": "europepmc", "query": "\\"clozapine\\" AND (...)", "hits": 3,
             "read": ["12345678"]},
            ...]}

A metabolite binding is keyed ``metabolite:<id>/bindings[<target>]``: the metabolite is
one record whichever drugs make it (``tools/data/metabolites_data.jsonl``), so one entry
covers it under every parent. A receptor's (or a non-receptor target's) clinical effects
are keyed ``receptor:<id>/effects`` / ``target:<id>/effects``, ONE entry per owner (kind
``receptor_effect``): it says no searched source states any effect of acting on it, and
lands as ``effects_unknown`` on an owner that carries no effect node.

Three rules, each enforced:

* **A real source wins.** :func:`apply_unknown` stamps only a claim that is still
  unsourced (for a binding direction: still ``affinity_only``; for effects: no effect
  node at all); a log entry whose claim
  has since gained a source is ignored, so a later find needs no log edit.
* **The search must be complete.** :data:`UNKNOWN_REQUIRED_SOURCES` lists, per node
  kind, the corpora a search has to cover; ``check_data.py`` (family 4) fails a stamp
  missing one. A kind with no entry here cannot be UNKNOWN at all.
* **It expires.** A search older than ``freshness.FRESHNESS_MAX_MONTHS`` fails
  ``check_data.py`` family 13 (the same freshness check, and the same pre-push path),
  because the literature moves: a new paper can answer it.

The emitted stamp is compact (``{"searched", "corpora"}``): the viewer only needs the
tooltip's "Searched X, Y on DATE"; the full queries stay in the committed log.

Built with the help of Claude Code.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from lib.text_fold import ascii_key

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UNKNOWN_LOG_PATH = os.path.join(ROOT, "tools", "generated_cache", "unknown_searches.json")

# Node kind -> the corpora a search must have covered before that kind's node may read
# UNKNOWN. A binding direction is stated (when it is stated at all) in a measured-assay
# table (PDSP, GtoPdb's action column), an encyclopedic article (EN + FR Wikipedia), or a
# primary paper (Europe PMC abstracts).
# A receptor's clinical effects (``receptor_effect``, one UNKNOWN per owner: "no source
# states any effect of acting on it") are stated, when at all, in its encyclopedic article,
# its GtoPdb function rows, the psychopharmacology textbook, or a human study.
UNKNOWN_REQUIRED_SOURCES: dict[str, tuple[str, ...]] = {
    "drug_binding_action": ("pdsp_ki", "gtopdb_ki", "wikipedia_pharm", "wikipedia_fr",
                            "europepmc"),
    "receptor_effect": ("wikipedia_pharm", "gtopdb_function", "stahl_essential",
                        "europepmc"),
}

_BINDING_SITE = re.compile(
    r"^(?P<kind>drug|metabolite):(?P<owner>[^/]+)/bindings\[(?P<target>[^\]:]+)\]$")
_EFFECTS_SITE = re.compile(r"^(?P<kind>receptor|target):(?P<owner>[^/]+)/effects$")


fold = ascii_key  # a metabolite name folded for matching (case + punctuation)


def binding_site(owner_id: str, target: str, kind: str = "drug") -> str:
    """A binding's log key, in ``tools/sourcing/citation_site.py``'s grammar (the test
    suite pins the two together): ``drug:<id>/bindings[<target>]``, or
    ``metabolite:<id>/bindings[<target>]`` for a metabolite's own binding (one record
    per molecule, whichever drugs make it). An affinity-only binding has no action."""
    return f"{kind}:{owner_id}/bindings[{target}]"


def effects_site(owner_kind: str, owner_id: str) -> str:
    """An owner's effects log key (``receptor:<id>/effects``, ``target:<id>/effects``),
    in ``citation_site.py``'s grammar: ONE entry per owner, since what UNKNOWN states is
    that no source names any effect of acting on it (a sourced effect is per node)."""
    return f"{owner_kind}:{owner_id}/effects"


def affinity_only_bindings(drugs: list[dict[str, Any]],
                           metabolites: list[dict[str, Any]] = ()) -> list[dict[str, Any]]:
    """Every binding with no direction, as ``{site, drug, ligand, metabolite, target,
    binding}``: a drug's own, then each referenced metabolite's (``drug`` = its first
    parent, whose article a search may also read; ``metabolite`` = its name). ``ligand``
    is the name a search looks up. Works on the authored and the emitted records alike."""
    out = []
    first_parent: dict[str, str] = {}
    for d in drugs:
        for b in d.get("bindings", []):
            if b.get("affinity_only"):
                out.append({"site": binding_site(d["id"], b["target"]), "drug": d["id"],
                            "ligand": d.get("name") or d["id"], "metabolite": None,
                            "target": b["target"], "binding": b})
        for r in d.get("metabolites", []):
            first_parent.setdefault(r["id"], d["id"])
    for m in metabolites:
        if m["id"] not in first_parent:
            continue
        for b in m.get("bindings") or []:
            if b.get("affinity_only"):
                out.append({"site": binding_site(m["id"], b["target"], "metabolite"),
                            "drug": first_parent[m["id"]], "ligand": m["name"],
                            "metabolite": m["name"], "target": b["target"], "binding": b})
    return out


def load_log(path: str = UNKNOWN_LOG_PATH) -> dict[str, Any]:
    """The committed search log, ``{}`` when there is none yet."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def stamp(entry: dict[str, Any]) -> dict[str, Any]:
    """The compact emitted form of one log entry: the date + the corpora searched."""
    corpora = []
    for src in entry.get("sources", []):
        if src.get("corpus") and src["corpus"] not in corpora:
            corpora.append(src["corpus"])
    return {"searched": entry["searched"], "corpora": corpora}


def missing_required(kind: str, corpora: list[str]) -> list[str]:
    """The required corpora of ``kind`` a search did not cover (all of them for a kind
    that cannot be UNKNOWN)."""
    need = UNKNOWN_REQUIRED_SOURCES.get(kind)
    if need is None:
        return ["<kind cannot be UNKNOWN>"]
    return [c for c in need if c not in corpora]


def apply_unknown(drugs: list[dict[str, Any]], metabolites: list[dict[str, Any]] = (),
                  log: dict[str, Any] | None = None, receptors: list[dict[str, Any]] = (),
                  targets: dict[str, dict[str, Any]] | None = None) -> dict[str, int]:
    """Stamp ``unknown`` on every still-unsourced claim the log covers.

    A binding direction (``drug_binding_action``) is stamped on the binding row while it
    is still ``affinity_only``; an owner's effects (``receptor_effect``) as
    ``effects_unknown`` on the receptor record / target entry while it carries no
    ``effects`` node. Mutates the emitted records in place and returns a small tally.
    Raises on a log key that resolves to nothing (a renamed drug, metabolite, receptor
    or target, a dropped binding), so a stale entry can never sit silently in the
    committed log.
    """
    log = load_log() if log is None else log
    owners = {("drug", d["id"]): d for d in drugs}
    owners.update({("metabolite", m["id"]): m for m in metabolites})
    owners.update({("receptor", r["id"]): r for r in receptors})
    owners.update({("target", tid): t for tid, t in (targets or {}).items()
                   if t.get("type") != "receptor"})
    stats = {"stamped": 0, "superseded": 0}
    for key, entry in sorted(log.items()):
        kind = entry.get("kind")
        m = (_BINDING_SITE if kind == "drug_binding_action" else
             _EFFECTS_SITE if kind == "receptor_effect" else None)
        m = m.match(key) if m else None
        if not m:
            raise ValueError(f"unknown_searches.json: {key!r} is not a {kind} site (the "
                             f"UNKNOWN kinds: {', '.join(UNKNOWN_REQUIRED_SOURCES)})")
        owner = owners.get((m["kind"], m["owner"]))
        if owner is None:
            raise KeyError(f"unknown_searches.json: {key!r} names no {m['kind']}")
        if kind == "receptor_effect":
            if owner.get("effects"):
                stats["superseded"] += 1  # a real source won since the search
            else:
                owner["effects_unknown"] = stamp(entry)
                stats["stamped"] += 1
            continue
        rows = [b for b in owner.get("bindings", []) if b["target"] == m["target"]]
        if not rows:
            raise KeyError(f"unknown_searches.json: {key!r} resolves to no binding")
        for b in rows:
            if b.get("affinity_only"):
                b["unknown"] = stamp(entry)
                stats["stamped"] += 1
            else:
                stats["superseded"] += 1  # a real source won since the search
    return stats
