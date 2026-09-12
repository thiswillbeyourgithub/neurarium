#!/usr/bin/env python
"""The `data-search` contract between index.html and the search index in main.js.

The panel's controls are searchable because the markup marks them, not because a list
in JS names them. That is what keeps a new option findable the day it lands, and it is
also the part nothing else can check: a marked control that cannot be named produces a
blank result row, and marking the search box itself produces a result that reopens the
search you are already in. Neither crashes, so neither shows up anywhere but here.

Stdlib only, no browser. Built with the help of Claude Code.
"""
import re
import sys
import unicodedata
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_i18n import catalogues  # noqa: E402  the one parser of js/i18n.js

ROOT = Path(__file__).resolve().parent.parent.parent
HTML = ROOT / "public" / "index.html"
MAIN = ROOT / "public" / "js" / "main.js"
HTML_TEXT = HTML.read_text(encoding="utf-8")

# Every element carrying the mark. A void <input> has no inner content; a <button> or
# <a> carries its own name inside it, which is exactly the half an opening-tag-only
# match would miss (a browse-section header is `<button ...><span data-i18n=...>`).
TAG = re.compile(r"<(?:button|input|a)\b[^>]*\bdata-search\b[^>]*>", re.S)
CLOSE = re.compile(r"</(?:button|a)>", re.S)
ID = re.compile(r'\bid="([^"]+)"')
ALIAS = re.compile(r'\bdata-search="([^"]*)"')


def fold(s):
    """The half of js/main.js `foldText` an alias list is subject to: decompose,
    drop the combining marks, lowercase. The matcher folds both sides of its
    comparison through that, so "guidee" and "guidée" reach the same control and
    spelling both is dead weight rather than a second way in.
    """
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if not unicodedata.combining(c))


def marked():
    """``[(opening tag, id, alias list or None, inner html, offset)]``, in order.

    The offset is where the opening tag starts, carried along because the match
    already knows it: recovering it later by searching for the tag's own text would
    be a second, weaker notion of where a control sits (two identical tags resolve to
    the same place).
    """
    out = []
    for m in TAG.finditer(HTML_TEXT):
        tag = m.group(0)
        end = CLOSE.search(HTML_TEXT, m.end())
        inner = "" if tag.startswith("<input") else HTML_TEXT[m.end():end.start() if end else m.end()]
        alias = ALIAS.search(tag)
        out.append((tag, (ID.search(tag) or [None, None])[1],
                    alias.group(1) if alias else None, inner, m.start()))
    return out


class MarkupTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rows = marked()

    def test_the_panel_marks_some_controls(self):
        self.assertGreater(len(self.rows), 10)

    def test_the_search_box_is_not_searchable(self):
        # A result that opens the search you are already inside is a loop, and it is
        # the one exclusion the feature was specified with.
        for tag, eid, _, _, _ in self.rows:
            self.assertNotEqual(eid, "search-toggle", tag)

    def test_every_marked_control_can_be_named(self):
        # main.js names a checkbox by the <label> wrapping it and anything else by its
        # own title / aria-label / text. A control with none of those indexes as an
        # empty row, which reads as a bug in the results list rather than as a missing
        # attribute in the markup.
        for tag, eid, _, inner, start in self.rows:
            if 'type="checkbox"' in tag:
                # The wrapping <label> is what carries the words; find the opening tag
                # before this input and require it to be one.
                before = HTML_TEXT[:start]
                self.assertRegex(
                    before[-400:],
                    re.compile(r"<label\b[^>]*>(?:(?!</label>).)*$", re.S),
                    f"{eid}: a marked checkbox with no wrapping <label>")
            else:
                # Named by an attribute (an icon button's title), by an i18n key
                # filled into its own text, or by a child that carries one.
                nameable = ("title:" in tag or "aria-label" in tag
                            or "data-i18n" in tag or "data-i18n" in inner
                            or inner.strip())
                self.assertTrue(nameable, f"{eid}: a marked control with no title, "
                                          f"aria-label or text to name it by")

    def test_every_marked_control_has_an_id(self):
        # Not required by the code, but a control worth searching for is a control
        # worth naming in a bug report, in the tour, and in a deep link.
        for tag, eid, _, _, _ in self.rows:
            self.assertIsNotNone(eid, tag)

    def test_an_alias_list_is_words_not_markup(self):
        for tag, eid, alias, _, _ in self.rows:
            if alias is None:
                continue
            self.assertTrue(alias.strip(), f"{eid}: an empty alias list")
            self.assertNotIn("<", alias, f"{eid}: markup in an alias list")

    def test_an_alias_is_spelled_once(self):
        # An alias is a way IN to a name the panel already shows, so two spellings
        # the matcher cannot tell apart are not two ways in. Accents fold away on
        # both sides, so the unaccented twin of an accented alias buys nothing, and
        # a word repeated outright is just a slip. Both shipped once.
        for _, eid, alias, _, _ in self.rows:
            if alias is None:
                continue
            seen = {}
            for word in alias.split():
                key = fold(word)
                self.assertNotIn(key, seen, f"{eid}: {word!r} is {seen.get(key)!r} "
                                            f"again once folded")
                seen[key] = word


class WiringTest(unittest.TestCase):
    """The three ends that have to agree: the query, the chip, the strings."""

    def test_main_js_builds_the_index_from_the_attribute(self):
        js = MAIN.read_text(encoding="utf-8")
        self.assertIn('querySelectorAll("[data-search]")', js,
                      "the search index no longer reads the markup, so the attribute "
                      "is decoration and a new marked control does nothing")
        self.assertIn('command: "search.filterCommands"', js,
                      "the command rows have no type-filter chip, so they cannot be "
                      "scoped to and drown in a common query")

    def test_the_new_strings_are_in_the_catalogue(self):
        # Only the EN side is asserted here: test_i18n's CatalogueParityTest already
        # owns "every key is translated", so counting both would be a second, weaker
        # copy of that rule (and a naive count disagrees with the real parser on a
        # multi-line entry).
        en, _ = catalogues()
        for key in ("search.filterCommands", "search.on", "search.off"):
            self.assertIn(key, en, f"{key} is missing from the catalogue")


if __name__ == "__main__":
    unittest.main(verbosity=2)
