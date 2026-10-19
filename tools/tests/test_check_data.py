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
import re
import sys
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_data  # noqa: E402
from checks.common import REPO_ROOT, Report  # noqa: E402
from checks.duplicates import check_binding_dups, check_id_collection  # noqa: E402
from checks.flow import _affinity_weight, _tone_of, check_flow_consistency  # noqa: E402
from checks.freshness import check_freshness  # noqa: E402
from checks.innervation import check_innervation  # noqa: E402
from checks.provenance import check_provenance  # noqa: E402
from checks.quotes import rehydrate_quotes  # noqa: E402
from checks.reachability import check_reachability  # noqa: E402
from checks.sources import check_sources  # noqa: E402
from checks.sources.drugs import _NO_SUBJECT_QUOTE  # noqa: E402
from checks.sources.gate import spans_heading  # noqa: E402
from checks.sources.stahl import stahl_monograph_check  # noqa: E402
from lib.text_fold import alnum_key  # noqa: E402
from checks.todos import check_todos  # noqa: E402
from checks.walks import iter_drug_sources  # noqa: E402
from lib.quote_match import normalize_for_match  # noqa: E402
from data_generators.drugs import DRUG_ACTIONS, TONE_RULES  # noqa: E402


def _run_check(meta, drugs, projections, receptors):
    """Run family 8 over synthetic data, returning (report, [review lines])."""
    report = Report(verbose=True)
    buf = io.StringIO()
    with redirect_stdout(buf):
        check_flow_consistency(report, meta, drugs, projections, receptors)
    warns = [ln.split("[review]", 1)[1].strip()
             for ln in buf.getvalue().splitlines() if "[review]" in ln]
    return report, warns


class SpansHeadingTest(unittest.TestCase):
    """A quote glued across a page's section heading is refused (prazepam's metabolite
    quote ran on into "## Interactions" and still matched once whitespace folded)."""

    def test_heading_line_inside_a_quote(self):
        glued = ("Prazepam is a prodrug for desmethyldiazepam.\n\n## Interactions\n"
                 "Prazepam may interact with cimetidine .")
        self.assertTrue(spans_heading(glued))
        self.assertFalse(spans_heading(
            "Prazepam is a prodrug for desmethyldiazepam."))
        self.assertFalse(spans_heading("Ki | 5-HT2A | #3 site"))


class NormalizeForMatchTest(unittest.TestCase):
    """The quote gate's canonical form folds typesetting away, never text."""

    def test_soft_hyphen_line_break_joins_the_word(self):
        # A table cell wrapped at a soft hyphen (the AGNP TDM Table 5 drug column)
        # used to split into "brexpi prazole", so the row's quote could not match.
        page = normalize_for_match("Brexpi\u00ad\nprazole + \n24 h")
        self.assertIn(normalize_for_match("Brexpiprazole 24 h"), page)

    def test_underline_tag_keeps_its_content(self):
        # Table 1 underlines enzymes as `<u>CYP1A2,</u>`; the tag used to leave a
        # stray "u" word between the drug and its enzyme.
        page = normalize_for_match("Clozapine **<u>CYP1A2, CYP2C19,</u>** CYP3A4")
        self.assertIn(normalize_for_match("Clozapine CYP1A2, CYP2C19, CYP3A4"), page)

    def test_a_real_u_word_survives(self):
        self.assertEqual(normalize_for_match("vitamin U"), "vitamin u")


class AffinityWeightTest(unittest.TestCase):
    def test_no_ki_is_neutral_mid(self):
        self.assertAlmostEqual(_affinity_weight(None), 0.55)
        self.assertAlmostEqual(_affinity_weight({}), 0.55)
        self.assertAlmostEqual(_affinity_weight({"median": 0}), 0.55)

    def test_ramp_monotonic_and_clamped(self):
        w_strong = _affinity_weight({"median": 1.0})     # 1 nM
        w_weak = _affinity_weight({"median": 1000.0})    # 1 uM
        self.assertGreater(w_strong, w_weak)
        # clamped to [0.35, 1.0] at the extremes
        self.assertLessEqual(_affinity_weight({"median": 0.001}), 1.0)
        self.assertGreaterEqual(_affinity_weight({"median": 1e9}), 0.35)


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
        return _tone_of(tgt, action, rec_meta or {}, self.rules)

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


class ReviewLevelTest(unittest.TestCase):
    """A review item is counted but printed only under --verbose (never a warning)."""

    def _out(self, verbose):
        report = Report(verbose=verbose)
        buf = io.StringIO()
        with redirect_stdout(buf):
            report.review("drug 'x': intended split")
            check_data._summary(report)
        return report, buf.getvalue()

    def test_hidden_by_default_but_counted(self):
        report, out = self._out(False)
        self.assertEqual((report.reviews, report.warnings), (1, 0))
        self.assertNotIn("intended split", out)
        self.assertIn("1 review item(s) not listed", out)

    def test_listed_when_verbose(self):
        _, out = self._out(True)
        self.assertIn("[review] drug 'x': intended split", out)


class MetaboliteStoreTest(unittest.TestCase):
    """The metabolite-store reachability checks in check_reachability.

    A metabolite is ONE metabolites.jsonl record however many drugs make it
    (desipramine by imipramine AND lofepramine), each parent holding only an ``{id}``
    reference. So the failure modes are a dangling ref, an orphan record no panel
    reaches, a ``drug_id`` link to no drug, and a binding on no known target. Each is
    measured against a clean synthetic baseline, so the test isolates exactly one error.
    """

    META = {"drug_targets": {"h1": {}, "d2": {}}, "source_corpora": {}}

    @staticmethod
    def _errors(drugs, metabolites):
        report = Report()
        with redirect_stdout(io.StringIO()):
            check_reachability(report, MetaboliteStoreTest.META,
                                          [], [], [], [], [], drugs, [], metabolites)
        return report.errors

    @staticmethod
    def _world(**metab):
        """Two drugs sharing metabolite 'foobar' (one record, two refs)."""
        drugs = [{"id": "drugA", "name": "DrugA", "bindings": [],
                  "metabolites": [{"id": "foobar"}]},
                 {"id": "drugB", "name": "DrugB", "bindings": [],
                  "metabolites": [{"id": "foobar"}]}]
        rec = {"id": "foobar", "name": "FooBar",
               "bindings": [{"target": "h1", "action": "antagonist"}]}
        rec.update(metab)
        return drugs, [rec]

    def setUp(self):
        self.base = self._errors(*self._world())

    def test_dangling_ref_is_one_error(self):
        drugs, metabs = self._world()
        drugs[0]["metabolites"].append({"id": "nope"})
        self.assertEqual(self._errors(drugs, metabs), self.base + 1)

    def test_orphan_record_is_one_error(self):
        drugs, metabs = self._world()
        metabs.append({"id": "lonely", "name": "Lonely"})
        self.assertEqual(self._errors(drugs, metabs), self.base + 1)

    def test_bad_drug_link_is_one_error(self):
        self.assertEqual(self._errors(*self._world(drug_id="ghost")), self.base + 1)

    def test_unknown_binding_target_is_one_error(self):
        bad = self._world(bindings=[{"target": "zz", "action": "antagonist"}])
        self.assertEqual(self._errors(*bad), self.base + 1)


class NoSubjectQuoteTest(unittest.TestCase):
    """A binding quote can be verbatim on the page and still support nothing.

    Stahl's "How Drug Causes Side Effects" block lists the CLASS's mechanisms as
    subject-less rules, identically across monographs, so it never says this drug
    has the action; 151 antipsychotic bindings were once sourced from three such
    lines. The guard has to separate those from the sentences that do attribute
    the action, which look superficially similar."""

    def _m(self, quote):
        return bool(_NO_SUBJECT_QUOTE.match(quote))

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
        pages, span, stray = stahl_monograph_check(
            self._drug("Sulpiride", [786, 788]), self.RANGES)
        self.assertEqual((pages, span, stray), ([786, 788], (786, 790), []))

    def test_neighbouring_monograph_is_caught(self):
        _pages, span, stray = stahl_monograph_check(
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
        pages, _span, stray = stahl_monograph_check(drug, self.RANGES)
        self.assertEqual(pages, [788, 789, 4242])
        self.assertEqual(stray, [4242])

    def test_combo_matches_either_half(self):
        """A combo is indexed under its own name here; when it is not, either
        constituent's monograph is the honest span."""
        _pages, span, _stray = stahl_monograph_check(
            self._drug("Bupropion + Naltrexone", [130]), self.RANGES)
        self.assertEqual(span, (128, 133))

    def test_unindexed_drug_reports_no_span(self):
        """A drug Stahl has no monograph for is unrangeable, not in violation."""
        pages, span, stray = stahl_monograph_check(
            self._drug("Psilocybin", [500]), self.RANGES)
        self.assertEqual((pages, span, stray), ([500], None, []))

    def test_name_folding_ignores_case_and_punctuation(self):
        self.assertEqual(alnum_key("Amphetamine (D,L)"),
                         alnum_key("amphetamine (d,l)"))


class UncertaintyBulletTest(unittest.TestCase):
    """Family 5's gates on the "uncertain" badge's bullets.

    The trap this exists for (see the new-node-kind checklist): family 5 passes
    silently until its walk actually *visits* a new kind, so every case below is
    written to fail if the walk skips a node's ``uncertainty`` entirely."""

    META = {"source_corpora": {"stahl": {"ref": "Stahl"},
                               "pdsp_ki": {"ref": "PDSP", "csv": "x.csv"}},
            "quote_pipelines": {"page_llm_judged": ["raw", "extract_llm",
                                                    "judge_llm", "neurarium"]},
            "uncertainty_reasons": {"side_effect_rule": {}, "not_a_mechanism": {},
                                    "contradicted": {}}}
    # A subject-less side-effect rule: verbatim on the page, and it attributes
    # nothing. This is the shape the badge exists for.
    QUOTE = ("Blocking alpha 1 adrenergic receptors can cause dizziness, "
             "hypotension, and syncope")

    def _errors(self, binding):
        report = Report()
        with redirect_stdout(io.StringIO()):
            check_sources(report, self.META,
                                     [{"id": "d", "bindings": [binding]}], [], [], [],
                                     [])
        return report.errors

    def _binding(self, uncertainty, quote="a plain attributed sentence"):
        return {"target": "alpha1a", "uncertainty": uncertainty,
                "sources": [{"corpus": "stahl", "page": 40, "quote": quote,
                             "provenance": "verified",
                             "pipeline": "page_llm_judged"}]}

    def test_a_sourceless_bullet_must_declare_absence(self):
        self.assertEqual(self._errors(self._binding(
            [{"kind": "side_effect_rule"}])), 1)
        self.assertEqual(self._errors(self._binding(
            [{"kind": "not_a_mechanism", "absence": True}])), 0)

    def test_an_absence_bullet_may_not_also_cite_a_source(self):
        """Contradictory: the pill would read NOSOURCE over a real citation."""
        self.assertEqual(self._errors(self._binding(
            [{"kind": "not_a_mechanism", "absence": True,
              "sources": [{"corpus": "stahl", "page": 40, "quote": "x",
                       "pipeline": "page_llm_judged"}]}])), 1)

    def _contradiction_errors(self, binding, site):
        report = Report()
        with redirect_stdout(io.StringIO()):
            check_sources(report, self.META,
                                     [{"id": "d", "bindings": [binding]}], [], [], [],
                                     [], contradictions={site: {}})
        return report.errors

    def test_a_contradiction_site_must_name_a_flagged_node(self):
        """CONTRADICTIONS is keyed by citation site: a site naming no emitted node
        marks nothing, and a named node without its bullet means stale data/."""
        flagged = self._binding([{"kind": "not_a_mechanism", "absence": True},
                                 {"kind": "contradicted", "absence": True}])
        flagged["action"] = "antagonist"
        self.assertEqual(self._contradiction_errors(
            flagged, "drug:d/bindings[alpha1a:antagonist]"), 0)
        self.assertEqual(self._contradiction_errors(
            flagged, "drug:d/bindings[alpha1a:agonist]"), 1)
        bare = self._binding([{"kind": "not_a_mechanism", "absence": True}])
        bare["action"] = "antagonist"
        self.assertEqual(self._contradiction_errors(
            bare, "drug:d/bindings[alpha1a:antagonist]"), 1)

    def test_kind_must_be_in_the_shipped_vocabulary(self):
        self.assertEqual(self._errors(self._binding(
            [{"kind": "vibes", "absence": True}])), 1)

    def test_bullet_sources_go_through_the_quote_gate(self):
        """Proven with an unresolvable corpus, which errors on any machine; the
        verbatim half needs the author-side pages and is exercised by the real
        run of check_data.py."""
        self.assertEqual(self._errors(self._binding(
            [{"kind": "side_effect_rule",
              "sources": [{"corpus": "nosuchbook", "page": 40, "quote": "x"}]}])), 1)

    def test_a_measured_ki_bullet_is_not_asked_for_prose(self):
        """A PDSP source is a CSV row id, gated by family 8, so requiring a quote
        here would fail every measured_ki bullet."""
        self.assertEqual(self._errors(self._binding(
            [{"kind": "side_effect_rule",
              "sources": [{"corpus": "pdsp_ki", "ki_id": 7,
                           "provenance": "verified"}]}])), 0)

    def test_a_measured_ki_bullet_is_gated_against_the_csv(self):
        """Regression: family 8 walked only a binding's own ``ki``, so a bullet citing
        a PDSP row (a curated denial like MDMA 5-HT1B "> 10000 nM") reached no gate."""
        import tempfile

        def errors(ki_id, value):
            with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp:
                Path(tmp, "ki.csv").write_text("Number,ki Val\n7,10000\n", encoding="utf-8")
                rel = str(Path(tmp, "ki.csv").relative_to(REPO_ROOT))
                meta = {**self.META, "source_corpora": {
                    **self.META["source_corpora"], "pdsp_ki": {"ref": "PDSP", "csv": rel}}}
                report = Report()
                binding = self._binding([{"kind": "contradicted", "sources": [
                    {"corpus": "pdsp_ki", "ki_id": ki_id, "value_nm": value,
                     "provenance": "verified"}]}])
                with redirect_stdout(io.StringIO()):
                    check_sources(report, meta, [{"id": "d", "bindings": [binding]}],
                                             [], [], [], [])
                return report.errors
        self.assertEqual(errors(7, 10000), 0)
        self.assertEqual(errors(8, 10000), 1)
        self.assertEqual(errors(7, 5), 1)

    def test_declaring_uncertainty_stands_the_subjectless_guard_down(self):
        """The two mechanisms answer the same problem, so they must not both fire:
        the guard bans such a quote outright, the badge keeps it and says why."""
        self.assertEqual(self._errors(self._binding(
            [{"kind": "not_a_mechanism", "absence": True}], quote=self.QUOTE)), 0)
        # ... and without the declaration the guard still rejects it
        b = self._binding([], quote=self.QUOTE)
        del b["uncertainty"]
        self.assertEqual(self._errors(b), 1)

    def test_a_pathways_bullets_are_gated_too(self):
        """The badge is not a drug-only feature: a blanket pathway carries the same
        bullets, so the walk must reach them there as well (the checklist trap again,
        one node kind further on)."""
        def errors(uncertainty):
            report = Report()
            proj = {"from": "raphe", "to": "caudate_R", "uncertainty": uncertainty,
                    "sources": [{"corpus": "stahl", "page": 40, "quote": "x",
                                 "provenance": "verified",
                                 "pipeline": "page_llm_judged"}]}
            with redirect_stdout(io.StringIO()):
                check_sources(report, self.META, [], [proj], [], [], [])
            return report.errors
        self.assertEqual(errors([{"kind": "not_a_mechanism", "absence": True}]), 0)
        self.assertEqual(errors([{"kind": "vibes", "absence": True}]), 1)
        self.assertEqual(errors([{"kind": "side_effect_rule"}]), 1)
        self.assertEqual(errors([{"kind": "side_effect_rule",
                                  "sources": [{"corpus": "nosuchbook", "page": 1,
                                               "quote": "x"}]}]), 1)


class InnervationCoverageTest(unittest.TestCase):
    """Family 10: regions expressing a transmitter system that no pathway of that
    system reaches. Warning-only, so what these lock is that the arithmetic points at
    the right regions (a false 'fully covered' would quietly hide the gap the check
    exists to surface)."""

    STRUCTS = [{"id": f"{b}_R", "base_name": b.title()} for b in
               ("raphe", "frontal", "occipital", "thalamus")]

    def _run(self, receptors, projections, meta=None):
        report = Report()
        buf = io.StringIO()
        base_meta = {"system_flow_kinds": {"serotonergic": "serotonergic"},
                     "drug_targets": {}}
        with redirect_stdout(buf):
            check_innervation(report, meta or base_meta, self.STRUCTS,
                                         projections, receptors)
        return [ln.split("[warn]", 1)[1].strip()
                for ln in buf.getvalue().splitlines() if "[warn]" in ln]

    def test_unreached_region_is_named(self):
        warns = self._run(
            [{"id": "5ht2a", "family": "serotonergic",
              "locations": ["frontal", "occipital"]}],
            [{"kind": "serotonergic", "from": "raphe_R", "to": "frontal_R"}])
        self.assertEqual(len(warns), 1)
        self.assertIn("1/2 region(s)", warns[0])
        self.assertIn("Occipital", warns[0])
        self.assertNotIn("Frontal", warns[0])

    def test_full_coverage_warns_nothing(self):
        self.assertEqual(self._run(
            [{"id": "5ht2a", "family": "serotonergic", "locations": ["frontal"]}],
            [{"kind": "serotonergic", "from": "raphe_R", "to": "frontal_R"}]), [])

    def test_ubiquitous_receptor_is_ignored(self):
        """A receptor expressed everywhere would put every region in every gap and
        drown the signal, so it is excluded rather than counted as unreached."""
        self.assertEqual(self._run(
            [{"id": "5ht2a", "family": "serotonergic", "ubiquitous": True,
              "locations": ["frontal", "occipital", "thalamus"]}],
            [{"kind": "serotonergic", "from": "raphe_R", "to": "frontal_R"}]), [])

    def test_expression_gap_is_reported_but_not_for_a_source_nucleus(self):
        """The mirror question: a pathway landing where the system has no recorded
        receptor means the expression layer is thin. Its own source nucleus does not
        count (a nucleus need not express what it projects onto)."""
        warns = self._run(
            [{"id": "5ht2a", "family": "serotonergic", "locations": ["frontal"]}],
            [{"kind": "serotonergic", "from": "raphe_R", "to": "frontal_R"},
             {"kind": "serotonergic", "from": "raphe_R", "to": "thalamus_R"}])
        gaps = [w for w in warns if "expression gap" in w]
        self.assertEqual(len(gaps), 1)
        self.assertIn("thalamus", gaps[0])
        self.assertNotIn("raphe", gaps[0])

    def test_family_with_no_projection_kind_is_flagged(self):
        warns = self._run(
            [{"id": "mt1", "family": "melatonergic", "locations": ["thalamus"]}],
            [])
        self.assertTrue(any("no projection kind at all" in w and "melatonergic" in w
                            for w in warns))


class UnjudgedQuoteGateTest(unittest.TestCase):
    """No LLM-picked quote ships unjudged.

    A sentence a model *chose* out of prose is the one that can be chosen wrongly
    (right page, wrong claim), so it is not backed until a second model agreed it
    supports the claim. The gate reads the rule OFF `meta.quote_pipelines` rather
    than off a list of key names, so a new pipeline is covered the day it lands;
    these tests pin both halves of that reading.
    """

    META = {
        "source_corpora": {"stahl": {"ref": "Stahl"}},
        "quote_pipelines": {
            "page_llm": ["raw", "extract_llm", "neurarium"],
            "page_llm_judged": ["raw", "extract_llm", "judge_llm", "neurarium"],
            "page_code": ["raw", "code", "neurarium"],
        },
    }

    def _run(self, pipeline):
        drug = {"id": "clozapine", "name": "Clozapine", "bindings": [{
            "target": "5ht2a",
            "sources": [{"corpus": "stahl", "page": 1, "quote": "x",
                         "provenance": "verified", "pipeline": pipeline}],
        }]}
        report = Report()
        buf = io.StringIO()
        with redirect_stdout(buf):
            check_sources(report, self.META, [drug], [], [], [], [])
        return report, buf.getvalue()

    def test_an_extracted_but_unjudged_quote_fails(self):
        report, out = self._run("page_llm")
        self.assertTrue(report.errors)
        self.assertIn("never judged", out)

    def test_a_judged_quote_passes(self):
        report, out = self._run("page_llm_judged")
        self.assertIn("every LLM-picked quote was judged", out)

    def test_a_code_grepped_quote_needs_no_judge(self):
        # A quote copied out of a table cannot be chosen wrongly, so the rule reads
        # it as clean: the chain has no extract_llm step to doubt.
        _report, out = self._run("page_code")
        self.assertIn("every LLM-picked quote was judged", out)

    def test_a_pipeline_meta_cannot_render_fails(self):
        report, out = self._run("page_invented")
        self.assertTrue(report.errors)
        self.assertIn("not in meta.quote_pipelines", out)


class CorpusUrlTest(unittest.TestCase):
    """A source corpus's ``url`` is optional but, when present, must be a real link.

    A copyrighted book has no free landing page, so it carries no ``url`` at all (the
    provenance pill, not a link, conveys the grade). The placeholder it used to carry
    was indistinguishable from a forgotten one, so a present-but-unlinkable url is now
    an error: these lock both halves.
    """

    @staticmethod
    def _errors(corpora):
        report = Report()
        with redirect_stdout(io.StringIO()):
            check_todos(report, {"source_corpora": corpora},
                                   [], [], [], [], [], [])
        return report.errors

    def test_absent_url_is_accepted(self):
        self.assertEqual(self._errors({"stahl": {"ref": "Stahl", "citation": "S."}}), 0)

    def test_real_url_is_accepted(self):
        self.assertEqual(
            self._errors({"gtopdb": {"ref": "G", "url": "https://example.org/"}}), 0)

    def test_placeholder_url_is_an_error(self):
        self.assertEqual(self._errors({"stahl": {"ref": "Stahl", "url": "TODO"}}), 1)


class FreshnessTest(unittest.TestCase):
    """Family 13: a cited page of an editable corpus older than 12 months fails.

    A Wikipedia article or a live database can change under a citation, so its
    download date rides every source and ages into an error. Today is pinned, so the
    test does not itself go stale.
    """

    TODAY = date(2026, 10, 11)
    META = {"source_corpora": {"wikipedia_pharm": {"ref": "W", "editable": True},
                               "stahl": {"ref": "S"}}}

    def _errors(self, sources):
        report = Report()
        with redirect_stdout(io.StringIO()):
            check_freshness(report, self.META, [[{"sources": sources}]],
                                       today=self.TODAY)
        return report.errors

    def test_fresh_page_passes(self):
        self.assertEqual(self._errors([{"corpus": "wikipedia_pharm", "page": "x_fresh",
                                        "fetched": "2026-10-11"}]), 0)

    def test_thirteen_month_old_page_fails(self):
        self.assertEqual(self._errors([{"corpus": "wikipedia_pharm", "page": "x_old",
                                        "fetched": "2025-09-11"}]), 1)

    def test_exactly_twelve_months_still_passes(self):
        self.assertEqual(self._errors([{"corpus": "wikipedia_pharm", "page": "x_edge",
                                        "fetched": "2025-10-11"}]), 0)

    def test_undated_page_fails(self):
        self.assertEqual(self._errors([{"corpus": "wikipedia_pharm", "page": "x_none"}]), 1)

    def test_book_page_needs_no_date(self):
        self.assertEqual(self._errors([{"corpus": "stahl", "page": 15}]), 0)


class FamilyCountTest(unittest.TestCase):
    """The numbered families, against the two docs that count them in prose.

    Adding a family is three edits in three files, and the two doc edits are the ones
    nothing notices: the count drifts, a reader trusts it, and the newest gate reads as
    something the checker does not run. So the numbers are read back off the source of
    truth here rather than restated.
    """

    ROOT = Path(__file__).resolve().parent.parent.parent
    # The docs spell the count as a word, so the count has to be spelled here too.
    # Only the range that can plausibly come next: a count outside it is a failure
    # naming the missing word, not a KeyError that says nothing about the docs.
    WORDS = {11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
             15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
             19: "nineteen", 20: "twenty"}

    @classmethod
    def setUpClass(cls):
        # The families live in tools/checks/ (one module each), driven by check_data.py.
        files = [cls.ROOT / "tools" / "check_data.py",
                 *sorted((cls.ROOT / "tools" / "checks").rglob("*.py"))]
        src = "\n".join(f.read_text(encoding="utf-8") for f in files)
        cls.numbers = sorted(int(n) for n in
                             re.findall(r'report\.header\("(\d+)\.', src))

    def test_the_families_are_numbered_contiguously_from_zero(self):
        # A gap or a repeat would print two families under one number, which reads as
        # one gate having silently swallowed the other.
        self.assertEqual(self.numbers, list(range(len(self.numbers))))

    def test_both_docs_state_the_real_count(self):
        count = len(self.numbers)
        word = self.WORDS.get(count)
        self.assertIsNotNone(word, f"{count} families, which WORDS has no word for: "
                                   f"add it, then say {count} in both docs")
        last = self.numbers[-1]
        want = f"{word.capitalize()} families (numbered 0-{last} in the output)"
        # Whitespace-normalized, so the sentence is matched as a sentence: where the
        # markdown happens to wrap mid-paragraph is not what this test is about (and
        # the repo's own convention says not to hard-wrap one).
        checks = " ".join(
            (self.ROOT / "docs" / "DATA_CHECKS.md").read_text(encoding="utf-8").split())
        # assertIn would print the whole document on failure; the count is the message.
        self.assertTrue(want in checks, f"docs/DATA_CHECKS.md does not say {want!r}")
        claude = (self.ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(f"{word} families (" in claude,
                        f"CLAUDE.md does not say {word!r} families")


class RehydrateQuotesTest(unittest.TestCase):
    """``rehydrate_quotes`` copies EVERY quote-node field but ``id``, the same rule as
    js/data.js's rehydrateQuotes, so the two never need a shared field list (they
    once each kept their own copy of it, which a new quote-node field had to update
    twice)."""

    def test_copies_every_field_but_id(self):
        by_id = {"q1": {"id": "q1", "corpus": "stahl", "page": 15, "quote": "x",
                        "a_future_field": 1}}
        node = {"sources": [{"quote_id": "q1", "provenance": "verified"}]}
        referenced, dangling = set(), []
        rehydrate_quotes(node, by_id, referenced, dangling)
        self.assertEqual(node["sources"][0], {"provenance": "verified", "corpus": "stahl",
                                              "page": 15, "quote": "x",
                                              "a_future_field": 1})
        self.assertEqual((referenced, dangling), ({"q1"}, []))

    def test_dangling_id_reported(self):
        dangling = []
        rehydrate_quotes([{"quote_id": "nope"}], {}, set(), dangling)
        self.assertEqual(dangling, ["nope"])


class ShortQuoteTest(unittest.TestCase):
    """The "very short quote, may be an incidental substring" warning skips a Ki row.

    A Ki quote is one affinity-table row ('5-HT 1B | 1744 | Human'): short by design,
    and its target + value make a chance match implausible, so warning on it only
    buried the real short quotes (it fired on ~480 Ki rows on every run)."""

    PAGE = ("5-HT 1B | 1744 | Human\nIt blocks D2 well.\nClass: Stimulant\n"
            "α 2A | 15 | Antagonist\nInhibits CYP2D6\n")

    def _warns(self, drug):
        """The incidental-substring warnings check_sources prints for one drug, its
        quotes cited against a one-page synthetic corpus ``wiki`` holding PAGE."""
        import tempfile
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp:
            Path(tmp, "page.md").write_text(self.PAGE, encoding="utf-8")
            rel = str(Path(tmp).relative_to(REPO_ROOT))
            meta = {"source_corpora": {"wiki": {"pages_dir": rel}}}
            buf = io.StringIO()
            with redirect_stdout(buf):
                check_sources(Report(), meta,
                                         [{"id": "x", "bindings": [], **drug}], [], [], [], [])
        return [ln for ln in buf.getvalue().splitlines() if "incidental" in ln]

    @staticmethod
    def _src(quote):
        return {"corpus": "wiki", "page": "page", "quote": quote, "provenance": "sourced"}

    def test_a_ki_row_is_not_warned(self):
        ki = {"source": self._src("5-HT 1B | 1744 | Human")}
        self.assertEqual(self._warns({"bindings": [{"target": "5ht1b", "ki": ki}]}), [])

    def test_a_class_label_is_not_warned(self):
        self.assertEqual(self._warns({"category_sources": [self._src("Stimulant")]}), [])

    def test_any_table_row_is_not_warned(self):
        # A direction row cited by a binding (not a Ki) is a whole table row too.
        binding = {"target": "alpha2a", "sources": [self._src("α 2A | 15 | Antagonist")]}
        self.assertEqual(self._warns({"bindings": [binding]}), [])

    def test_a_metabolism_cell_is_not_warned(self):
        enzyme = {"enzyme": "cyp2d6", "sources": [self._src("Inhibits CYP2D6")]}
        self.assertEqual(self._warns({"enzymes": [enzyme]}), [])

    def test_a_short_binding_quote_still_is(self):
        binding = {"target": "d2", "sources": [self._src("blocks D2")]}
        self.assertEqual(len(self._warns({"bindings": [binding]})), 1)


class DrugSourceWalkTest(unittest.TestCase):
    """``iter_drug_sources`` is THE walk the grade family (4) and the quote family (5)
    share: every list of citations a shipped drug carries must be on it, or a new facet
    is neither graded nor quote-gated. The only lists it leaves out are the uncertainty
    bullets', gated per bullet by ``check_uncertainty``."""
    LEFT_OUT = {"uncertainty"}

    def test_every_citation_list_of_a_shipped_drug_is_walked(self):
        path = Path(__file__).resolve().parents[2] / "public" / "data" / "drugs.jsonl"
        missed = set()

        def walk(node, key, seen):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in self.LEFT_OUT:
                        continue
                    if (isinstance(v, list) and v
                            and all(isinstance(x, dict) and "corpus" in x for x in v)):
                        missed.update(f"{key}.{k}" for x in v if id(x) not in seen)
                    walk(v, f"{key}.{k}", seen)
            elif isinstance(node, list):
                for x in node:
                    walk(x, f"{key}[]", seen)

        for line in path.read_text(encoding="utf-8").splitlines():
            drug = json.loads(line)
            walk(drug, "drug", {id(src) for _, src, *_ in iter_drug_sources(drug)})
        self.assertEqual(missed, set())

    def test_grade_family_grades_what_the_quote_family_gates(self):
        """Enzyme and formed_by rows were quote-gated but never graded: a bad grade
        there now fails family 4 too."""
        bad = {"corpus": "nosuch", "page": 1, "quote": "x", "provenance": "bogus"}
        drug = {"id": "d", "enzymes": [{"enzyme": "CYP2D6", "sources": [bad]}],
                "metabolites": [{"id": "m", "formed_by": [{"enzyme": "CYP3A4",
                                                            "sources": [bad]}]}]}
        sites = [ctx for ctx, *_ in iter_drug_sources(drug)]
        self.assertEqual(sites, ["drug d enzyme CYP2D6 sources[0]",
                                 "drug d metabolite m formed_by CYP3A4 sources[0]"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            check_provenance(Report(), {}, [], [], [], [], [],
                                        [drug], [])
        self.assertEqual(sum("'bogus'" in ln for ln in buf.getvalue().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()


class ProjectionClaimGateTest(unittest.TestCase):
    """A pathway sub-claim may only cite a quote that names what it is cited for.

    The transmitter / sign claims cite a SUBSET of the arrow's own sources, so the
    verbatim gate alone would pass anything: it is the SELECTION that can be wrong (a
    hand-edit, or a claims block left behind by an older generator run). Family 5
    re-derives it with the same closed vocabulary the generator graded it with, so these
    tests pin both failure shapes: a source on a claim its quote is silent about, and a
    grade above the base one with no source at all.
    """

    META = {
        "source_corpora": {"kandel": {"ref": "Kandel"}},
        "quote_pipelines": {"page_llm_judged": ["raw", "extract_llm", "judge_llm",
                                                "neurarium"]},
        "kind_signs": {"excitatory": "excitatory", "histaminergic": "modulatory"},
    }

    def _run(self, claims, kind="excitatory"):
        src = {"corpus": "kandel", "page": 1, "quote": "The cortex projects to the "
               "putamen.", "provenance": "verified", "pipeline": "page_llm_judged"}
        proj = {"from": "frontal_R", "to": "putamen_R", "kind": kind,
                "neurotransmitter": "Glutamate", "sources": [src],
                "claims": {k: (dict(v, sources=[src]) if v.pop("cite", False) else v)
                           for k, v in claims.items()}}
        report = Report()
        buf = io.StringIO()
        with redirect_stdout(buf):
            check_sources(report, self.META, [], [proj], [], [], [])
        return report, buf.getvalue()

    def test_a_claim_citing_a_quote_that_does_not_name_it_fails(self):
        report, out = self._run({"transmitter": {"grade": "verified", "cite": True}})
        self.assertTrue(report.errors)
        self.assertIn("does not name the transmitter", out)

    def test_an_unattested_claim_graded_above_the_base_fails(self):
        report, out = self._run({"sign": {"grade": "verified"}})
        self.assertTrue(report.errors)
        self.assertIn("with no source", out)

    def test_an_honest_claim_passes(self):
        report, _out = self._run({"transmitter": {"grade": "llm"},
                                  "sign": {"grade": "llm"}})
        self.assertFalse(report.errors)

    def test_a_claim_whose_value_has_no_word_test_fails(self):
        # A modulatory kind makes no sign claim, so a sign node on one is a claim
        # nobody made: there is no vocabulary that could ever have attested it.
        report, out = self._run({"sign": {"grade": "verified", "cite": True}},
                                kind="histaminergic")
        self.assertTrue(report.errors)
        self.assertIn("has no word test", out)


    def test_the_gate_covers_an_enzyme_row_too(self):
        """The same helper gates the metabolism tier (drug_enzyme_strength)."""
        src = {"corpus": "kandel", "page": 1, "quote": "Cleared by CYP3A4.",
               "provenance": "verified", "pipeline": "page_llm_judged"}
        drug = {"id": "d", "name": "D", "enzymes": [{
            "enzyme": "cyp3a4", "role": "substrate", "strength": "major",
            "sources": [src],
            "claims": {"strength": {"grade": "verified", "sources": [src]}}}]}
        report = Report()
        buf = io.StringIO()
        with redirect_stdout(buf):
            check_sources(report, self.META, [drug], [], [], [], [])
        self.assertTrue(report.errors)
        self.assertIn("does not name the strength", buf.getvalue())


class SectionAddonAnchorTest(unittest.TestCase):
    """An addon anchored on a browse SECTION rather than on a node (family 2).

    A section is the one owner kind with no node behind it, so the usual "does the
    anchored node exist" question is asked against the emitted section vocabulary
    instead. That makes the vocabulary load-bearing: a section key nothing registers
    is an addon that ships, is graded, is counted, and is never drawn, which is the
    silent loss the whole addon check exists to prevent.
    """

    META = {
        "addon_slots": {"section.projections": "section"},
        "addon_displays": ["admonition"],
        "addon_tones": {"info": "i"},
        "addon_sections": {"projections": "Projections"},
        "drug_targets": {},
    }

    def _run(self, **patch):
        addon = {"id": "a", "owner_kind": "section", "owner": "projections",
                 "slot": "section.projections", "display": "admonition",
                 "tone": "info", "text": "Both sides are our assumption."}
        addon.update(patch)
        report = Report()
        buf = io.StringIO()
        with redirect_stdout(buf):
            check_reachability(report, self.META, [], [], [], [], [], [],
                                          [addon])
        return report, buf.getvalue()

    def test_a_registered_section_anchor_passes(self):
        report, _out = self._run()
        self.assertFalse(report.errors)

    def test_an_unregistered_section_anchor_fails(self):
        report, out = self._run(owner="circuits")
        self.assertTrue(report.errors)
        self.assertIn("not a known section id", out)


class BindingDupTest(unittest.TestCase):
    """3.98.0 collapsed amphetamine's DAT reuptake_inhibitor + releaser pair onto two
    releaser rows; family 1 must catch a (target, action) listed twice."""

    def _errors(self, drugs):
        report = Report()
        with redirect_stdout(io.StringIO()):
            check_binding_dups(report, drugs)
        return report.errors

    def test_collapsed_pair_is_an_error(self):
        drug = {"id": "x", "bindings": [{"target": "dat", "action": "releaser"},
                                        {"target": "dat", "action": "releaser"}]}
        self.assertTrue(self._errors([drug]))

    def test_dual_mechanism_is_fine(self):
        drug = {"id": "x", "bindings": [{"target": "dat", "action": "reuptake_inhibitor"},
                                        {"target": "dat", "action": "releaser"}]}
        self.assertFalse(self._errors([drug]))


class NodeIdShapeTest(unittest.TestCase):
    """An id becomes a file name under /api/, so a path-like id is a hard error."""

    def _errors(self, ids):
        report = Report(verbose=True)
        with redirect_stdout(io.StringIO()):
            check_id_collection(report, "drugs", [{"id": i, "name": i} for i in ids])
        return report.errors

    def test_plain_ids_pass(self):
        self.assertEqual(self._errors(["sertraline", "putamen_R", "amphetamine_dl"]), 0)

    def test_path_like_id_is_an_error(self):
        self.assertEqual(self._errors(["../x"]), 1)
        self.assertEqual(self._errors(["a/b"]), 1)
