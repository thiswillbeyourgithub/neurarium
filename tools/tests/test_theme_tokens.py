#!/usr/bin/env python
"""The day theme must not be able to inherit a colour picked for the night one.

Both themes are one token block (see CLAUDE.md "Theme"): `:root` defines the dark
palette and `:root[data-theme="light"]` redefines only tokens. The failure mode that
rule does not catch on its own is a rule written with a *literal* colour: it looks
right on the dark panel it was authored against, ships, and is light-on-light the day
a visitor clicks the sun. That is exactly how the graded source pills came to measure
1.7:1 in the day theme while reading perfectly at night.

So this test asserts the two halves of the convention mechanically: every token the
dark block declares has a day-theme counterpart, and no rule paints text with a
literal colour unless the ground under it is fixed in BOTH themes (the allow-list
below names each one and why).

Built with the help of Claude Code.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX = os.path.join(ROOT, "public", "index.html")

# Tokens that are deliberately not a colour, so the day theme has nothing to say
# about them.
THEME_FREE = {"--panel-w"}

# A literal `color:` is honest only where the ground under it does not flip with the
# theme. Each entry is the value plus the reason it is allowed to stay literal.
LITERAL_INK_OK = {
    "#fff": "white on var(--accent); the accent is purple in both themes",
    "#06131f": "dark ink on var(--accent), same reason",
    "#000": "--label-color, a floating-label knob set per label, not a rule",
    "#f2f3f5": "the lightbox close button, over a near-black image backdrop",
    "#ffe3e5": "the error banner, over its own opaque dark red",
    "currentcolor": "inherits, so it is themed by whatever set it",
    "inherit": "inherits, so it is themed by whatever set it",
    "transparent": "no ink at all",
}


def stylesheet():
    """The page's own `<style>` block, without the `<noscript>` inline styles."""
    with open(INDEX, encoding="utf-8") as fh:
        src = fh.read()
    blocks = re.findall(r"<style[^>]*>(.*?)</style>", src, re.S)
    assert blocks, "index.html has no <style> block"
    return "\n".join(blocks)


def _block(css, selector):
    """The declarations inside the first rule with exactly this selector."""
    i = css.index(selector + " {")
    return css[i:css.index("\n      }", i)]


def _tokens(text):
    return set(re.findall(r"^\s*(--[a-z0-9-]+)\s*:", text, re.M))


class EveryTokenIsThemedTest(unittest.TestCase):

    def setUp(self):
        self.css = stylesheet()

    def test_the_day_theme_redefines_every_colour_token(self):
        dark = _tokens(_block(self.css, ":root")) - THEME_FREE
        light = _tokens(_block(self.css, ':root[data-theme="light"]'))
        self.assertEqual(dark - light, set(),
                         "declared for the night theme only, so the day theme "
                         "inherits a colour picked to glow on near-black")

    def test_the_day_theme_invents_no_token_of_its_own(self):
        # A token only the light block declares resolves to nothing at night, which
        # fails silently (the property is simply dropped).
        dark = _tokens(_block(self.css, ":root"))
        light = _tokens(_block(self.css, ':root[data-theme="light"]'))
        self.assertEqual(light - dark, set())


class NoLiteralInkTest(unittest.TestCase):

    def test_text_colour_comes_from_a_token(self):
        offenders = []
        for line in stylesheet().split("\n"):
            for val in re.findall(r"(?<![-\w])color:\s*([^;]+);", line):
                val = val.strip().lower()
                if val.startswith("var(") or val.startswith("rgba(var("):
                    continue
                if val in LITERAL_INK_OK:
                    continue
                offenders.append(line.strip())
        self.assertEqual(offenders, [],
                         "a literal text colour: it will be wrong in one of the two "
                         "themes unless its ground is fixed in both, in which case "
                         "add it to LITERAL_INK_OK with the reason")


if __name__ == "__main__":
    unittest.main(verbosity=2)
