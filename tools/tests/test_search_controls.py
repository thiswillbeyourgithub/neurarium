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
from html.parser import HTMLParser
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
    """The half of js/main.js `foldText` an alias list is subject to: decompose, drop
    the combining marks, lowercase, then drop hyphens and Unicode dashes. The matcher
    folds both sides of its comparison through that, so "guidee" and "guidée" reach the
    same control, and so do "night-mode" and "nightmode": spelling both is dead weight
    rather than a second way in.

    `foldText`'s remaining step, the Greek letter -> Latin name map, is deliberately
    not mirrored. It is there so a receptor name written with a glyph is reachable from
    a keyboard; an alias list is keyboard words already, so no alias can carry the
    glyph it would fold. Mirroring it would be a second copy of a table to keep in step
    for a case that cannot arise.
    """
    folded = "".join(c for c in unicodedata.normalize("NFD", s.lower())
                     if not unicodedata.combining(c))
    return re.sub(r"[-‐-―]", "", folded)


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


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}


class _Node:
    """One element: its tag, its attributes, its parent, its children in order."""

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.kids = tag, dict(attrs), parent, []

    def hidden_ancestor(self):
        """The nearest enclosing element carrying `hidden`, or None."""
        node = self.parent
        while node is not None:
            if "hidden" in node.attrs:
                return node
            node = node.parent
        return None

    def previous_sibling(self):
        sibs = self.parent.kids if self.parent else []
        i = sibs.index(self)
        return sibs[i - 1] if i else None


class _Tree(HTMLParser):
    """Enough of a DOM to ask "what encloses this, and what sits just before it".

    The other tests here read the markup with regexes, which is all a single tag
    needs; this one is about where a control *sits*, and nesting is exactly what a
    regex cannot see. An unmatched end tag pops to its own opening rather than
    unbalancing everything after it.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", [], None)
        self.stack = [self.root]

    def _open(self, tag, attrs):
        node = _Node(tag, attrs, self.stack[-1])
        self.stack[-1].kids.append(node)
        return node

    def handle_starttag(self, tag, attrs):
        node = self._open(tag, attrs)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def walk(self, node=None):
        node = self.root if node is None else node
        yield node
        for kid in node.kids:
            yield from self.walk(kid)


class MarkupTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rows = marked()
        cls.tree = _Tree()
        cls.tree.feed(HTML_TEXT)

    def test_the_markup_nests_cleanly(self):
        # Guards the guard below: every element the tree opened was closed, so an
        # "this option is visible" answer is the markup's, not a lost end tag's.
        self.assertEqual(len(self.tree.stack), 1,
                         "index.html left an element unclosed, so the enclosing-section "
                         "rule below is reading a broken tree")

    def test_a_marked_option_in_a_collapsed_section_can_be_revealed(self):
        # A picked option flips a persisted preference, and main.js shows the visitor
        # it happened by scrolling to the control and flashing it. Both are no-ops on a
        # `hidden` subtree, so an option inside a collapsed accordion body needs that
        # body to be openable by clicking the header right before it, which is what
        # main.js's select() does. An option that is not in one is simply visible.
        for node in self.tree.walk():
            if "data-search" not in node.attrs or node.attrs.get("type") != "checkbox":
                continue
            body = node.hidden_ancestor()
            if body is None:
                continue
            head = body.previous_sibling()
            eid = node.attrs.get("id")
            self.assertIsNotNone(head, f"{eid}: nothing precedes its hidden section")
            self.assertIn("collapse-header", (head.attrs.get("class") or "").split(),
                          f"{eid}: its hidden section is not opened by a "
                          f"collapse-header, so a search pick would flip it invisibly")

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

    def test_a_marked_control_carries_decorative_chrome(self):
        # Guards the guard: WiringTest asserts the naming path drops aria-hidden
        # subtrees, which only means anything while some marked control HAS one (the
        # browse headers' chevron). If that ever stops being true, the rule below has
        # quietly become vacuous and should be reconsidered, not left passing.
        decorated = [eid for _, eid, _, inner, _ in self.rows
                     if 'aria-hidden="true"' in inner]
        self.assertTrue(decorated,
                        "no marked control carries decorative chrome any more, so "
                        "the visible-words rule in WiringTest now proves nothing")


class FoldTest(unittest.TestCase):
    """`fold` against js/main.js `foldText`, the rule it stands in for.

    A guard written from a stale reading of what it guards passes while proving less
    than it says. `fold` drifted once already, missing the dash step and so unable to
    see the very collision `test_an_alias_is_spelled_once` exists to catch.
    """

    def test_the_steps_mirror_foldtext(self):
        js = (ROOT / "public" / "js" / "main.js").read_text(encoding="utf-8")
        body = js[js.index("function foldText("):js.index("const SEARCH_FIELDS")]
        for step, why in (
                ('normalize("NFD")', "accents no longer decompose"),
                ("toLowerCase()", "case no longer folds"),
                # Matched as the source spells them: main.js writes these two ranges
                # as \u escapes, so the characters themselves would never be found.
                (r"[\u0300-\u036f]", "combining marks are no longer dropped"),
                (r"[-\u2010-\u2015]", "dashes are no longer dropped")):
            self.assertIn(step, body, f"foldText changed: {why}, so `fold` here "
                                      f"is a stale copy of the matcher's rule")

    def test_it_folds_what_the_matcher_folds(self):
        for a, b in (("guidée", "guidee"), ("night-mode", "nightmode"),
                     ("Sombre", "sombre"), ("non‑breaking", "nonbreaking")):
            self.assertEqual(fold(a), fold(b), f"{a!r} and {b!r} reach the same "
                                               f"control but fold apart")


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

    def test_a_control_is_named_by_its_visible_words(self):
        # A control is named by its own label, and a glyph marked aria-hidden is not
        # part of that label: it is the affordance. Read by raw textContent the six
        # browse headers listed as "Drugs \u25b8". Two ends have to hold for that to
        # stay fixed: visibleText still skips an aria-hidden subtree, and the naming
        # path still reads through it instead of going back to textContent.
        js = MAIN.read_text(encoding="utf-8")
        self.assertTrue('getAttribute("aria-hidden") === "true"' in js,
                        "visibleText no longer drops aria-hidden chrome, so a "
                        "decorative glyph is part of a control's name again")
        start = js.index('querySelectorAll("[data-search]")')
        block = js[start:js.index("const items = [", start)]
        self.assertTrue("visibleText(" in block,
                        "the command rows no longer name a control by its visible "
                        "words")
        self.assertFalse("textContent" in block,
                         "a command row is named by raw textContent again, which "
                         "folds a chevron / icon glyph into the name")

    def test_a_picked_option_opens_the_section_holding_it(self):
        # The markup half of this rule is MarkupTest's: a marked option inside a
        # collapsed body has a collapse-header right before that body. This is the
        # half that uses it. Without the reveal, picking "Show active metabolites"
        # from search flips a persisted preference with nothing on screen to show it.
        js = MAIN.read_text(encoding="utf-8")
        start = js.index('querySelectorAll("[data-search]")')
        block = js[start:js.index("const items = [", start)]
        self.assertIn('closest("[hidden]")', block,
                      "a picked option no longer looks for the collapsed section "
                      "holding it, so it would flip invisibly")
        self.assertIn("collapse-header", block,
                      "a picked option no longer opens its section by the section's "
                      "own header")

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
