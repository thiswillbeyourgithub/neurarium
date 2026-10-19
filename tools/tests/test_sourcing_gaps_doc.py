#!/usr/bin/env python
"""docs/SOURCING_GAPS.md lists the current gaps only, so it cannot rot.

The doc once grew into dated snapshots, finished plans and hand-typed counts that
went stale the day after they were written. Its contract (stated at its top) is:
every figure lives in the generated ``SOURCING_GAPS`` block that
``tools/update_readme_stats.py`` rewrites (freshness is checked by
``test_generated_artifacts_fresh``), and the hand-written prose carries no date, no
history heading and no number. Inline code, fenced code and the generated block are
exempt, as are identifiers that merely contain digits (``CYP2D6``, ``5-HT1E``,
corpus ``#9``). Built with the help of Claude Code.
"""

import re
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from update_readme_stats import GAPS_DOC, GAPS_END, GAPS_START  # noqa: E402

DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
HISTORY_HEADING = re.compile(
    r"^#+ .*\b(snapshot|plan|audit|complete|completed|done|status|surveyed|shipped|"
    r"closed|history)\b", re.IGNORECASE | re.MULTILINE)
# A bare number: not part of an identifier (CYP2D6, M1-M5, 5-HT1E, CYP3A4\*22), not a
# corpus number (#9). Everything else is a count, a year or a page that can rot.
NUMBER = re.compile(r"(?<![\w#*\\/.-])\d+(?:[.,]\d+)?(?!\w)(?!-\w)")
FENCE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
INLINE_CODE = re.compile(r"`[^`\n]*`")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def hand_written(text: str) -> str:
    """The doc minus everything a test must not hold it to: the generated block,
    fenced and inline code, and HTML comments."""
    if GAPS_START in text and GAPS_END in text:
        pre, rest = text.split(GAPS_START, 1)
        text = pre + rest.split(GAPS_END, 1)[1]
    for pattern in (FENCE, INLINE_CODE, COMMENT):
        text = pattern.sub(" ", text)
    return text


def violations(text: str) -> list[str]:
    """Every line of hand-written prose breaking the contract, with the reason."""
    prose = hand_written(text)
    found = [f"dated: {m.group()}" for m in DATE.finditer(prose)]
    found += [f"history heading: {m.group().strip()}" for m in HISTORY_HEADING.finditer(prose)]
    for line in prose.splitlines():
        numbers = NUMBER.findall(line)
        if numbers:
            found.append(f"hand-typed number(s) {numbers}: {line.strip()[:120]}")
    return found


class SourcingGapsDocTest(unittest.TestCase):
    def setUp(self):
        self.text = GAPS_DOC.read_text(encoding="utf-8")

    def test_has_generated_block(self):
        self.assertIn(GAPS_START, self.text)
        self.assertIn(GAPS_END, self.text)

    def test_states_its_contract(self):
        self.assertIn("**Contract: this file lists the current gaps only.**", self.text)

    def test_prose_cannot_rot(self):
        found = violations(self.text)
        self.assertFalse(found, "docs/SOURCING_GAPS.md breaks its contract (move the "
                                "figure into the generated block, or drop the history):\n"
                                + "\n".join(found))

    def test_guard_catches_each_shape(self):
        # The guard itself: each rotting shape is caught, each identifier is not.
        for bad in ("## Snapshot (2026-07-27)\n", "### Phase 2 plan\n",
                    "## Kinds now closed\n", "13 drugs lack a class.\n"):
            self.assertTrue(violations(bad), bad)
        for fine in ("CYP2D6, 5-HT1E, M1-M5, α1A/B/D, corpus #9, CYP3A4\\*22.\n",
                     "Run `fetch_ki.py --top 3`.\n", GAPS_START + "\n| a | 12 |\n" + GAPS_END):
            self.assertFalse(violations(fine), fine)


if __name__ == "__main__":
    unittest.main()
