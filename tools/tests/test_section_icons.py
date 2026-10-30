#!/usr/bin/env python
"""Every detail-panel section key must name an icon (public/js/panel/section-icons.js).

A section draws its icon from its `data-icon`, else its `data-tour-sec`; a key with no
SECTION_ICONS entry draws nothing, silently, so a new section would ship as the one
icon-less heading in its panel. This collects every key the panel code hands out
(tour anchors, betaSection ids, explicit icons) and fails on one that is neither mapped
nor listed in NOT_A_SECTION with a reason.

Built with the help of Claude Code.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "public" / "js" / "panel"
ICONS_JS = PANEL / "section-icons.js"

# Keys that anchor something other than a foldable `<h3>` section, so no icon is drawn.
NOT_A_SECTION = {
    "facts": "the fact rows under a panel's title",
    "links": "the external-link row under the description",
    "wiki": "the Wikipedia description",
    "brands": "an <h4> subsection of Identification",
    "metabolites": "an <h4> subsection of Metabolism",
    "pgx": "an <h4> subsection of Pharmacogenomics",
}

KEY_PATTERNS = [
    r'tourSec = "([^"]+)"', r'tourSec: "([^"]+)"', r'betaSection\("([^"]+)"',
    r'dataset\.icon = "([^"]+)"', r'icon: "([^"]+)"',
    # helpers taking the tour anchor positionally (pathways.js, expression.js)
    r'appendPathwayList\([^,]+, [^,]+, [^,]+, "([^"]+)"\);',
    r'appendFoundIn\([^,]+, [^,]+, "([^"]+)"\);',
]


def _icons():
    src = ICONS_JS.read_text()
    glyphs = set(re.findall(r'^  "([a-z0-9-]+)": \'', src, re.M))
    block = src[src.index("export const SECTION_ICONS"):]
    block = block[:block.index("\n};")]
    return glyphs, dict(re.findall(r'^  (\w+): "([a-z0-9-]+)",', block, re.M))


def _used_keys():
    keys = {}
    for path in PANEL.rglob("*.js"):
        if path == ICONS_JS:
            continue
        src = path.read_text()
        for pat in KEY_PATTERNS:
            for key in re.findall(pat, src):
                keys.setdefault(key, path.relative_to(ROOT).as_posix())
    return keys


def _empty_section_calls():
    """(file, call text) of every emptySection(...) call, parentheses balanced."""
    for path in PANEL.rglob("*.js"):
        src = path.read_text()
        for m in re.finditer(r"\bemptySection\(", src):
            if src[max(0, m.start() - 16):m.start()].endswith("function "):
                continue
            depth, i = 0, m.end() - 1
            while True:
                depth += {"(": 1, ")": -1}.get(src[i], 0)
                if depth == 0:
                    break
                i += 1
            yield path.relative_to(ROOT).as_posix(), src[m.start():i + 1]


class SectionIconTest(unittest.TestCase):

    def test_every_empty_top_level_section_names_its_icon(self):
        # An empty section is built apart from its filled twin, so it must carry the
        # key itself (a `<h4>` subsection draws no icon).
        bare = [(f, " ".join(call.split())[:90]) for f, call in _empty_section_calls()
                if '"h4"' not in call and "subHead(" not in call
                and "tourSec" not in call and "icon:" not in call]
        self.assertEqual(bare, [], "an empty <h3> section with neither tourSec nor icon")

    def test_every_section_key_has_an_icon(self):
        _, mapping = _icons()
        missing = {k: where for k, where in _used_keys().items()
                   if k not in mapping and k not in NOT_A_SECTION}
        self.assertEqual(missing, {}, "a panel section key with no SECTION_ICONS entry: "
                         "map it, or list it in NOT_A_SECTION with the reason")

    def test_every_mapped_icon_has_a_glyph(self):
        glyphs, mapping = _icons()
        self.assertTrue(mapping)
        self.assertEqual({k: v for k, v in mapping.items() if v not in glyphs}, {})

    def test_the_key_collector_sees_the_known_sections(self):
        # Guards the regexes themselves: a refactor that renames the helpers would
        # otherwise make the first test pass vacuously.
        used = _used_keys()
        for key in ("bindings", "identity", "effects", "regions", "pathways", "drugs"):
            self.assertIn(key, used)


if __name__ == "__main__":
    unittest.main(verbosity=2)
