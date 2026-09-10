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
HAND_AUTHORED = ("/formed_by[",)


class GrammarTest(unittest.TestCase):

    def test_a_site_reads_as_one_address(self):
        self.assertEqual(CS.site("drug", "clozapine", "bindings[5ht2a]"),
                         "drug:clozapine/bindings[5ht2a]")
        self.assertEqual(CS.site("receptor", "5ht1a", "locations", "amygdala"),
                         "receptor:5ht1a/locations[amygdala]")
        self.assertEqual(CS.site("circuit", "reward"), "circuit:reward")

    def test_an_enzyme_row_is_keyed_by_isoform_and_role(self):
        # A drug that is both cleared by an isoform and inhibits it has two nodes with
        # two sources there, so the isoform alone would address both at once.
        sub = {"enzyme": "cyp2d6", "role": "substrate"}
        inh = {"enzyme": "cyp2d6", "role": "inhibitor"}
        self.assertNotEqual(CS.member_label(sub, 0), CS.member_label(inh, 0))

    def test_a_list_member_is_named_by_what_it_is(self):
        # Never by position: appliers rewrite these lists wholesale, so an index would
        # silently come to address a different claim.
        self.assertEqual(CS.member_label({"target": "5ht2a"}, 3), "5ht2a")
        self.assertEqual(CS.member_label({"enzyme": "cyp3a4"}, 3), "cyp3a4")
        self.assertEqual(CS.member_label({"name": "norfluoxetine"}, 3), "norfluoxetine")
        self.assertEqual(CS.member_label({"nothing": "usable"}, 3), "3")

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

    ed = Probe({}, D._page_dirs())
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
