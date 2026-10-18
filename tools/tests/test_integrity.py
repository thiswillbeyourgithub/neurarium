#!/usr/bin/env python
"""Unit tests for the authored-table typo guards (``data_generators.integrity``).

Each guard must pass on the committed tables and raise once a key names nothing::

    python -m unittest discover -t tools/tests -s tools/tests -p test_integrity.py

Built with the help of Claude Code.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_generators import integrity as I  # noqa: E402


class IntegrityTest(unittest.TestCase):
    def test_committed_tables_pass(self):
        I.validate_quote_registries()
        I.validate_drug_targets()
        I.validate_tone_rules()
        I.validate_genes()
        I.validate_structure_aliases()
        I.validate_translations(set())

    def test_typo_projection_quote_key_raises(self):
        with mock.patch.dict(I.PROJECTION_QUOTES, {("nowhere", "elsewhere"): []}):
            with self.assertRaisesRegex(KeyError, "PROJECTION_QUOTES keys match no"):
                I.validate_quote_registries()

    def test_typo_drug_target_region_raises(self):
        spec = dict(next(iter(I.DRUG_TARGETS.values())), regions=["not_a_base"])
        with mock.patch.dict(I.DRUG_TARGETS, {"fake_target": spec}):
            with self.assertRaisesRegex(KeyError, "region 'not_a_base'"):
                I.validate_drug_targets()

    def test_unknown_addon_owner_raises(self):
        addon = {"id": "a", "owner_kind": "drug", "owner": "nodrug"}
        with self.assertRaisesRegex(KeyError, "not a known drug id"):
            I.validate_addon_owners([addon], drug_ids={"x"}, receptor_ids=set(),
                                    target_ids=set())

    def test_orphan_metabolite_enzyme_quote_raises(self):
        with mock.patch.dict(I.METABOLITE_ENZYME_QUOTES, {("d", "m"): []}):
            with self.assertRaisesRegex(KeyError, "d/m"):
                I.validate_metabolite_enzyme_quotes(set(I.METABOLITE_ENZYME_QUOTES) - {("d", "m")})


if __name__ == "__main__":
    unittest.main()
