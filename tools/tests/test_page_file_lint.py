"""Lint: no tool joins a page id into a ``.md`` (or raw ``.json`` / ``.html`` / ``.xml``) path by hand.

A citation's ``page`` comes from untrusted places (an LLM's judged answer, an API
response, a hand edit), and ``../../README`` joined into ``<pages_dir>/<page>.md``
names a file outside the corpus. ``lib/page_file.py`` is the one place that turns a
page id into a page file (``page_file`` returns None, ``page_path`` raises), so this
greps every ``tools/**/*.py`` for the hand-rolled spellings of that join and fails on
any outside it. Like ``tools/check_js.py`` it is a lint, not a parser: it matches the
spellings the codebase has used (an f-string ending ``{x}.md``, a ``".md"`` literal
for concatenation / ``with_suffix`` / ``os.path.join``, ``%s.md`` / ``{}.md``).

A fetcher's raw store (``raw/<id>.json`` / ``.html`` / ``.xml``) is keyed by the same
data-derived ids (an API's setid, a Wikipedia slug), so its join goes through
``page_path(dir, id, suffix)`` too; :data:`RAW_JOIN` catches a directory joined to an
f-string that is only ``{id}.<ext>`` (``d / f"{x}.json"``, ``os.path.join(d,
f"{x}.html")``, ``d + f"/{x}.xml"``). A name with a literal stem (``batch_{i}.json``)
is not an id join and passes.

Built with the help of Claude Code.
"""

import re
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent

JOIN = re.compile(r"""\}\.md["']|["']\.md["']|%s\.md|\{\}\.md""")
_RAW_ID = r"""\{[^}]*\}\.(?:json|html|xml)["']"""
RAW_JOIN = re.compile(rf"""/\s*f["']{_RAW_ID}|join\([^)]*f["']{_RAW_ID}|\+\s*f["']/{_RAW_ID}""")

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
            if ((JOIN.search(line) or RAW_JOIN.search(line))
                    and not line.lstrip().startswith("#")):
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
                     'p = "{}.md".format(page)', "p = d / f'{cand[\"page\"]}.md'",
                     'p = RAW / f"{owner}.json"', 'p = os.path.join(RAW, f"{slug}.html")',
                     'p = RAW + f"/{slug}.html"', "(RAW_DIR / f'{meta[\"setid\"]}.xml')"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sourcing").mkdir()
            (root / "sourcing" / "bad.py").write_text("\n".join(spellings), "utf-8")
            (root / "sourcing" / "ok.py").write_text(
                'p = page_path(PAGES, page)\nif name.endswith(".mdx"): pass\n'
                'p = page_path(RAW, owner, ".json")\n'
                'p = os.path.join(out, f"batch_{i}.json")\np = DATA / f"{name}.jsonl"\n',
                "utf-8")
            self.assertEqual([n for _, n, _ in violations(root)],
                             list(range(1, len(spellings) + 1)))


# A quote-gate page (``<pages_dir>/<page>.md``) is read through ``read_page`` /
# ``read_page_file`` too, so every reader decodes it the same way (bad bytes replaced,
# an absent page None). A page path is whatever ``page_path`` / ``page_file`` hand back
# for a ``.md`` (two arguments, no suffix), what ``wikipedia.page_for`` resolves, or a
# loop variable over a ``*.md`` glob; reading one of those names by hand is flagged.
_ARGS2 = r"""[^(),]*(?:\([^()]*\))?[^(),]*,[^(),]*(?:\([^()]*\))?[^(),]*"""
PAGE_VAR = re.compile(rf"""\b(\w+)\s*=\s*(?:\w+\.)?(?:page_for\([^)]*\)|"""
                      rf"""(?:page_path|page_file)\({_ARGS2}\))""")
GLOB_VAR = re.compile(r"""\bfor\s+(\w+)\s+in\b.*\.glob\(\s*["']\*\.md["']""")
WRITE_MODE = re.compile(r"""\bopen\([^)]*,\s*["'][wax]""")  # a page being stored, not read
READ_ALLOWED = {
    "lib/page_file.py": "the one page reader",
    "fetch/build_index.py": "a self-contained ``uv run`` script indexing the page tree "
                            "pdf_to_pages wrote; it imports no tools library",
}


def raw_page_reads(root=TOOLS):
    """``[(relative path, line number, line)]`` for every page file read by hand."""
    out = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("tests/") or rel in READ_ALLOWED:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        names = {m.group(1) for line in lines
                 for rx in (PAGE_VAR, GLOB_VAR) for m in rx.finditer(line)}
        if not names:
            continue
        alt = "|".join(sorted(map(re.escape, names)))
        read = re.compile(rf"""\bopen\(\s*(?:{alt})\b|(?<![\w.])(?:{alt})\.read_text\(|"""
                          rf"""Path\(\s*(?:{alt})\s*\)\.read_text\(""")
        for n, line in enumerate(lines, 1):
            if (read.search(line) and not WRITE_MODE.search(line)
                    and not line.lstrip().startswith("#")):
                out.append((rel, n, line.strip()))
    return out


class PageReadLintTest(unittest.TestCase):
    def test_no_hand_rolled_page_read(self):
        found = raw_page_reads()
        self.assertFalse(found, "read page files through lib.page_file (read_page / "
                                "read_page_file), not by hand:\n" + "\n".join(
                                    f"  tools/{p}:{n}: {line}" for p, n, line in found))

    def test_allowlist_entries_still_exist(self):
        for rel in READ_ALLOWED:
            self.assertTrue((TOOLS / rel).is_file(), f"stale READ_ALLOWED entry {rel}")

    def test_lint_catches_each_spelling(self):
        import tempfile
        bad = ['p = page_path(PAGES, page)', 'text = p.read_text("utf-8", errors="replace")',
               'en = wikistore.page_for(drug)', 'with open(en, encoding="utf-8") as f:',
               'text = Path(en).read_text(encoding="utf-8")',
               'for q in sorted(d.glob("*.md"), key=len):', 'text = q.read_text("utf-8")',
               'md = page_file(tree, page)', 'text = md.read_text() if md else ""']
        ok = ['raw = page_path(RAW, slug, ".html")', 'html = raw.read_text("utf-8")',
              'text = read_page(PAGES, page)', 'text = read_page_file(en)',
              'page_path(PAGES, page).write_text(body)',
              'with open(en, "w", encoding="utf-8") as f:']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "fetch").mkdir()
            (root / "fetch" / "bad.py").write_text("\n".join(bad), "utf-8")
            (root / "fetch" / "ok.py").write_text("\n".join(ok), "utf-8")
            self.assertEqual([(p, n) for p, n, _ in raw_page_reads(root)],
                             [("fetch/bad.py", n) for n in (2, 4, 5, 7, 9)])


if __name__ == "__main__":
    unittest.main()
