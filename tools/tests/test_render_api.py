"""``tools/render_api.py``: the /api Markdown pages render from the committed data, and
every link and quote marker on them resolves.

Run: ``python -m unittest tools.tests.test_render_api``
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import render_api  # noqa: E402
import api_sections  # noqa: E402 (the panel's own words, read from en.js)

LINK = re.compile(r"\]\(/api/([^)]*)\)")
MARKER = re.compile(r"\[(?:verified|sourced|llm|uncertain) (q_[0-9a-f]+)\]")
LISTED = re.compile(r"^- `(q_[0-9a-f]+)` ", re.M)


class RenderApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "api"
        cls.n = render_api.render(render_api.PUBLIC / "data", cls.out, "0.0.0")
        cls.pages = {p.relative_to(cls.out).as_posix(): p.read_text(encoding="utf-8")
                     for p in cls.out.rglob("*.md")}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def top(self):
        """The node pages and indexes, without the per-section pages under ``<id>/``."""
        return {n: t for n, t in self.pages.items() if n.count("/") <= 1}

    def test_one_page_per_node_plus_index(self):
        kinds = {name.split("/")[0] for name in self.pages if "/" in name}
        # + one index per kind, the top index and the 404 page
        self.assertEqual(len(self.top()), self.n + len(kinds) + 2)
        self.assertIn("drug/sertraline.md", self.pages)
        self.assertIn("receptor/d2.md", self.pages)

    def test_every_link_resolves(self):
        for name, text in self.pages.items():
            for target in LINK.findall(text):
                self.assertFalse(target.endswith(".md"), f"{name}: {target} keeps its .md")
                page = target + "index.md" if target.endswith("/") or not target else target + ".md"
                self.assertIn(page, self.pages, f"{name} links to missing {target}")

    def test_every_quote_marker_is_listed_once(self):
        for name, text in self.pages.items():
            listed = LISTED.findall(text)
            self.assertEqual(len(listed), len(set(listed)), f"{name}: a quote listed twice")
            self.assertEqual(set(MARKER.findall(text)), set(listed), name)

    def test_not_found_lists_every_page(self):
        text = self.pages["not_found.md"]
        self.assertIn("No page at this address", text)
        for name in self.top():
            if not name.endswith("index.md") and name != "not_found.md":
                self.assertIn(f"(/api/{name.removesuffix('.md')})", text)

    def test_sources_sit_on_their_claim_line(self):
        # A `<claim>_sources` key renders beside its claim, never as its own section or
        # bullet (it once read "## category sources" far below "categories" in Facts).
        for name, text in self.pages.items():
            self.assertNotRegex(text, r"(?m)^## [a-z][a-z_ ]*\b(sources|provenance)$", name)
            self.assertNotRegex(text, r"(?m)^\s*- [a-z_]+_sources:", name)
        facts = self.pages["drug/sertraline/facts.md"]
        self.assertRegex(facts, r"(?m)^- Class \(categories\): .*\[verified q_[0-9a-f]+\]")
        self.assertRegex(facts, r"(?m)^- Nomenclature \(nbn\): .*\[verified q_[0-9a-f]+\]")

    def test_llm_grade_always_flagged_unsourced(self):
        # An LLM-memory claim must never read like a citation to an agent.
        for name, text in self.pages.items():
            for line in text.splitlines():
                if re.search(r"\[llm[\] ]|: llm\b", line) and "Grades:" not in line:
                    self.assertIn("UNSOURCED", line, f"{name}: {line}")

    def test_section_pages_split_the_full_page(self):
        full = self.pages["drug/sertraline.md"]
        self.assertIn("(/api/drug/sertraline/bindings)", full)
        part = self.pages["drug/sertraline/bindings.md"]
        self.assertIn(f"## {api_sections.text('drug.actsOn')}\n", part)
        self.assertNotIn(f"## {api_sections.text('drug.brands')}\n", part)
        # each section page lists exactly the quotes it cites
        self.assertEqual(set(MARKER.findall(part)), set(LISTED.findall(part)))
        self.assertIn("drug/sertraline/index.md", self.pages)

    def test_source_links_match_the_viewer_tooltip(self):
        # A DailyMed quote carries its label page (corpus page_url), as the tooltip does.
        self.assertRegex(self.pages["drug/sertraline.md"] + "".join(self.pages.values()),
                         r"https://dailymed\.nlm\.nih\.gov/dailymed/drugInfo\.cfm\?setid=[0-9a-f-]+")
        # A Ki cited by quote keeps its own reference permalink next to the marker.
        self.assertRegex("".join(self.pages.values()),
                         r"\[verified q_[0-9a-f]+\] \([^)]*reference: https://")

    def test_effect_page_lists_owners_and_derived_drugs(self):
        page = self.pages["effect/nausea.md"]
        self.assertIn("Kind: effect (BETA)", page)
        self.assertIn("#tabs=effect:nausea", page)
        self.assertIn("(/api/receptor/5ht3)", page)
        self.assertIn("## " + api_sections.text("effect.drugs").split("{")[0], page)
        self.assertIn("(/api/drug/ondansetron)", self.pages["effect/antiemetic.md"])
        self.assertIn("(/api/effect/nausea)", self.pages["effect/index.md"])

    def test_effect_page_flags_an_isolated_tissue_owner(self):
        self.assertIn("(/api/receptor/h3) (uncertain: isolated_tissue)",
                      self.pages["effect/vasoconstriction.md"])

    def test_presentation_fields_skipped(self):
        self.assertNotIn("shape_file", self.pages["structure/putamen_R.md"])


class PageIdGuardTest(unittest.TestCase):
    """A malformed id must never become a file path outside its kind directory."""

    def test_render_refuses_a_path_like_id(self):
        data = render_api.load(render_api.PUBLIC / "data")
        data["drugs"][0] = dict(data["drugs"][0], id="../escaped")
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(render_api, "load", return_value=data):
            with self.assertRaises(ValueError):
                render_api.render(render_api.PUBLIC / "data", Path(tmp) / "api", "0.0.0")
            self.assertFalse((Path(tmp) / "escaped.md").exists())

    def test_reserved_and_projection_ids(self):
        render_api._check_page_id("projection", "raphe--frontal_R")
        for bad in ("index", "not_found", "a/b", "", None):
            with self.assertRaises(ValueError):
                render_api._check_page_id("drug", bad)


if __name__ == "__main__":
    unittest.main()


class UptimeLineTest(unittest.TestCase):
    """The DEV restart line (render_api.UPTIME), executed by Caddy's `templates` on /api/*.
    The template itself was checked against a real Caddy in a docker build; here: where it
    goes, that it vanishes cleanly when it renders empty, and that the Caddyfile wires it."""

    def test_inserted_under_the_title(self):
        out = render_api.with_uptime("# Sertraline\nKind: drug.\n")
        self.assertEqual(out, f"# Sertraline\n{render_api.UPTIME}Kind: drug.\n")

    def test_renders_to_the_built_page_when_off(self):
        # Off DEV the whole {{%if%}} block yields "", which must give back the page as built.
        page = "# Neurarium API (version 1.0.0)\n\nOne page per node.\n"
        self.assertEqual(render_api.with_uptime(page).replace(render_api.UPTIME, ""), page)

    def test_refuses_text_holding_the_delimiters(self):
        for bad in ("# A\nsee {{% here", "# A\nend %}}"):
            with self.assertRaises(ValueError):
                render_api.with_uptime(bad)

    def test_caddyfile_runs_the_template_with_the_same_delimiters(self):
        caddy = (Path(__file__).resolve().parents[2] / "docker" / "Caddyfile").read_text()
        block = caddy[caddy.index("handle /api/* {"):]
        self.assertIn("templates {", block)
        self.assertIn(f"between {render_api.UPTIME_OPEN} {render_api.UPTIME_CLOSE}", block)
        self.assertIn("mime text/markdown", block)
