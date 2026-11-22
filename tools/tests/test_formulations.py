#!/usr/bin/env python
"""Unit tests for the drug formulation sub-nodes (vocabulary, classifiers, emitter).

Stdlib ``unittest`` only, offline::

    python -m unittest discover -t tools/tests -s tools/tests -p test_formulations.py

Built with the help of Claude Code.
"""

import doctest
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from data_generators import formulations as F  # noqa: E402

SRC = {"corpus": "stahl", "page": 709, "quote": "Seroquel XR", "provenance": "verified",
       "extraction": "code"}


def _drug(**kw):
    return {"id": "quetiapine", **kw}


class ClassifyTest(unittest.TestCase):
    def test_doctests(self):
        self.assertEqual(doctest.testmod(F).failed, 0)

    def test_abbreviations_are_case_sensitive(self):
        # French prose is full of "La" / "la": never Ritalin LA's extended release.
        self.assertIsNone(F.classify("La résorption du loprazolam est rapide"))
        self.assertEqual(F.classify("Ritalin LA"), "xr")

    def test_precedence(self):
        self.assertEqual(F.classify("Cotempla XR-ODT"), "xr")
        self.assertEqual(F.classify("risperidone long-acting injectable"), "depot")
        self.assertEqual(F.classify("pipotiazine palmitate intramuscular injection"), "depot")

    def test_modified_release_is_not_read(self):
        # "modified release" covers delayed AND extended: reading either is a guess.
        self.assertIsNone(F.classify("a modified-release tablet"))

    def test_attests(self):
        q = "IR : 2–3 hours CR : 4.5 hours"
        self.assertTrue(F.attests("ir", q))
        self.assertTrue(F.attests("xr", q))
        self.assertFalse(F.attests("depot", q))

    def test_denomination_needs_an_oral_only_route_for_ir(self):
        self.assertIsNone(F.classify_denomination("X 10 mg, comprimé", "orale;rectale"))
        self.assertEqual(F.classify_denomination("X 10 mg, comprimé", "orale"), "ir")
        # Methylphenidate's "QUASYM L.P." (dotted LP) once read as immediate release:
        # "gélule" alone made it ir. A modified release is never ir.
        self.assertEqual(F.classify_denomination(
            "QUASYM L.P. 30 mg, gélule à libération modifiée", "orale"), "xr")
        self.assertIsNone(F.classify_denomination("X 30 mg, gélule à libération modifiée", "orale"))
        self.assertIsNone(F.classify_label_title("X CAPSULE, MODIFIED RELEASE [Y]"))

    def test_label_route_overrides_a_bare_tablet(self):
        # Generic Saphris: the SPL title says "TABLET", its route code says sublingual.
        # Read as IR, its 1 h peak was published as a swallowed tablet's (3.114.0).
        title = "ASENAPINE TABLET [ALEMBIC PHARMACEUTICALS INC.]"
        self.assertEqual(F.classify_label_title(title, {"SUBLINGUAL"}), "sublingual")
        self.assertEqual(F.classify_label_title(title, {"ORAL"}), "ir")
        self.assertIsNone(F.classify_label_title(title, {"ORAL", "SUBLINGUAL"}))

    def test_extended_established_name_is_xr(self):
        # "Extended Phenytoin Sodium Capsules" (Dilantin Kapseals' generic): its
        # 4-12 h peak is the extended capsule's, never an IR one.
        self.assertEqual(F.classify_label_title(
            "EXTENDED PHENYTOIN SODIUM (PHENYTOIN SODIUM) CAPSULE [REMEDYREPACK INC.]",
            {"ORAL"}), "xr")

    def test_kit_title_is_never_classified(self):
        self.assertIsNone(F.classify_label_title(
            "AUSTEDO (DEUTETRABENAZINE) TABLET KIT AUSTEDO XR TABLET, EXTENDED RELEASE"))


class EmitTest(unittest.TestCase):
    def test_emits_in_display_order(self):
        out = F.drug_formulations(_drug(formulations=[
            {"release": "xr", "release_sources": [SRC],
             "brands": [{"name": "Seroquel XR", "region": "na", "sources": [SRC]}]},
            {"release": "ir", "release_sources": [SRC], "tmax": {"hours": 1.5},
             "tmax_sources": [dict(SRC, quote="peak 1.5 h")]}]))
        self.assertEqual([f["release"] for f in out["formulations"]], ["ir", "xr"])
        self.assertEqual(out["formulations"][0]["tmax"], {"hours": 1.5})

    def test_rejects(self):
        cases = [
            {"release": "slow", "release_sources": [SRC], "tmax": {"hours": 1}},
            {"release": "xr", "tmax": {"hours": 1}},                       # no source
            {"release": "xr", "release_sources": [SRC]},                   # no claim
        ]
        for row in cases:
            with self.subTest(row=row), self.assertRaises((KeyError, ValueError)):
                F.drug_formulations(_drug(formulations=[row]))
        with self.assertRaises(ValueError):                                # twice
            F.drug_formulations(_drug(formulations=[
                {"release": "xr", "release_sources": [SRC], "tmax": {"hours": 1}}] * 2))

    def test_claim_left_at_molecule_level_too_fails(self):
        # An applier re-ran after apply_formulations: the build refuses the duplicate.
        tq = dict(SRC, quote="peak 6 h")
        with self.assertRaises(ValueError):
            F.drug_formulations(_drug(
                tmax={"hours": 6}, tmax_sources=[tq],
                formulations=[{"release": "xr", "release_sources": [SRC],
                               "tmax": {"hours": 6}, "tmax_sources": [tq]}]))
        with self.assertRaises(ValueError):
            F.drug_formulations(_drug(
                brands=[{"name": "Seroquel XR", "region": "na", "sources": [SRC]}],
                formulations=[{"release": "xr", "release_sources": [SRC],
                               "brands": [{"name": "Seroquel XR", "region": "na",
                                           "sources": [SRC]}]}]))


if __name__ == "__main__":
    unittest.main()
