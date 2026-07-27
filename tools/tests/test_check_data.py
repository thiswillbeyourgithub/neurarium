#!/usr/bin/env python
"""Unit tests for tools/check_data.py's family-8 flow/binding consistency check.

Stdlib ``unittest`` only (no deps), matching test_generate.py. Runnable directly:

    python tools/tests/test_check_data.py

pytest-discoverable. These lock the ported flow model (``_affinity_weight`` /
``_tone_of``, which mirror js/data.js) and the end-to-end contradiction detection
against small synthetic inputs, so a future edit that silently changes the model,
or the flag conditions, fails loudly here rather than only skewing the eyeball list.

Built with the help of Claude Code.
"""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_data  # noqa: E402
from data_generators.drugs import DRUG_ACTIONS, TONE_RULES  # noqa: E402


def _run_check(meta, drugs, projections, receptors):
    """Run family 8 over synthetic data, returning (report, [warning lines])."""
    report = check_data.Report()
    buf = io.StringIO()
    with redirect_stdout(buf):
        check_data.check_flow_consistency(report, meta, drugs, projections, receptors)
    warns = [ln.split("[warn]", 1)[1].strip()
             for ln in buf.getvalue().splitlines() if "[warn]" in ln]
    return report, warns


class AffinityWeightTest(unittest.TestCase):
    def test_no_ki_is_neutral_mid(self):
        self.assertAlmostEqual(check_data._affinity_weight(None), 0.55)
        self.assertAlmostEqual(check_data._affinity_weight({}), 0.55)
        self.assertAlmostEqual(check_data._affinity_weight({"median": 0}), 0.55)

    def test_ramp_monotonic_and_clamped(self):
        w_strong = check_data._affinity_weight({"median": 1.0})     # 1 nM
        w_weak = check_data._affinity_weight({"median": 1000.0})    # 1 uM
        self.assertGreater(w_strong, w_weak)
        # clamped to [0.35, 1.0] at the extremes
        self.assertLessEqual(check_data._affinity_weight({"median": 0.001}), 1.0)
        self.assertGreaterEqual(check_data._affinity_weight({"median": 1e9}), 0.35)


class ToneSignTest(unittest.TestCase):
    """The flow model's directions. The rule table is DATA, authored once in
    tools/data_generators/drugs.py and shipped as ``meta.tone_rules``, so these load
    the real table rather than a fixture: a direction changed there without a matching
    intent fails here, and the viewer reads the same table so the two cannot drift."""

    def setUp(self):
        # a modeled presynaptic inhibitory autoreceptor + a postsynaptic receptor
        self.rec_meta = {
            "alpha2a": {"id": "alpha2a", "sign": "inhibitory", "synaptic": "both"},
            "5ht2a": {"id": "5ht2a", "sign": "excitatory", "synaptic": "postsynaptic"},
        }
        self.rules = TONE_RULES

    def _tone(self, tgt, action, rec_meta=None):
        return check_data._tone_of(tgt, action, rec_meta or {}, self.rules)

    def test_transporter_reuptake_raises(self):
        tgt = {"type": "transporter", "system": "serotonergic"}
        self.assertEqual(self._tone(tgt, "reuptake_inhibitor")[0], 1)
        # a non-tone-setting action on the same transporter contributes nothing
        self.assertEqual(self._tone(tgt, "agonist")[0], 0)

    def test_vesicular_transporter_lowers(self):
        tgt = {"type": "transporter", "system": "dopaminergic", "vesicular": True}
        self.assertEqual(self._tone(tgt, "blocker")[0], -1)
        self.assertEqual(self._tone(tgt, "vesicular_inhibitor")[0], -1)

    def test_vesicular_substrate_raises(self):
        """The other way to engage VMAT2: a substrate (amphetamine, MDMA) dumps the
        vesicular stores into the cytosol, so the SAME target reads tone *up*. The
        direction has to come from the action, not from the target being vesicular
        (which would read the archetypal dopamine-raising drug as lowering it)."""
        tgt = {"type": "transporter", "system": "dopaminergic", "vesicular": True}
        self.assertEqual(self._tone(tgt, "vesicular_releaser")[0], 1)
        # a non-tone-setting action on the same transporter still contributes nothing
        self.assertEqual(self._tone(tgt, "agonist"), (0, None))

    def test_enzyme_inhibition_raises(self):
        tgt = {"type": "enzyme", "system": "serotonergic"}
        self.assertEqual(self._tone(tgt, "enzyme_inhibitor")[0], 1)

    def test_presynaptic_inhibitory_autoreceptor(self):
        tgt = {"type": "receptor", "system": "adrenergic", "receptor": "alpha2a"}
        self.assertEqual(self._tone(tgt, "agonist", self.rec_meta)[0], -1)
        self.assertEqual(self._tone(tgt, "antagonist", self.rec_meta)[0], 1)

    def test_postsynaptic_receptor_is_not_a_tone_setter(self):
        tgt = {"type": "receptor", "system": "serotonergic", "receptor": "5ht2a"}
        self.assertEqual(self._tone(tgt, "antagonist", self.rec_meta),
                         (0, None))


class ToneRulesAreSharedTest(unittest.TestCase):
    """The rule table has to actually REACH both consumers, or deduplicating it just
    moved the drift somewhere quieter. These lock the two ends of the pipe: the table
    is emitted into meta.json (what the viewer fetches), and every action it names is
    a real one (a typo would silently mean "no tone" rather than failing)."""

    def test_emitted_into_meta(self):
        meta_path = (Path(__file__).resolve().parent.parent.parent
                     / "public" / "data" / "meta.json")
        emitted = json.loads(meta_path.read_text("utf-8")).get("tone_rules")
        self.assertEqual(emitted, json.loads(json.dumps(TONE_RULES)))

    def test_every_rule_names_a_real_action(self):
        actions = set(DRUG_ACTIONS)
        for bucket, rules in TONE_RULES.items():
            for action, rule in rules.items():
                self.assertIn(action, actions, f"{bucket}.{action}")
                self.assertIn(rule[0], (1, -1), f"{bucket}.{action}")

    def test_the_two_vmat2_directions_stay_opposite(self):
        """The bug that motivated the dedup: a VMAT2 substrate and a VMAT2 blocker
        engage one target and must move tone opposite ways."""
        ves = TONE_RULES["vesicular_transporter"]
        self.assertEqual(ves["vesicular_releaser"][0], -ves["vesicular_inhibitor"][0])


class FlowConsistencyEndToEndTest(unittest.TestCase):
    """A drug that raises serotonergic tone via SERT while antagonising a
    postsynaptic 5-HT receptor expressed in the target region must trip BOTH the
    system-level (8a) and region-level (8b) flags; a drug whose postsynaptic action
    agrees with its flow must trip neither."""

    def _meta(self):
        return {
            "drug_targets": {
                "sert": {"type": "transporter", "system": "serotonergic",
                         "receptor": None, "regions": ["raphe"]},
                "5ht2a": {"type": "receptor", "system": "serotonergic",
                          "receptor": "5ht2a", "regions": ["cortex"]},
            },
            "drug_actions": {
                "reuptake_inhibitor": {"effect": "boost"},
                "antagonist": {"effect": "block"},
                "agonist": {"effect": "boost"},
            },
            "system_flow_kinds": {"serotonergic": "serotonergic"},
            # The real rule table, not a fixture copy: the check reads its
            # directions from meta exactly as the viewer does.
            "tone_rules": TONE_RULES,
        }

    def _receptors(self):
        return [{"id": "5ht2a", "sign": "excitatory", "synaptic": "postsynaptic",
                 "family": "serotonergic", "locations": ["cortex"]}]

    def _projections(self):
        return [{"kind": "serotonergic", "from": "raphe", "to": "cortex"}]

    def test_contradiction_trips_both_flags(self):
        drug = {"id": "testblock", "name": "Testblock", "bindings": [
            {"target": "sert", "action": "reuptake_inhibitor", "ki": {"median": 1.0}},
            {"target": "5ht2a", "action": "antagonist", "ki": {"median": 1.0}},
        ]}
        report, warns = _run_check(self._meta(), [drug], self._projections(),
                                   self._receptors())
        self.assertEqual(report.errors, 0)
        joined = "\n".join(warns)
        self.assertIn("serotonergic flow modeled up", joined)   # 8a
        self.assertIn("boosts serotonergic flow into cortex", joined)  # 8b
        self.assertIn("5ht2a", joined)

    def test_agreeing_action_trips_nothing(self):
        drug = {"id": "testboost", "name": "Testboost", "bindings": [
            {"target": "sert", "action": "reuptake_inhibitor", "ki": {"median": 1.0}},
            {"target": "5ht2a", "action": "agonist", "ki": {"median": 1.0}},
        ]}
        _, warns = _run_check(self._meta(), [drug], self._projections(),
                              self._receptors())
        self.assertEqual([w for w in warns if "testboost" in w], [])

    def test_combo_drug_is_skipped(self):
        drug = {"id": "a_plus_b", "name": "A + B", "bindings": [
            {"target": "sert", "action": "reuptake_inhibitor", "ki": {"median": 1.0}},
            {"target": "5ht2a", "action": "antagonist", "ki": {"median": 1.0}},
        ]}
        _, warns = _run_check(self._meta(), [drug], self._projections(),
                              self._receptors())
        self.assertEqual(warns, [])


class SharedMetaboliteGuardTest(unittest.TestCase):
    """The shared-metabolite consistency guard in check_reachability.

    One metabolite can be produced by several modeled drugs (desipramine by imipramine
    AND lofepramine, mCPP by nefazodone AND trazodone). Its bindings are a property of
    the molecule, so every parent's inline copy must be identical; the guard fails loudly
    when a hand-edit diverges them, since divergence would double-list the molecule and
    skew the tally. These lock that behavior against a synthetic pair of parents.
    """

    META = {"drug_targets": {"h1": {}, "d2": {}}, "source_corpora": {}}

    @staticmethod
    def _errors(drugs):
        """Errors raised by check_reachability over a synthetic drug list."""
        report = check_data.Report()
        with redirect_stdout(io.StringIO()):
            check_data.check_reachability(report, SharedMetaboliteGuardTest.META,
                                          [], [], [], [], [], drugs)
        return report.errors

    @staticmethod
    def _parents(binding_a, binding_b):
        """Two drugs sharing a metabolite 'FooBar' with the given inline bindings."""
        return [
            {"id": "drugA", "name": "DrugA", "bindings": [],
             "metabolites": [{"name": "FooBar", "bindings": binding_a}]},
            {"id": "drugB", "name": "DrugB", "bindings": [],
             "metabolites": [{"name": "FooBar", "bindings": binding_b}]},
        ]

    def test_divergent_bindings_add_exactly_one_error(self):
        b = [{"target": "h1", "action": "antagonist"}]
        # Same two parents, once with identical metabolite bindings and once with
        # divergent ones: only the divergence trips the guard, so it costs exactly one
        # extra error (isolating the guard from any unrelated per-drug errors).
        identical = self._errors(self._parents(b, [dict(b[0])]))
        diverged = self._errors(self._parents(
            b, [{"target": "d2", "action": "antagonist"}]))
        self.assertEqual(diverged, identical + 1)


class NoSubjectQuoteTest(unittest.TestCase):
    """A binding quote can be verbatim on the page and still support nothing.

    Stahl's "How Drug Causes Side Effects" block lists the CLASS's mechanisms as
    subject-less rules, identically across monographs, so it never says this drug
    has the action; 151 antipsychotic bindings were once sourced from three such
    lines. The guard has to separate those from the sentences that do attribute
    the action, which look superficially similar."""

    def _m(self, quote):
        return bool(check_data._NO_SUBJECT_QUOTE.match(quote))

    def test_class_boilerplate_is_rejected(self):
        for quote in (
            "Blocking muscarinic cholinergic receptors can cause dry mouth, blurred "
            "vision, urinary retention, constipation, and paralytic ileus",
            "Blocking alpha 1 adrenergic receptors can cause dizziness, hypotension, "
            "and syncope",
            "Antihistaminic actions may cause sedation, weight gain",
        ):
            self.assertTrue(self._m(quote), quote)

    def test_attributed_mechanism_is_accepted(self):
        for quote in (
            # the subject is the drug ("it"), so this one really does claim H1 blockade
            "By blocking histamine 1 receptors in the brain, it can cause sedation and "
            "possibly weight gain",
            "Paroxetine's weak antimuscarinic properties can cause constipation, dry "
            "mouth, and blurred vision",
            "Anticholinergic actions, especially at high doses, may cause sedation",
            # a plain mechanism statement, the normal "How the Drug Works" shape
            "Blocks dopamine 2 receptors, reducing positive symptoms of psychosis",
        ):
            self.assertFalse(self._m(quote), quote)


class StahlMonographRangeTest(unittest.TestCase):
    """The other half of "is this quote about this drug?": a Stahl quote has to sit
    on a page of the drug's OWN monograph. A sentence lifted off the neighbouring
    entry is verbatim on the page it cites and still says nothing about this drug,
    so the verbatim gate alone cannot catch it."""

    RANGES = {"sulpiride": (786, 790), "sertraline": (770, 775),
              "dextromethorphanbupropion": (247, 252), "bupropion": (128, 133)}

    def _drug(self, name, pages, **extra):
        return {"id": name.lower(), "name": name, "bindings": [
            {"target": "d2", "sources": [{"corpus": "stahl", "page": p, "quote": "x"}]}
            for p in pages], **extra}

    def test_own_monograph_passes(self):
        pages, span, stray = check_data.stahl_monograph_check(
            self._drug("Sulpiride", [786, 788]), self.RANGES)
        self.assertEqual((pages, span, stray), ([786, 788], (786, 790), []))

    def test_neighbouring_monograph_is_caught(self):
        _pages, span, stray = check_data.stahl_monograph_check(
            self._drug("Sulpiride", [788, 771]), self.RANGES)
        self.assertEqual(span, (786, 790))
        self.assertEqual(stray, [771])

    def test_quotes_are_found_anywhere_in_the_drug(self):
        """Not just on bindings: half-life, NbN, metabolite and brand sources all
        cite pages the same way, so the walk has to reach them too."""
        drug = self._drug("Sulpiride", [788])
        drug["half_life_sources"] = [{"corpus": "stahl", "page": 4242, "quote": "x"}]
        drug["metabolites"] = [{"name": "m", "sources": [
            {"corpus": "kandel", "page": 9, "quote": "x"},      # another corpus: ignored
            {"corpus": "stahl", "page": 789, "quote": "x"}]}]
        pages, _span, stray = check_data.stahl_monograph_check(drug, self.RANGES)
        self.assertEqual(pages, [788, 789, 4242])
        self.assertEqual(stray, [4242])

    def test_combo_matches_either_half(self):
        """A combo is indexed under its own name here; when it is not, either
        constituent's monograph is the honest span."""
        _pages, span, _stray = check_data.stahl_monograph_check(
            self._drug("Bupropion + Naltrexone", [130]), self.RANGES)
        self.assertEqual(span, (128, 133))

    def test_unindexed_drug_reports_no_span(self):
        """A drug Stahl has no monograph for is unrangeable, not in violation."""
        pages, span, stray = check_data.stahl_monograph_check(
            self._drug("Psilocybin", [500]), self.RANGES)
        self.assertEqual((pages, span, stray), ([500], None, []))

    def test_name_folding_ignores_case_and_punctuation(self):
        self.assertEqual(check_data._fold_name("Amphetamine (D,L)"),
                         check_data._fold_name("amphetamine (d,l)"))


if __name__ == "__main__":
    unittest.main()
