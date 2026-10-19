"""data_generators.effect_index: the effect -> receptors -> drugs index (BETA), for agents.

The single implementation of this join: ``llms_txt.py`` and ``tools/render_api.py`` read
it in Python, and the viewer reads its ``to_json`` form, ``/derived/effects.json``,
written by ``render_api.py --effects-out`` at build / serve time (the Docker ``api``
stage, ``tools/serve.py``), never committed. ``public/js/receptor-effects.js``
``readEffectIndex`` only resolves the ids in that file, it computes nothing. Rules: a
drug's binding inherits a receptor_effect node only when its ``action`` is one of the
actions that node's mode lists (``meta.receptor_effect_modes``); an affinity_only binding
(no action) inherits nothing; every drug adds its active metabolites' bindings, each
tagged with the metabolite (as ``js/data/drugs.js`` ``allBindings`` does). Derived, never stored: a statement about the receptors a drug acts
on, not about the drug.

Stdlib only, no package-relative import, so ``render_api`` can load it off ``sys.path``.

Built with the help of Claude Code.
"""

from __future__ import annotations

import re
from typing import Any


def _en(value: Any) -> str:
    """A label as English, whether still bilingual (``{en, fr}``) or already emitted."""
    return value.get("en", "") if isinstance(value, dict) else str(value)


def owner_effects(receptors: list[dict[str, Any]],
                  drug_targets: dict[str, dict[str, Any]]) -> dict[str, tuple[str, str, list]]:
    """Target id -> (owner kind, English name, its stored ``effects`` nodes), as the viewer's merged
    target list keys them: a receptor by its id, a non-receptor target by its
    ``drug_targets`` key (a receptor-linked ``drug_targets`` entry IS the receptor)."""
    out = {r["id"]: ("receptor", _en(r.get("name") or r["id"]), r.get("effects") or [])
           for r in receptors}
    for tid, t in drug_targets.items():
        if not t.get("receptor"):
            out[tid] = ("target", _en(t.get("name") or tid), t.get("effects") or [])
    return out


def _norm(name: str) -> str:
    """A drug name folded like the viewer's ``normName`` (js/util.js)."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def drug_bindings(drug: dict[str, Any], drugs_by_id: dict[str, dict[str, Any]],
                  metabolites_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The drug's bindings as the viewer's derived readouts join them (``allBindings``,
    ``js/data/drugs.js``), borrowing tagged ``via_metabolite`` (the molecule lent from):
    each active metabolite's own bindings, else its linked modeled drug's (a prodrug's
    only bindings, any other drug's on top of its own); a salt declaring
    ``constituents`` each modeled constituent's."""
    out = list(drug.get("bindings") or [])
    for name in drug.get("constituents") or []:
        part = drugs_by_id.get(name.lower()) or next(
            (d for d in drugs_by_id.values() if _norm(d.get("name")) == _norm(name)), None)
        if part and part is not drug:
            out += [{**b, "via_metabolite": name} for b in part.get("bindings") or []]
    for ref in drug.get("metabolites") or []:
        m = metabolites_by_id.get(ref.get("id"), {})
        linked = drugs_by_id.get(m.get("drug_id") or "")
        own = m.get("bindings") or ((linked or {}).get("bindings") or [])
        out += [{**b, "via_metabolite": m.get("name")} for b in own]
    return out


def possible_effects(bindings: list[dict[str, Any]], effects_of: dict[str, tuple[str, str, list]],
                     modes: dict[str, dict[str, Any]]) -> dict[str, list[tuple[dict, dict]]]:
    """Effect id -> its ``(binding, node)`` pairs, first-seen order of the bindings."""
    out: dict[str, list[tuple[dict, dict]]] = {}
    for b in bindings:
        if not b.get("action"):
            continue
        for node in effects_of.get(b.get("target"), ("", "", []))[2]:
            if b["action"] not in (modes.get(node["mode"]) or {}).get("actions", []):
                continue
            via = out.setdefault(node["effect"], [])
            # One route per (target, compound): the parent and its active metabolite
            # on one receptor are two contributions, each labelled by its compound.
            if not any(vb.get("target") == b.get("target") and vn is node
                       and vb.get("via_metabolite") == b.get("via_metabolite")
                       for vb, vn in via):
                via.append((b, node))
    return out


def build(receptors: list[dict[str, Any]], drugs: list[dict[str, Any]],
          metabolites: list[dict[str, Any]], meta: dict[str, Any]) -> list[dict[str, Any]]:
    """One entry per effect some target carries, sorted by English label::

        {"id": "nausea", "label": "Nausea / vomiting",
         "owners": [{"kind": "receptor", "id": "5ht3", "name": "5-HT3", "node": {...}}, ...],
         "drugs": [{"drug": {...}, "via": [(binding, node), ...]}, ...]}
    """
    labels = meta.get("receptor_effect_labels") or {}
    modes = meta.get("receptor_effect_modes") or {}
    effects_of = owner_effects(receptors, meta.get("drug_targets") or {})
    drugs_by_id = {d["id"]: d for d in drugs}
    metabolites_by_id = {m["id"]: m for m in metabolites}
    index: dict[str, dict[str, Any]] = {}

    def entry(effect: str) -> dict[str, Any]:
        return index.setdefault(effect, {"id": effect, "label": _en(labels.get(effect, effect)),
                                         "owners": [], "drugs": []})

    for tid, (kind, name, nodes) in effects_of.items():
        for node in nodes:
            entry(node["effect"])["owners"].append({"kind": kind, "id": tid, "name": name,
                                                    "node": node})
    for d in drugs:
        joined = possible_effects(drug_bindings(d, drugs_by_id, metabolites_by_id), effects_of, modes)
        for effect, via in joined.items():
            entry(effect)["drugs"].append({"drug": d, "via": via})
    return sorted(index.values(), key=lambda e: e["label"].lower())


def to_json(index: list[dict[str, Any]]) -> dict[str, Any]:
    """The viewer's file: ids only, the viewer resolves them against the data it loaded::

        {"effects": [{"id": "nausea",
                      "owners": [{"target": "5ht3", "mode": "agonism"}, ...],
                      "drugs": [{"drug": "ondansetron",
                                 "via": [{"target": "5ht3", "action": "antagonist",
                                          "mode": "antagonism"}]}, ...]}]}

    A via entry borrowed from an active metabolite or constituent also names its ``via_metabolite`` (the
    metabolite's name, as the viewer tags the binding). Order is the index's (effects by
    English label, drugs in data order)."""
    def via(b: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
        out = {"target": b["target"], "action": b["action"], "mode": node["mode"]}
        if b.get("via_metabolite"):
            out["via_metabolite"] = b["via_metabolite"]
        return out
    return {"effects": [
        {"id": e["id"],
         "owners": [{"target": o["id"], "mode": o["node"]["mode"]} for o in e["owners"]],
         "drugs": [{"drug": d["drug"]["id"], "via": [via(b, n) for b, n in d["via"]]}
                   for d in e["drugs"]]}
        for e in index]}


def owners_by_mode(effect: dict[str, Any], modes: dict[str, dict[str, Any]]
                   ) -> list[tuple[str, list[dict[str, Any]]]]:
    """``[(English mode label, owners)]`` for one index entry, in ``modes`` order, a mode
    no owner holds left out; owners sorted by id. The one grouping ``llms.txt`` and the
    ``/api/effect/<id>`` page both read."""
    out = []
    for mode, spec in modes.items():
        owners = sorted((o for o in effect["owners"] if o["node"]["mode"] == mode),
                        key=lambda o: o["id"])
        if owners:
            out.append((_en(spec.get("label", mode)), owners))
    return out


def summary_lines(index: list[dict[str, Any]], modes: dict[str, dict[str, Any]],
                  site_url: str) -> list[str]:
    """One Markdown line per effect for ``llms.txt``: its owners by mode, its drug count.
    e.g. ``- [Nausea / vomiting](<site>/api/effect/nausea) `nausea`: agonism of 5-HT3, D2;
    28 drugs could cause it``."""
    out = []
    for e in index:
        parts = [f"{label.lower()} of {', '.join(sorted(o['name'] for o in owners))}"
                 for label, owners in owners_by_mode(e, modes)]
        out.append(f"- [{e['label']}]({site_url}/api/effect/{e['id']}) `{e['id']}`: "
                   f"{'; '.join(parts)}; {len(e['drugs'])} "
                   f"{'drug' if len(e['drugs']) == 1 else 'drugs'} could cause it")
    return out
