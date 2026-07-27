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
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_data  # noqa: E402


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
    def setUp(self):
        # a modeled presynaptic inhibitory autoreceptor + a postsynaptic receptor
        self.rec_meta = {
            "alpha2a": {"id": "alpha2a", "sign": "inhibitory", "synaptic": "both"},
            "5ht2a": {"id": "5ht2a", "sign": "excitatory", "synaptic": "postsynaptic"},
        }

    def test_transporter_reuptake_raises(self):
        tgt = {"type": "transporter", "system": "serotonergic"}
        self.assertEqual(check_data._tone_of(tgt, "reuptake_inhibitor", {})[0], 1)
        # a non-tone-setting action on the same transporter contributes nothing
        self.assertEqual(check_data._tone_of(tgt, "agonist", {})[0], 0)

    def test_vesicular_transporter_lowers(self):
        tgt = {"type": "transporter", "system": "dopaminergic", "vesicular": True}
        self.assertEqual(check_data._tone_of(tgt, "blocker", {})[0], -1)
        self.assertEqual(check_data._tone_of(tgt, "vesicular_inhibitor", {})[0], -1)

    def test_vesicular_substrate_raises(self):
        """The other way to engage VMAT2: a substrate (amphetamine, MDMA) dumps the
        vesicular stores into the cytosol, so the SAME target reads tone *up*. The
        direction has to come from the action, not from the target being vesicular
        (which would read the archetypal dopamine-raising drug as lowering it)."""
        tgt = {"type": "transporter", "system": "dopaminergic", "vesicular": True}
        self.assertEqual(check_data._tone_of(tgt, "vesicular_releaser", {})[0], 1)
        # a non-tone-setting action on the same transporter still contributes nothing
        self.assertEqual(check_data._tone_of(tgt, "agonist", {}), (0, None))

    def test_enzyme_inhibition_raises(self):
        tgt = {"type": "enzyme", "system": "serotonergic"}
        self.assertEqual(check_data._tone_of(tgt, "enzyme_inhibitor", {})[0], 1)

    def test_presynaptic_inhibitory_autoreceptor(self):
        tgt = {"type": "receptor", "system": "adrenergic", "receptor": "alpha2a"}
        self.assertEqual(check_data._tone_of(tgt, "agonist", self.rec_meta)[0], -1)
        self.assertEqual(check_data._tone_of(tgt, "antagonist", self.rec_meta)[0], 1)

    def test_postsynaptic_receptor_is_not_a_tone_setter(self):
        tgt = {"type": "receptor", "system": "serotonergic", "receptor": "5ht2a"}
        self.assertEqual(check_data._tone_of(tgt, "antagonist", self.rec_meta),
                         (0, None))


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


if __name__ == "__main__":
    unittest.main()
