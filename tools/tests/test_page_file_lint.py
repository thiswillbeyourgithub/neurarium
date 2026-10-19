"""Lint: no tool joins a page id into a ``.md`` path by hand.

A citation's ``page`` comes from untrusted places (an LLM's judged answer, an API
response, a hand edit), and ``../../README`` joined into ``<pages_dir>/<page>.md``
names a file outside the corpus. ``lib/page_file.py`` is the one place that turns a
page id into a page file (``page_file`` returns None, ``page_path`` raises), so this
greps every ``tools/**/*.py`` for the hand-rolled spellings of that join and fails on
any outside it. Like ``tools/check_js.py`` it is a lint, not a parser: it matches the
spellings the codebase has used (an f-string ending ``{x}.md``, a ``".md"`` literal
for concatenation / ``with_suffix`` / ``os.path.join``, ``%s.md`` / ``{}.md``).

Built with the help of Claude Code.
"""

import re
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent

JOIN = re.compile(r"""\}\.md["']|["']\.md["']|%s\.md|\{\}\.md""")

# path -> why its joins are safe. Keep it short: a new entry needs a reason a
# reviewer accepts, never "it was there already".
ALLOWED = {
    "lib/page_file.py": "the one rule every other caller goes through",
    "fetch/pdf_to_pages.py": "names each page after the integer index it enumerates "
                             "itself, never a data-derived id",
}


def violations(root=TOOLS):
    """``[(relative path, line number, line)]`` for every hand-rolled page join."""
    out = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("tests/") or rel in ALLOWED:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if JOIN.search(line) and not line.lstrip().startswith("#"):
                out.append((rel, n, line.strip()))
    return out


class PageJoinLintTest(unittest.TestCase):
    def test_no_hand_rolled_page_join(self):
        found = violations()
        self.assertFalse(found, "join page ids through lib.page_file (page_file / "
                                "page_path), not by hand:\n" + "\n".join(
                                    f"  tools/{p}:{n}: {line}" for p, n, line in found))

    def test_allowlist_entries_still_exist(self):
        for rel in ALLOWED:
            self.assertTrue((TOOLS / rel).is_file(), f"stale ALLOWED entry {rel}")

    def test_lint_catches_each_spelling(self):
        import tempfile
        spellings = ['p = PAGES / f"{page}.md"', 'p = os.path.join(d, page + ".md")',
                     'p = (d / page).with_suffix(".md")', 'p = "%s.md" % page',
                     'p = "{}.md".format(page)', "p = d / f'{cand[\"page\"]}.md'"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sourcing").mkdir()
            (root / "sourcing" / "bad.py").write_text("\n".join(spellings), "utf-8")
            (root / "sourcing" / "ok.py").write_text(
                'p = page_path(PAGES, page)\nif name.endswith(".mdx"): pass\n', "utf-8")
            self.assertEqual([n for _, n, _ in violations(root)],
                             list(range(1, len(spellings) + 1)))


if __name__ == "__main__":
    unittest.main()
