"""NbN labels must not drift into near-duplicates.

Each drug's ``nbn`` is copied from its own Stahl monograph, and Stahl is not consistent
with itself: pregabalin's line drops the comma gabapentin's keeps, amoxapine names the
SN-RI transmitters in the other order. Any viewer that groups by label (the drug map's
"Nomenclature" colouring, its legend) then shows one class twice. So two labels with
the same words, ignoring order, case and punctuation, are one label written two ways,
and an English label must always carry the same French one. The quote under the label
stays verbatim; only the label is canonical.

Built with the help of Claude Code.
"""
import re
import sys
import unittest
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import drugs_io  # noqa: E402


# Filler words a rephrasing adds or drops ("dopamine and norepinephrine ..." vs
# "dopamine, norepinephrine ..."), in both languages.
FILLER = {"and", "of", "the", "et", "de", "la", "le", "les", "du", "des", "d", "l"}


def word_key(label: str) -> tuple:
    """Content words of a label, lowercased and sorted: the same key for any
    reordering, punctuation or filler-word change ("glutamate (Glu); yet to be
    determined" vs "glutamate; yet to be determined (Glu)")."""
    return tuple(sorted(w for w in re.findall(r"\w+", label.lower()) if w not in FILLER))


class NbnLabelTest(unittest.TestCase):
    def setUp(self):
        self.labels = [(d["id"], d["nbn"]) for d in drugs_io.load_drugs() if d.get("nbn")]

    def test_no_near_duplicate_labels(self):
        for lang in ("en", "fr"):
            by_key = defaultdict(set)
            for _, nbn in self.labels:
                by_key[word_key(nbn[lang])].add(nbn[lang])
            dupes = [sorted(v) for v in by_key.values() if len(v) > 1]
            self.assertEqual(dupes, [], f"{lang} NbN labels written two ways")

    def test_one_french_label_per_english_label(self):
        fr_of = defaultdict(set)
        for _, nbn in self.labels:
            fr_of[nbn["en"]].add(nbn["fr"])
        split = {en: sorted(fr) for en, fr in fr_of.items() if len(fr) > 1}
        self.assertEqual(split, {}, "one English NbN translated two ways")


if __name__ == "__main__":
    unittest.main()
