#!/usr/bin/env python
"""When the "What's new" notes open, and what they must not stack on.

Release notes are about the build, not about the scene, so they open the moment the
visitor clicks through the loading overlay. They used to ride the guided tour's gate,
which waits for the assemble animation to settle, so a returning visitor read them
several seconds late (and never at all on a load where the intro was cancelled).

There is no DOM harness for `js/main.js`'s boot wiring, so this is a structural lint in
the style of test_search_controls.py / test_theme_tokens.py: it pins WHERE the trigger
sits rather than what it renders, which is exactly what regressed. The behaviour itself
was verified in a real browser (the popup opens ~120ms after the click, the tour waits
for it to close).

Stdlib ``unittest`` only. Runnable directly:

    python tools/tests/test_changelog_launch.py

Built with the help of Claude Code.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MAIN_JS = REPO_ROOT / "public" / "js" / "main.js"


def _function_body(source: str, header: str) -> str:
    """Return the braced body that follows ``header``, by brace matching.

    ``header`` is matched literally and must end at the body's opening ``{``; nesting is
    counted so an inner block does not end the body early. Good enough for this file
    (no braces inside strings or regex literals in the spans it is used on).
    """
    start = source.index(header) + len(header)
    depth, i = 0, start
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i]
        i += 1
    raise AssertionError(f"unbalanced braces after {header!r}")


class ChangelogLaunchTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.js = MAIN_JS.read_text(encoding="utf-8")

    def test_the_notes_open_from_the_overlay_click(self):
        # waitForStart() resolves on the "Start exploring" click, so a trigger inside
        # its `.then` is what "right away" means; anything further down the launch is
        # gated on an animation.
        body = _function_body(self.js, "loading.waitForStart().then(() => {")
        self.assertIn("showChangelogOnce()", body)

    def test_the_notes_do_not_ride_the_scene_settle_gate(self):
        # tryAutoTour only runs once the assemble intro has settled, which is precisely
        # the wait this fix removed.
        body = _function_body(self.js, "const tryAutoTour = () => {")
        self.assertNotIn("changelog", body)

    def test_the_trigger_is_one_shot_and_fires_from_one_place(self):
        self.assertEqual(len(re.findall(r"\bshowIfUnseen\(\)", self.js)), 1)
        self.assertEqual(len(re.findall(r"\bshowChangelogOnce\(\)", self.js)), 1)

    def test_the_tour_gates_on_the_notes_popup(self):
        # The two open from different events now, so the tour must decline to stack on
        # an open changelog the way it already declines to stack on the Sources popup.
        gates = re.search(r"const tourGateEls = \[([^\]]*)\]", self.js)
        self.assertIsNotNone(gates, "tourGateEls is gone: has the gate been rewritten?")
        self.assertIn('"changelog-modal"', gates.group(1))
        self.assertIn('"sourcing-modal"', gates.group(1))


if __name__ == "__main__":
    unittest.main()
