#!/usr/bin/env python
"""Unit tests for tools/sourcing/recheck_quotes.py's corpus -> page-dir map.

Stdlib ``unittest`` only (no deps). Runnable directly::

    python tools/tests/test_recheck_quotes.py

pytest-discoverable. The regression guarded here: the map used to be hardcoded in
the script and covered only the six corpora that existed when it was written, so
``build`` died with a ``KeyError`` on the first quote from corpus #9-#12. It now
reads ``meta.source_corpora``, which the generator already emits, and this test
holds the two halves together as new corpora are added.

Built with the help of Claude Code.
"""

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "sourcing"))
import recheck_quotes as R  # noqa: E402

CORPORA = json.loads(
    (REPO_ROOT / "public" / "data" / "meta.json").read_text(encoding="utf-8")
)["source_corpora"]


class PageDirTest(unittest.TestCase):

    def test_every_paged_corpus_is_covered(self):
        paged = {name for name, entry in CORPORA.items() if entry.get("pages_dir")}
        self.assertEqual(set(R.PAGE_DIR), paged)
        self.assertGreater(len(paged), 6, "the stale hardcoded map had six entries")

    def test_a_csv_corpus_is_absent_rather_than_pointing_nowhere(self):
        for name, entry in CORPORA.items():
            if entry.get("csv") and not entry.get("pages_dir"):
                self.assertNotIn(name, R.PAGE_DIR)

    def test_each_path_is_the_one_the_registry_states(self):
        for name, path in R.PAGE_DIR.items():
            self.assertEqual(path, CORPORA[name]["pages_dir"])




class ClaimReconstructionTest(unittest.TestCase):
    """The kinds that had never been rechecked must reach the judge as real claims.

    ``reconstruct_claims`` folds any quote it cannot place into a generic claim, and for
    a long while that fallback read "this quote substantiates a receptor/target mechanism
    classification" -- which a brand name or a half-life does not. Those kinds sat at 0%
    stamped, and had a pass run over them it would have asked the judge the wrong
    question. So: every one of them is reconstructed, and named.
    """

    @classmethod
    def setUpClass(cls):
        quotes = {q["id"]: q for q in R._jsonl("quotes.jsonl")}
        cls.claims, cls.kinds = R.reconstruct_claims(quotes)

    def _one(self, kind):
        got = [q for q, k in self.kinds.items() if k == kind]
        self.assertTrue(got, f"no quote reconstructed as {kind}")
        return got

    def test_brands_half_lives_and_metabolites_are_reconstructed(self):
        for kind in ("drug_brands", "drug_half_life", "drug_metabolites",
                     "drug_metabolite_bindings", "drug_metabolite_enzyme",
                     "drug_enzymes", "addons"):
            self._one(kind)

    def test_a_brand_claim_names_the_brand(self):
        drug = next(d for d in R._jsonl("drugs.jsonl") if d.get("brands"))
        brand = drug["brands"][0]
        qid = brand["sources"][0]["quote_id"]
        self.assertIn(brand["name"], " ".join(self.claims[qid]))
        self.assertEqual(self.kinds[qid], "drug_brands")

    def test_a_half_life_claim_names_the_duration(self):
        drug = next(d for d in R._jsonl("drugs.jsonl")
                    if d.get("half_life_sources") and d.get("half_life"))
        qid = drug["half_life_sources"][0]["quote_id"]
        self.assertIn(R._hours(drug["half_life"]), " ".join(self.claims[qid]))

    def test_a_claim_several_quotes_share_says_so(self):
        # A judge shown one quote beside a claim that two quotes back TOGETHER rejects a
        # citation that carries its share: 5-HT1B's synaptic="both" is one presynaptic
        # quote plus one postsynaptic one, and neither alone says "both". That cost two
        # good quotes a green check once, so the claim now states the arrangement.
        import collections
        per_site = collections.defaultdict(set)
        for qid, texts in self.claims.items():
            for text in texts:
                if " | " in text:
                    per_site[text.split(" | ", 1)[0]].add(qid)
        shared = {s for s, q in per_site.items() if len(q) > 1}
        self.assertTrue(shared, "no co-cited site in the dataset to check against")
        for site in shared:
            for qid in per_site[site]:
                text = next(t for t in self.claims[qid] if t.startswith(site + " | "))
                self.assertIn("cited here alongside", text, f"{qid} at {site}")
        for site, qids in per_site.items():
            if len(qids) == 1:
                qid = next(iter(qids))
                text = next(t for t in self.claims[qid] if t.startswith(site + " | "))
                self.assertNotIn("cited here alongside", text, f"{qid} at {site}")

    def test_nothing_in_those_kinds_falls_back_to_the_generic_claim(self):
        scoped = {"drug_brands", "drug_half_life", "drug_metabolites",
                  "drug_metabolite_bindings"}
        for qid, kind in self.kinds.items():
            if kind in scoped:
                self.assertNotIn("could not be reconstructed",
                                 " ".join(self.claims[qid]), qid)


class ApplyMergeTest(unittest.TestCase):
    """A scoped pass must not wipe the stamps it did not re-judge.

    ``apply`` used to write ``quote_llm.json`` from this pass's verdicts alone, which was
    harmless while every run covered the whole corpus and destructive the moment
    ``build --kinds`` narrowed one: the 759 quotes an earlier pass confirmed would have
    been dropped by a pass that only looked at brands.
    """

    def test_merge_keeps_untouched_stamps_and_demotes_a_failed_recheck(self):
        quotes = [q for q in R._jsonl("quotes.jsonl")][:3]
        keep, demote, promote = (q["id"] for q in quotes)
        with tempfile.TemporaryDirectory() as tmp:
            cache, batches = Path(tmp) / "cache", Path(tmp) / "batches"
            cache.mkdir(), batches.mkdir()
            (cache / "quote_llm.json").write_text(
                json.dumps({keep: "sonnet", demote: "sonnet"}), encoding="utf-8")
            (cache / "quote_recheck_flagged.json").write_text(
                json.dumps([{"qid": keep, "note": "an older flag"},
                            {"qid": promote, "note": "this pass re-judged it"}]),
                encoding="utf-8")
            (batches / "batch_0.json").write_text(
                json.dumps({"pages": {}, "items": [{"qid": promote, "page_ref": "x:1",
                                                    "quote": "q", "claims": ["c"]}]}),
                encoding="utf-8")
            verdicts = Path(tmp) / "v.json"
            verdicts.write_text(json.dumps({"verdicts": {
                demote: {"present": True, "supports": False, "note": "does not attribute"},
                promote: {"present": True, "supports": True}}}), encoding="utf-8")

            old_cache = R.CACHE
            R.CACHE = str(cache)
            try:
                R.cmd_apply(argparse.Namespace(batches=str(batches),
                                               verdicts=str(verdicts), llm="sonnet"))
            finally:
                R.CACHE = old_cache

            stamped = json.loads((cache / "quote_llm.json").read_text(encoding="utf-8"))
            flagged = json.loads(
                (cache / "quote_recheck_flagged.json").read_text(encoding="utf-8"))
        self.assertEqual(stamped.get(keep), "sonnet", "an untouched stamp was dropped")
        self.assertNotIn(demote, stamped, "a failed recheck kept its stamp")
        self.assertEqual(stamped.get(promote), "sonnet")
        self.assertIn(keep, [f["qid"] for f in flagged], "an untouched flag was dropped")
        self.assertIn(demote, [f["qid"] for f in flagged])
        self.assertNotIn(promote, [f["qid"] for f in flagged],
                         "a flag this pass cleared was carried over")

    def test_a_flag_on_a_quote_nobody_cites_any_more_is_dropped(self):
        # A rejected quote is either dropped or repaired into a different sentence, and
        # the id is a content hash, so both leave the old id uncited. Left in the file it
        # is re-proposed by every pass for ever and reads as an item nothing can close.
        quotes = [q for q in R._jsonl("quotes.jsonl")][:2]
        live, judged = (q["id"] for q in quotes)
        with tempfile.TemporaryDirectory() as tmp:
            cache, batches = Path(tmp) / "cache", Path(tmp) / "batches"
            cache.mkdir(), batches.mkdir()
            (cache / "quote_recheck_flagged.json").write_text(
                json.dumps([{"qid": live, "note": "still cited, still open"},
                            {"qid": "q_goneforever", "note": "its sentence was dropped"}]),
                encoding="utf-8")
            (batches / "batch_0.json").write_text(
                json.dumps({"pages": {}, "items": [{"qid": judged, "page_ref": "x:1",
                                                    "quote": "q", "claims": ["c"]}]}),
                encoding="utf-8")
            verdicts = Path(tmp) / "v.json"
            verdicts.write_text(json.dumps({"verdicts": {
                judged: {"present": True, "supports": True}}}), encoding="utf-8")
            old = R.CACHE
            try:
                R.CACHE = str(cache)
                R.cmd_apply(argparse.Namespace(batches=str(batches),
                                               verdicts=str(verdicts), llm="sonnet"))
            finally:
                R.CACHE = old
            flagged = {f["qid"] for f in json.loads(
                (cache / "quote_recheck_flagged.json").read_text(encoding="utf-8"))}
            self.assertEqual(flagged, {live})


class SecondReadTest(unittest.TestCase):
    """A second, weaker model reading a quote can corroborate it or dispute it, never
    silently demote it.

    The user's rule is that no LLM-picked quote ships unjudged by Sonnet or better, and
    the corollary is that a quote Opus already confirmed does not become *less* trusted
    because Sonnet read it too. So a confirming second pass keeps the stronger stamp, and
    a contradicting one parks the quote in ``quote_recheck_disputed.json`` until the
    stronger model is asked again.
    """

    def _apply(self, tmp, prior, verdict, llm):
        """Run ``apply`` over one quote stamped ``prior``, returning the three caches."""
        qid = next(q["id"] for q in R._jsonl("quotes.jsonl"))
        cache, batches = Path(tmp) / "cache", Path(tmp) / "batches"
        cache.mkdir(), batches.mkdir()
        (cache / "quote_llm.json").write_text(json.dumps({qid: prior}), encoding="utf-8")
        (batches / "batch_0.json").write_text(
            json.dumps({"pages": {}, "items": [{"qid": qid, "page_ref": "x:1",
                                               "quote": "q", "claims": ["c"]}]}),
            encoding="utf-8")
        verdicts = Path(tmp) / "v.json"
        verdicts.write_text(json.dumps({"verdicts": {qid: verdict}}), encoding="utf-8")
        old_cache = R.CACHE
        R.CACHE = str(cache)
        try:
            R.cmd_apply(argparse.Namespace(batches=str(batches),
                                           verdicts=str(verdicts), llm=llm))
        finally:
            R.CACHE = old_cache
        read = lambda name: json.loads((cache / name).read_text(encoding="utf-8"))
        return qid, read("quote_llm.json"), read("quote_recheck_flagged.json"), \
            read("quote_recheck_disputed.json")

    def test_a_weaker_confirming_read_keeps_the_stronger_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            qid, stamped, flagged, disputed = self._apply(
                tmp, "opus", {"present": True, "supports": True}, "sonnet")
        self.assertEqual(stamped.get(qid), "opus", "a corroboration demoted the stamp")
        self.assertEqual(flagged, [])
        self.assertEqual(disputed, [])

    def test_a_weaker_doubting_read_disputes_rather_than_demotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            qid, stamped, flagged, disputed = self._apply(
                tmp, "opus", {"present": True, "supports": False, "note": "no"}, "sonnet")
        self.assertEqual(stamped.get(qid), "opus", "a disagreement demoted on its own")
        self.assertEqual(flagged, [], "a disagreement was reported as a settled failure")
        self.assertEqual([d["qid"] for d in disputed], [qid])
        self.assertEqual(disputed[0]["doubted_by"], "sonnet")

    def test_the_stamping_model_settling_it_demotes_and_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            qid, stamped, flagged, disputed = self._apply(
                tmp, "opus", {"present": True, "supports": False, "note": "no"}, "opus")
        self.assertNotIn(qid, stamped, "the model that stamped it could not un-stamp it")
        self.assertEqual([f["qid"] for f in flagged], [qid])
        self.assertEqual(disputed, [])

    def test_a_stronger_confirming_read_upgrades_the_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            qid, stamped, _, _ = self._apply(
                tmp, "haiku", {"present": True, "supports": True}, "sonnet")
        self.assertEqual(stamped.get(qid), "sonnet")



if __name__ == "__main__":
    unittest.main(verbosity=2)
