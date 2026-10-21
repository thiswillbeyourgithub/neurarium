"""The /api Markdown pages (``tools/render_api.py``) must never diverge from the viewer's
detail panels (``public/js/panel/``): same headings, same subtitles, same row labels, same
admonitions (addons).

The two are rendered by different code (JS in the browser, Python at image build), so
nothing but these tests keeps them together. Both read their words from one place,
``public/js/i18n/en.js``, and ``tools/api_sections.py`` is the one table saying which
stored field wears which panel heading. The tests close the remaining gaps:

- (a) every i18n key a panel uses as a section heading or subtitle is either mapped in
  that table or listed in ``api_sections.VIEWER_ONLY`` with the reason it has no Markdown
  twin, so a new panel section cannot ship without deciding its Markdown;
- (b) every stored top-level field of every page kind is mapped, hidden or folded with a
  reason, so a new data field cannot ship without a decision either;
- (c) every mapped heading, subtitle and row label renders with exactly the en.js text;
- (d) every addon renders (title and text) on its owner's page, in the section its slot
  sits in, and on every page showing a ``section.*`` slot's section;
- (e) every ``api_sections.ALWAYS`` section a record holds nothing for still renders, as
  its heading, subtitle and the panel's own "no information" sentence.

Run: ``python -m unittest discover -s tools/tests -t tools/tests -p test_panel_md_parity.py``
Built with the help of Claude Code.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import api_sections as AS  # noqa: E402
import render_api  # noqa: E402
from lib.structure_ids import base_id  # noqa: E402

PANEL = ROOT / "public" / "js" / "panel"
# The calls that build a panel heading (dom.js heading / subSection, info.js
# appendSourcedHeading, pathways.js appendPathwayList, sections.js betaSection /
# betaHeading) or a bare <h3>/<h4>/<h5>.
HEAD_CALL = re.compile(r"\b(heading|subSection|appendSourcedHeading|appendPathwayList"
                       r"|betaSection|betaHeading|el)\(")
T_KEY = re.compile(r'\bt\("([A-Za-z0-9_.]+)"')
STR = re.compile(r'"([A-Za-z0-9_.]+)"')
SUB_KEY = re.compile(r'\bsubKey:\s*"([A-Za-z0-9_.]+)"')
MODES = ("kind", "sign")  # a projection group's `mode`, filling "group.{mode}Heading"


def _args(text: str, open_at: int) -> str:
    """The argument text of the call whose ``(`` sits at ``open_at`` (parens balanced,
    string literals skipped)."""
    depth, i, quote = 0, open_at, None
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:i]
        i += 1
    return text[open_at + 1:]


def panel_heading_keys() -> dict[str, str]:
    """``i18n key -> file`` for every literal key a panel uses as a heading or subtitle."""
    out: dict[str, str] = {}
    for path in sorted(PANEL.rglob("*.js")):
        # Comment lines only (a `//` inside a string must not cut a call short).
        src = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                        if not line.lstrip().startswith(("//", "*", "/*")))
        for m in HEAD_CALL.finditer(src):
            args = _args(src, m.end() - 1)
            name = m.group(1)
            if name == "el" and not re.match(r'\s*"h[345]"', args):
                continue
            if name == "betaSection":
                lits = STR.findall(args)
                keys = lits[1:2] + SUB_KEY.findall(args)
            else:
                keys = T_KEY.findall(args)
            for k in keys:
                out.setdefault(k, path.relative_to(ROOT).as_posix())
    return out


def mapped_keys() -> set[str]:
    """Every heading / subtitle / parent key the table renders (mode templates filled)."""
    keys: set[str] = set()
    for fields in AS.FIELDS.values():
        for lab in fields.values():
            for k in (lab.key, lab.sub):
                if k and "{" in k:  # a mode template: the modes the catalogue words
                    keys |= {k.format(mode=m) for m in MODES} & set(AS.EN)
                elif k:
                    keys.add(k)
            if lab.parent:
                keys |= set(lab.parent.split(" > "))
    keys |= set(AS.PARENTS) | {s for s in AS.PARENTS.values() if s}
    return keys


class Rendered:
    """Every node page rendered once, as ``(kind, id) -> (record, page_set, sections)``."""
    _cache = None

    @classmethod
    def get(cls):
        if cls._cache is None:
            r = render_api.Renderer(render_api.load(render_api.PUBLIC / "data"))
            pages = {}
            for kind, records in r.pages.items():
                if kind == "effect":
                    continue
                for ident, rec in records.items():
                    pset = r.page_set(kind, ident, rec)
                    r.ident = ident
                    pages[(kind, ident)] = (rec, pset, r.sections(kind, rec))
            cls._cache = (r, pages)
        return cls._cache


class PanelHeadingsTest(unittest.TestCase):
    """(a) a panel heading with no Markdown decision fails here."""

    def test_scan_finds_the_panel_headings(self):
        # A guard on the guard: a scan matching nothing would pass every check below.
        keys = panel_heading_keys()
        for k in ("drug.brands", "drug.brandsSub", "drug.actsOn", "effects.heading",
                  "drug.workup", "circuit.structures"):
            self.assertIn(k, keys)

    def test_every_panel_heading_is_rendered_or_viewer_only(self):
        known = mapped_keys() | set(AS.VIEWER_ONLY)
        # A subtitle (`<heading>Sub`) follows its heading's decision.
        missing = {k: f for k, f in panel_heading_keys().items()
                   if k not in known and k.removesuffix("Sub") not in AS.VIEWER_ONLY}
        self.assertEqual(missing, {}, "map each in api_sections.FIELDS, or list it in "
                                      "VIEWER_ONLY with the reason it has no Markdown twin")

    def test_viewer_only_is_not_stale(self):
        scanned = panel_heading_keys()
        self.assertEqual(sorted(set(AS.VIEWER_ONLY) - set(scanned)), [],
                         "these VIEWER_ONLY keys are no longer a panel heading")
        self.assertEqual(sorted(set(AS.VIEWER_ONLY) & mapped_keys()), [],
                         "a key cannot be both rendered and viewer-only")

    def test_every_table_key_is_in_en_js(self):
        for k in mapped_keys() | set(AS.VIEWER_ONLY):
            self.assertIn(k, AS.EN, f"{k}: not in public/js/i18n/en.js")


class StoredFieldsTest(unittest.TestCase):
    """(b) a stored field with no Markdown decision fails here."""

    def test_every_stored_field_is_decided(self):
        r, pages = Rendered.get()
        undecided = set()
        for (kind, _), (rec, _, _) in pages.items():
            fields = AS.FIELDS.get(kind, {})
            for k in rec:
                if k in fields or k in AS.HIDDEN or (kind, k) in AS.FOLDED \
                        or k in render_api.RECORD_GRADES:
                    continue
                if k.endswith(render_api.SOURCE_SUFFIXES):
                    claim = r.claim_of(k, rec)
                    stem = next(k[:-len(s)] for s in render_api.SOURCE_SUFFIXES if k.endswith(s))
                    if claim or stem in fields:
                        continue  # rides its claim's line, or an orphan claim the table names
                undecided.add((kind, k))
        self.assertEqual(sorted(undecided), [], "add each to api_sections.FIELDS (with a panel "
                                                "label, or key=None and why), HIDDEN or FOLDED")

    def test_an_unlabelled_field_says_why(self):
        for kind, fields in AS.FIELDS.items():
            for k, lab in fields.items():
                if lab.key is None:
                    self.assertTrue(lab.why, f"{kind}.{k}: key=None needs a why")

    def test_every_parent_has_its_subtitle_decided(self):
        for fields in AS.FIELDS.values():
            for lab in fields.values():
                for p in (lab.parent or "").split(" > "):
                    if p:
                        self.assertIn(p, AS.PARENTS)


class RenderedWordsTest(unittest.TestCase):
    """(c) the Markdown wears exactly the en.js words."""

    def test_sample_pages(self):
        _, pages = Rendered.get()
        en = AS.EN
        drug = pages[("drug", "sertraline")][1][None]
        for k in ("drug.brands", "drug.actsOn", "drug.formulations", "drug.halfLife"):
            self.assertIn(f"\n## {en[k]}\n", drug, k)
        for k in ("drug.brandsSub", "drug.actsOnSub"):
            self.assertIn(f"\n*{en[k]}*\n", drug, k)
        self.assertIn(f"\n- {en['drug.class']} (categories): ", drug)
        receptor = pages[("receptor", "5ht1a")][1][None]
        self.assertIn(f"\n## {en['receptor.foundIn']}\n\n*{en['receptor.foundInSub']}*\n", receptor)
        self.assertIn(f"\n- {en['receptor.effect']} (sign): ", receptor)
        self.assertIn(f"\n## {en['effects.heading']}\n", receptor)
        structure = pages[("structure", "hippocampus_R")][1][None]
        self.assertIn(f"\n- {en['info.reference']} (wikipedia): ", structure)

    def test_every_mapped_label_renders(self):
        _, pages = Rendered.get()
        for (kind, ident), (rec, pset, secs) in pages.items():
            full = pset[None]
            slugs = {slug for slug, *_ in secs}
            for slug, head, lines, _ in secs:
                lab = AS.label(kind, slug)
                if slug == "facts" or lab is None or lab.key is None:
                    continue
                where = f"{kind}/{ident} {slug}"
                self.assertEqual(head, AS.text(lab.key, rec), where)
                self.assertIn(f"\n## {head}\n", full, where)
                sub = AS.text(lab.sub, rec)
                if sub:
                    self.assertIn(f"*{sub}*", lines, where)
                if lab.parent:
                    self.assertIn(f"In the viewer under: {AS.parent_text(lab)}.", lines, where)
            for k in rec:
                lab = AS.label(kind, k)
                if lab and lab.key and k not in slugs and k != "sources":
                    self.assertIn(f"\n- {AS.text(lab.key, rec)} ({k}): ", full, f"{kind}/{ident} {k}")


class EmptySectionsTest(unittest.TestCase):
    """(e) a section the panel shows empty (dom.js emptySection) shows empty in the
    Markdown too: heading, subtitle and the same en.js sentence, on the full page and on
    its own section page."""

    def test_lower_first_matches_the_panel(self):
        # The same examples as tools/tests/empty_section.test.mjs (dom.js lowerFirst).
        for raw, low in (("Age and sex differences", "age and sex differences"),
                         ("CNS penetration", "CNS penetration"),
                         ("Pharmacogenomics", "pharmacogenomics"), ("", ""), ("A", "a")):
            self.assertEqual(AS.lower_first(raw), low)
        self.assertEqual(AS.fill(AS.EN["info.noData"], what="x", kind=AS.EN["info.kindThis.drug"]),
                         "No information about x for this drug yet.")

    def test_every_always_section_is_a_panel_heading(self):
        scanned = panel_heading_keys()
        for kind, secs in AS.ALWAYS.items():
            for slug, sec in secs.items():
                self.assertIn(sec.key, scanned, f"{kind}/{slug}")
                self.assertTrue(AS.section_fields(kind, sec.key), f"{kind}/{slug}: no field")

    def test_an_absent_section_renders_its_placeholder(self):
        r, pages = Rendered.get()
        seen = set()
        for (kind, ident), (rec, pset, _) in pages.items():
            for slug, sec in AS.empty_sections(kind, rec, r.derived_sections(kind, rec)):
                seen.add((kind, slug))
                where = f"{kind}/{ident} {slug}"
                text = AS.EN[sec.none] if sec.none else AS.no_data(kind, sec.key)
                head = f"\n## {AS.EN[sec.key]}\n"
                sub, parent = AS.section_head(kind, sec.key)
                self.assertIn(slug, pset, where + ": no section page")
                for page in (pset[None], pset[slug]):
                    self.assertIn(head, page, where)
                    self.assertIn(text, page, where)
                    if sub:
                        self.assertIn(f"*{AS.EN[sub]}*", page, where)
                    if parent:
                        self.assertIn(f"In the viewer under: {parent}.", page, where)
        # A guard on the guard: the real data must exercise the placeholders.
        for probe in (("receptor", "demographics"), ("drug", "workup"), ("drug", "metabolism")):
            self.assertIn(probe, seen)

    def test_sample_placeholder(self):
        _, pages = Rendered.get()
        page = pages[("receptor", "5ht3")][1][None]
        self.assertIn("No information about age and sex differences for this receptor yet.", page)

    def test_derived_variants_keep_pharmacogenomics(self):
        """Lithium has no CPIC rows, but receptor pages' ClinPGx variants name it (the
        drug panel lists them), so only the CPIC subsection is empty, never the whole
        Pharmacogenomics section."""
        _, pages = Rendered.get()
        page = pages[("drug", "lithium")][1][None]
        self.assertNotIn("No information about pharmacogenomics for this drug", page)
        self.assertIn("No information about pharmacogenomic dosing (CPIC) for this drug yet.", page)


class AddonsTest(unittest.TestCase):
    """(d) every admonition the panel shows is on the Markdown page too."""

    def test_every_slot_is_placed(self):
        r, _ = Rendered.get()
        slots = render_api.load(render_api.PUBLIC / "data")["meta"]["addon_slots"]
        self.assertEqual(sorted(slots), sorted(AS.SLOT_PLACE),
                         "each meta.addon_slots slot needs a place in api_sections.SLOT_PLACE")

    def test_every_addon_renders_where_the_panel_puts_it(self):
        r, pages = Rendered.get()
        for a in r.addons:
            pkind, fields = AS.SLOT_PLACE[a["slot"]]
            if a["owner_kind"] == "section":
                hosts = [key for key, (rec, _, _) in pages.items()
                         if key[0] == pkind and (not fields or any(f in rec for f in fields))]
            else:
                hosts = [key for key in pages if key[0] == pkind
                         and a["owner"] in (key[1], base_id(key[1]))]
            self.assertTrue(hosts, f"addon {a['id']}: no page shows it")
            for key in hosts:
                rec, pset, _ = pages[key]
                where = next((f for f in fields if f in rec), None)
                for page in ([pset[None]] + ([pset[where]] if where else [])):
                    self.assertIn(f"**{a['title']}**", page, f"{a['id']} on {key}")
                    self.assertIn(a["text"], page, f"{a['id']} on {key}")


if __name__ == "__main__":
    unittest.main()
