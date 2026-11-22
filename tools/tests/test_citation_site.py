#!/usr/bin/env python
"""Unit tests for tools/sourcing/citation_site.py and the two ends that must agree.

A citation site is only worth anything if the pass that *shows* it to a judge
(`recheck_quotes.py`, reading the emitted data) and the pass that *acts* on it
(`demote_quotes.py`, walking the authoring files) spell it the same way. Nothing
crashes when they disagree: the demotion simply matches nothing and reports a success
that changed no data, which is the quietest possible way to leave a wrong green check
standing. So the load-bearing test here is the cross-check at the bottom, run over the
real dataset.

Built with the help of Claude Code.
"""
import collections
import json
import os
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS / "sourcing"))
sys.path.insert(0, str(TOOLS))
import citation_site as CS  # noqa: E402
import demote_quotes as D  # noqa: E402
import recheck_quotes as R  # noqa: E402
from data_generators.quote_table import quote_id  # noqa: E402

# Corpora whose quotes are deliberately never reconstructed into a claim, so their
# authoring-side sites have no emitted counterpart by design (see `EXCLUDE_CORPUS`).
UNJUDGED_CORPORA = {"allen_ahba"}

# Facets whose sources live in hand-authored Python rather than in a machine-writable
# file, so the applier reaches them by *reporting* them for a hand edit, never by
# rewriting them. A judge may still name one: the demotion then says out loud that the
# site matched nothing, which is the outcome we want, not a silent no-op.
# An enzyme row's `/strength` sub-claim is the same: its sources are derived by code from
# the row's own (quotes/attestation.py), so demoting the row's quote is what removes it.
# An uncertainty bullet's own citation (a `contradicted` source, hand-curated in
# quotes/contradictions.py) is the same: it can also be another node's machine-written
# source (dimenhydrinate's T½ quote doubts diphenhydramine's), yet at the bullet site
# only a hand edit of the CONTRADICTIONS table removes it.
HAND_AUTHORED = ("/formed_by[", "]/strength", "/uncertainty[")


class GrammarTest(unittest.TestCase):

    def test_a_site_reads_as_one_address(self):
        self.assertEqual(CS.site("drug", "clozapine", "bindings[5ht2a:antagonist]"),
                         "drug:clozapine/bindings[5ht2a:antagonist]")
        self.assertEqual(CS.site("receptor", "5ht1a", "locations", "amygdala"),
                         "receptor:5ht1a/locations[amygdala]")
        self.assertEqual(CS.site("circuit", "reward"), "circuit:reward")

    def test_an_enzyme_row_is_keyed_by_isoform_and_role(self):
        # A drug that is both cleared by an isoform and inhibits it has two nodes with
        # two sources there, so the isoform alone would address both at once.
        sub = {"enzyme": "cyp2d6", "role": "substrate"}
        inh = {"enzyme": "cyp2d6", "role": "inhibitor"}
        self.assertNotEqual(CS.member_label(sub, 0), CS.member_label(inh, 0))

    def test_a_binding_row_is_keyed_by_target_and_action(self):
        # Amisulpride antagonises D2 and partially agonises it: two nodes, two sources,
        # so the target alone would address both at once. A binding with no known
        # direction has nothing to add and keys on the target alone.
        anta = {"target": "d2", "action": "antagonist"}
        part = {"target": "d2", "action": "partial_agonist"}
        self.assertNotEqual(CS.member_label(anta, 0), CS.member_label(part, 0))
        self.assertEqual(CS.member_label({"target": "d2"}, 0), "d2")

    def test_a_list_member_is_named_by_what_it_is(self):
        # Never by position: appliers rewrite these lists wholesale, so an index would
        # silently come to address a different claim.
        self.assertEqual(CS.member_label({"enzyme": "cyp3a4"}, 3), "cyp3a4")
        self.assertEqual(CS.member_label({"name": "norfluoxetine"}, 3), "norfluoxetine")
        self.assertEqual(CS.member_label({"nothing": "usable"}, 3), "3")

    def test_a_formulation_claim_is_addressed_under_its_release(self):
        # A formulation is a two-level owner like a metabolite, keyed by its release.
        self.assertEqual(CS.member_label({"release": "xr"}, 2), "xr")
        r = lambda *p: CS.resolve("drugs_data.jsonl", ["quetiapine", "formulations", *p])
        self.assertEqual(r("xr", "release_sources"),
                         "drug:quetiapine/formulations[xr]/release")
        self.assertEqual(r("xr", "tmax_sources"), "drug:quetiapine/formulations[xr]/tmax")
        self.assertEqual(r("xr", "brands", "Seroquel XR", "sources"),
                         "drug:quetiapine/formulations[xr]/brands[Seroquel XR]")

    def test_an_unknown_file_addresses_nothing(self):
        # None means "not addressable", and the caller must read it as no match rather
        # than as a wildcard.
        self.assertIsNone(CS.resolve("some_other.json", ["a", "b"]))
        self.assertIsNone(CS.resolve("drugs_data.jsonl", ["clozapine"]))


def _emitted_sites():
    """``qid -> {site}``, as the judging pass names them out of ``public/data``."""
    quotes = {q["id"]: q for q in R._jsonl("quotes.jsonl")}
    claims, _ = R.reconstruct_claims(quotes)
    out = collections.defaultdict(set)
    for qid, texts in claims.items():
        for text in texts:
            if " | " in text:
                out[qid].add(text.split(" | ", 1)[0])
    return quotes, out


def _authoring_sites():
    """``qid -> {site}``, as the applier names them walking the authoring files."""
    found = collections.defaultdict(set)

    class Probe(D.Editor):
        def _apply_one(self, src, root=None, path=()):
            site = CS.resolve(root, list(path))
            if site:
                found[quote_id(src)].add(site)
            return False

    ed = Probe({}, D.emitted_page_dirs())
    with open(D.DRUGS, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                ed.walk(row, "drugs_data.jsonl", (row.get("id"),))
    for name in D.CACHE_FILES:
        path = os.path.join(D.CACHE, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                ed.walk(json.load(fh), name, ())
    return found


class BothEndsAgreeTest(unittest.TestCase):
    """The real dataset, both ends, same vocabulary."""

    @classmethod
    def setUpClass(cls):
        cls.quotes, cls.emitted = _emitted_sites()
        cls.authoring = _authoring_sites()

    def test_the_applier_can_reach_every_site_a_judge_is_shown(self):
        unreachable = []
        for qid, sites in self.emitted.items():
            # Only the machine-writable files are walked by the applier; the rest is
            # hand-authored Python it deliberately reports rather than rewrites, and a
            # site there is for a human to grep, not for the applier to match.
            if qid not in self.authoring:
                continue
            for site in sites - self.authoring[qid]:
                if any(mark in site for mark in HAND_AUTHORED):
                    continue
                if site.split(":", 1)[0] in ("drug", "receptor", "target", "enzyme"):
                    unreachable.append((qid, site, sorted(self.authoring[qid])[:2]))
        self.assertEqual(unreachable, [], "a judge would name a site the applier "
                                          "cannot act on, so the demotion would "
                                          "silently do nothing")

    def test_every_addressable_citation_is_shown_to_the_judge(self):
        unnamed = []
        for qid, sites in self.authoring.items():
            quote = self.quotes.get(qid)
            if not quote or quote["corpus"] in UNJUDGED_CORPORA:
                continue  # not emitted any more, or never judged by design
            missing = sites - self.emitted.get(qid, set())
            # A cache row the merge dropped (Stahl wins an enzyme pair the article also
            # states) is stored but not shipped, so it has no claim to be shown with.
            if missing and self.emitted.get(qid):
                unnamed.append((qid, sorted(missing), sorted(self.emitted[qid])[:2]))
        for qid, missing, shown in unnamed:
            self.assertTrue(all(m.startswith("drug:") and "/enzymes[" in m
                                for m in missing),
                            f"{qid}: cited at {missing} but the judge is only shown "
                            f"{shown}, so a verdict cannot reach that claim")


class NodeIndexTest(unittest.TestCase):
    """``CS.node_index`` (site -> node dict, what a ``contradicted`` entry is resolved
    through) must spell every site the claim walk spells, or an entry copied off a judge
    batch would resolve to nothing."""

    @classmethod
    def setUpClass(cls):
        cls.quotes, cls.emitted = _emitted_sites()
        data = {n: R._jsonl(f"{n}.jsonl") for n in
                ("drugs", "metabolites", "receptors", "projections", "circuits",
                 "projection_groups", "structures")}
        with open(os.path.join(R.DATA, "meta.json"), encoding="utf-8") as fh:
            targets = json.load(fh)["drug_targets"]
        cls.nodes, cls.ambiguous = CS.node_index(
            drugs=data["drugs"], metabolites=data["metabolites"],
            receptors=data["receptors"], targets=targets,
            projections=data["projections"], circuits=data["circuits"],
            groups=data["projection_groups"], structures=data["structures"])

    def test_it_reaches_every_node_kind_it_claims(self):
        heads = {s.split("/", 1)[0].split(":", 1)[0] + "/" + s.split("/", 1)[1].split("[", 1)[0]
                 for s in self.nodes if "/" in s}
        for want in ("drug/bindings", "drug/enzymes", "drug/metabolites", "drug/workup", "drug/excretion", "drug/sleep", "drug/seizure_threshold",
                     "drug/withdrawals", "drug/holders", "drug/brands",
                     "metabolite/bindings", "receptor/classification", "receptor/effects",
                     "receptor/release_modulation", "receptor/demographics"):
            self.assertIn(want, heads)
        self.assertIn("drug:amisulpride/bindings[d2:partial_agonist]", self.nodes)
        self.assertIsNot(self.nodes["drug:amisulpride/bindings[d2:partial_agonist]"],
                         self.nodes["drug:amisulpride/bindings[d2:antagonist]"])

    def test_a_drug_duration_value_is_a_node(self):
        # A T½ / Tmax value dict must be addressable, so a contradicted entry can doubt
        # it (methylphenidate's three conflicting Stahl half-lives).
        self.assertIn("drug:methylphenidate_d/half_life", self.nodes)
        self.assertIn("hours", self.nodes["drug:methylphenidate_d/half_life"])
        self.assertTrue(any(s.endswith("/tmax") for s in self.nodes))

    def test_every_sourced_node_site_is_one_the_claim_walk_names(self):
        walked = set().union(*self.emitted.values())
        stray = [s for s, node in self.nodes.items()
                 if any(isinstance(x, dict) and x.get("quote_id")
                        and self.quotes.get(x["quote_id"], {}).get("corpus")
                        not in UNJUDGED_CORPORA
                        for x in node.get("sources") or [])
                 and s not in walked]
        self.assertEqual(stray, [], "node_index spells these sites differently from "
                                    "the claim walk")

    def test_no_emitted_site_is_ambiguous(self):
        self.assertEqual(sorted(self.ambiguous), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
