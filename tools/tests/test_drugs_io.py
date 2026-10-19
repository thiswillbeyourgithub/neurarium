"""Unit tests for ``tools/lib/drugs_io.save_drugs``: a re-run that changes nothing is byte-stable.

Every applier that owns a field pops it and re-adds it, which moves the key to the end
of the record: ``apply_drug_history`` rewrote 202 lines, ``apply_drug_holders`` 90 and
``apply_originator`` 2 on a re-run that changed no value. ``save_drugs`` now keeps the
on-disk key order of every record the file already holds.

Built with the help of Claude Code.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import drugs_io  # noqa: E402


class KeyOrderTest(unittest.TestCase):

    def test_a_popped_and_readded_field_keeps_its_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "drugs_data.jsonl"
            drugs_io.save_drugs([{"id": "a", "holders": [1], "name": "A"}], path)
            before = path.read_bytes()
            (drug,) = drugs_io.load_drugs(path)
            drug.pop("holders")
            drug["holders"] = [1]
            drug["new"] = True
            drugs_io.save_drugs([drug], path)
            self.assertEqual(list(drugs_io.load_drugs(path)[0]), ["id", "holders", "name", "new"])
            del drug["new"]
            drugs_io.save_drugs([drug], path)
            self.assertEqual(path.read_bytes(), before)

    def test_a_new_record_keeps_its_built_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "drugs_data.jsonl"
            drugs_io.save_drugs([{"name": "B", "id": "b"}], path)
            self.assertEqual(list(drugs_io.load_drugs(path)[0]), ["name", "id"])


if __name__ == "__main__":
    unittest.main()
