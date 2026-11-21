"""Consistency of every drug's and metabolite's binding list (the emitted data).

The panel showed pimavanserin's 5-HT2A and pitolisant's H3 twice: one Stahl phrase
("antagonism/inverse agonism") had been split into an antagonist row and an inverse
agonist row citing the same quote. These checks pin that class of defect:

- no (target, action) pair twice on one compound;
- no antagonist row beside an inverse_agonist row on the same target (the latter
  already is an antagonism, the effects join treats both alike);
- an agonist-like and an antagonist-like row on one target must be told apart, by
  differing notes (lumateperone: presynaptic partial agonist, postsynaptic antagonist)
  or by an uncertainty / speculative flag on one of them (amisulpride's contradicted D2
  partial agonism);
- a metabolite record links a modeled drug or carries its own bindings, never both, and
  its drug id exists;
- a drug never lists itself as its own active metabolite.

A releaser that also blocks reuptake (amphetamine at DAT / NET) is two mechanisms and
passes.

Run: ``python -m unittest discover -s tools/tests -t tools/tests -p test_binding_consistency.py``
"""

from __future__ import annotations

import collections
import json
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "public" / "data"
AGONIST_LIKE = {"agonist", "partial_agonist", "pam"}
ANTAGONIST_LIKE = {"antagonist", "inverse_agonist", "nam", "blocker"}


def _rows(name: str) -> list[dict]:
    with open(DATA / name, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def binding_problems(owner: str, bindings: list[dict]) -> list[str]:
    """Every consistency breach in one compound's binding list, as readable lines."""
    out = []
    pairs = collections.Counter((b["target"], b.get("action")) for b in bindings)
    out += [f"{owner} {t}: {a} listed {n} times" for (t, a), n in pairs.items() if n > 1]
    by_target = collections.defaultdict(list)
    for b in bindings:
        by_target[b["target"]].append(b)
    for target, rows in by_target.items():
        actions = {b.get("action") for b in rows}
        if {"antagonist", "inverse_agonist"} <= actions:
            out.append(f"{owner} {target}: antagonist beside inverse_agonist")
        ag = [b for b in rows if b.get("action") in AGONIST_LIKE]
        ant = [b for b in rows if b.get("action") in ANTAGONIST_LIKE]
        if ag and ant:
            flagged = any(b.get("tentative") or b.get("uncertainty") for b in ag + ant)
            notes = {json.dumps(b.get("note"), sort_keys=True) for b in ag + ant}
            if not flagged and len(notes) < len(ag) + len(ant):
                out.append(f"{owner} {target}: agonist and antagonist rows not told apart")
    return out


class BindingConsistencyTest(unittest.TestCase):
    def test_drug_bindings(self):
        bad = [p for d in _rows("drugs.jsonl") for p in binding_problems(d["id"], d.get("bindings", []))]
        self.assertEqual(bad, [])

    def test_metabolite_bindings(self):
        bad = [p for m in _rows("metabolites.jsonl") for p in binding_problems(m["id"], m.get("bindings", []))]
        self.assertEqual(bad, [])

    def test_metabolite_links(self):
        drugs = {d["id"]: d for d in _rows("drugs.jsonl")}
        metabolites = {m["id"]: m for m in _rows("metabolites.jsonl")}
        bad = []
        for m in metabolites.values():
            if m.get("drug_id") and m["drug_id"] not in drugs:
                bad.append(f"{m['id']}: drug_id {m['drug_id']} is not a drug")
            if m.get("drug_id") and m.get("bindings"):
                bad.append(f"{m['id']}: both a linked drug and its own bindings")
        for d in drugs.values():
            for ref in d.get("metabolites", []):
                if ref["id"] not in metabolites:
                    bad.append(f"{d['id']}: unknown metabolite {ref['id']}")
                elif metabolites[ref["id"]].get("drug_id") == d["id"]:
                    bad.append(f"{d['id']}: lists itself as its own metabolite")
        self.assertEqual(bad, [])

    def test_the_checks_catch_the_known_shapes(self):
        """Each rule fires on the defect it was written for."""
        quote = [{"quote_id": "q"}]
        self.assertTrue(binding_problems("x", [
            {"target": "h3", "action": "antagonist", "sources": quote},
            {"target": "h3", "action": "inverse_agonist", "sources": quote}]))
        self.assertTrue(binding_problems("x", [{"target": "d2", "action": "antagonist"}] * 2))
        self.assertTrue(binding_problems("x", [
            {"target": "d2", "action": "antagonist"}, {"target": "d2", "action": "agonist"}]))
        self.assertFalse(binding_problems("x", [
            {"target": "d2", "action": "antagonist", "note": {"en": "postsynaptic"}},
            {"target": "d2", "action": "partial_agonist", "note": {"en": "presynaptic"}}]))
        self.assertFalse(binding_problems("x", [
            {"target": "dat", "action": "releaser"}, {"target": "dat", "action": "reuptake_inhibitor"}]))


if __name__ == "__main__":
    unittest.main()
