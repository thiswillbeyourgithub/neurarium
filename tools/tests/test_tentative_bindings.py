"""A binding shown "speculative" (``tentative: true``) must be hedged by its own source.

The flag is hand-authored, so it drifted: twelve Wikipedia bindings stated flatly ("showed
weak antagonistic activity at ...") were marked speculative because the sentence said
"weak", which is a potency, not a doubt. This pins the rule: a tentative binding that
cites quotes needs at least one quote carrying a hedge word, unless :data:`EXEMPT` says
why the doubt lies elsewhere. A binding with no quote (an ``llm`` grade) is not checked.

Run: ``python -m unittest discover -s tools/tests -t tools/tests -p test_tentative_bindings.py``
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "public" / "data"

HEDGE = re.compile(r"\b(may|might|could|perhaps|possibl[ey]|potentially|theoretical(ly)?|"
                   r"hypothetical(ly)?|unknown|suggest\w*|presumabl[ey]|unclear)\b", re.I)

# (drug, target) -> why the binding is speculative though its quote states it flatly.
EXEMPT = {
    ("acamprosate", "mglur1"): "Stahl names metabotropic glutamate receptors generically; the mGluR1 subtype is inferred",
}


def _quotes() -> dict[str, str]:
    with open(DATA / "quotes.jsonl", encoding="utf-8") as f:
        return {q["id"]: q["quote"] for q in map(json.loads, f)}


class TentativeBindingTest(unittest.TestCase):
    def test_speculative_binding_is_hedged_by_its_source(self):
        quotes = _quotes()
        bad = []
        with open(DATA / "drugs.jsonl", encoding="utf-8") as f:
            for drug in map(json.loads, f):
                for b in drug.get("bindings", []):
                    if not b.get("tentative") or (drug["id"], b["target"]) in EXEMPT:
                        continue
                    texts = [quotes[s["quote_id"]] for s in b.get("sources", [])
                             if s.get("quote_id") in quotes]
                    if texts and not any(HEDGE.search(t) for t in texts):
                        bad.append(f"{drug['id']} {b['target']}: {texts[0][:120]}")
        self.assertEqual(bad, [], "tentative but stated flatly by its source")

    def test_exemptions_are_still_tentative(self):
        """An exemption whose binding lost its flag (or vanished) is stale."""
        live = set()
        with open(DATA / "drugs.jsonl", encoding="utf-8") as f:
            for drug in map(json.loads, f):
                live |= {(drug["id"], b["target"]) for b in drug.get("bindings", [])
                         if b.get("tentative")}
        self.assertEqual(set(EXEMPT) - live, set())


if __name__ == "__main__":
    unittest.main()
