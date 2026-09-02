#!/usr/bin/env python
"""Unit tests for tools/data_generators/changelog.py, the release-note parser.

Stdlib ``unittest`` only (no deps), matching the other test modules. Runnable
directly: ``python tools/tests/test_changelog.py``, and pytest-discoverable.

The parser is the only thing standing between a typo in a hand-written markdown
file and a silently missing bullet in the What's new popup, so every rejection
path is tested as carefully as the happy one.

Built with the help of Claude Code.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data_generators"))
import changelog  # noqa: E402


TITLE = "# 1.0.0 (2026-01-31)\n"


class ParseTest(unittest.TestCase):
    def parse(self, text, title=TITLE):
        """The bullets of a file, with a valid title prepended (the title's own rules
        are covered by TitleTest, so every other case can ignore it)."""
        return changelog.parse_changelog(title + text, "test.md")["entries"]

    def test_bullet_with_french_and_commits(self):
        entries = self.parse(
            "## Added\n"
            "- A new thing (2e7c22f, 211E89F)\n"
            "  fr: Une nouveauté\n")
        self.assertEqual(entries, [{
            "category": "added",
            "text": {"en": "A new thing", "fr": "Une nouveauté"},
            "commits": ["2e7c22f", "211e89f"],   # normalized to lowercase
        }])

    def test_french_line_drops_its_own_sha_suffix(self):
        """A bullet's shas are metadata the viewer renders itself from ``commits``.

        The English half always had them stripped; the French half did not, so a
        French reader saw the sha list twice (once as literal text, once as the
        rendered commit links).
        """
        entries = self.parse(
            "## Fixed\n"
            "- A new thing (2e7c22f)\n"
            "  fr: Une nouveauté (2e7c22f)\n")
        self.assertEqual(entries[0]["text"]["fr"], "Une nouveauté")
        self.assertEqual(entries[0]["commits"], ["2e7c22f"])

    def test_commits_are_optional(self):
        entries = self.parse("## Fixed\n- Something\n  fr: Quelque chose\n")
        self.assertEqual(entries[0]["commits"], [])

    def test_parenthesis_that_is_not_a_sha_stays_in_the_text(self):
        """Bullets end in prose parentheses all the time; only a real sha list is
        stripped, so "(the tone model)" must survive as text."""
        entries = self.parse("## Improved\n- A thing (the tone model)\n  fr: Un truc\n")
        self.assertEqual(entries[0]["text"]["en"], "A thing (the tone model)")
        self.assertEqual(entries[0]["commits"], [])

    def test_categories_and_order_are_preserved(self):
        entries = self.parse(
            "## Fixed\n- B\n  fr: B\n"
            "## Added\n- A\n  fr: A\n")
        self.assertEqual([e["category"] for e in entries], ["fixed", "added"])

    def test_blank_lines_are_ignored(self):
        entries = self.parse("\n## Added\n\n- A\n  fr: A\n\n")
        self.assertEqual(len(entries), 1)

    def test_unknown_category_raises(self):
        with self.assertRaisesRegex(ValueError, "unknown category"):
            self.parse("## Broken\n- A\n  fr: A\n")

    def test_missing_french_raises(self):
        """The build must fail rather than ship a bullet that has no French: the
        popup would silently show English to a French reader."""
        with self.assertRaisesRegex(ValueError, "no 'fr:' line"):
            self.parse("## Added\n- A\n")

    def test_two_french_lines_on_one_bullet_raises(self):
        with self.assertRaisesRegex(ValueError, "already has a French line"):
            self.parse("## Added\n- A\n  fr: A\n  fr: B\n")

    def test_bullet_before_any_heading_raises(self):
        with self.assertRaisesRegex(ValueError, "before any"):
            self.parse("- A\n  fr: A\n")

    def test_stray_prose_raises(self):
        with self.assertRaisesRegex(ValueError, "not a heading"):
            self.parse("## Added\nthis is not a bullet\n")

    def test_empty_file_raises(self):
        with self.assertRaisesRegex(ValueError, "no bullets"):
            self.parse("## Added\n")


class TitleTest(unittest.TestCase):
    """The title carries the release date, which has nowhere else to live: the emit is
    a plain file read, with no git history to date a version from."""

    def parse(self, text):
        return changelog.parse_changelog(text, "test.md")

    def test_title_yields_version_and_date(self):
        parsed = self.parse("# 3.39.0 (2026-07-28)\n## Added\n- A\n  fr: A\n")
        self.assertEqual(parsed["version"], "3.39.0")
        self.assertEqual(parsed["date"], "2026-07-28")

    def test_missing_title_raises(self):
        with self.assertRaisesRegex(ValueError, "no release date"):
            self.parse("## Added\n- A\n  fr: A\n")

    def test_dateless_title_raises(self):
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            self.parse("# 3.39.0\n## Added\n- A\n  fr: A\n")

    def test_impossible_date_raises(self):
        with self.assertRaisesRegex(ValueError, "not a real date"):
            self.parse("# 3.39.0 (2026-02-31)\n## Added\n- A\n  fr: A\n")

    def test_two_titles_raise(self):
        with self.assertRaisesRegex(ValueError, "second"):
            self.parse("# 3.39.0 (2026-07-28)\n# 3.40.0 (2026-07-29)\n"
                       "## Added\n- A\n  fr: A\n")


class VersionKeyTest(unittest.TestCase):
    def test_orders_numerically_not_lexically(self):
        versions = ["3.9.0", "3.10.0", "3.10.1"]
        self.assertEqual(sorted(versions, key=changelog.version_key), versions)

    def test_rejects_a_non_semver_directory_name(self):
        for bad in ("3.39", "v3.39.0", "latest", "3.39.0-rc1"):
            with self.assertRaises(ValueError, msg=bad):
                changelog.version_key(bad)


class LoadTest(unittest.TestCase):
    """The real docs/changelog/ tree: it must parse, and every released version in
    it must be newest-first (the order the viewer relies on)."""

    def test_repo_changelog_loads_newest_first(self):
        releases = changelog.load_changelog(
            Path(__file__).resolve().parent.parent.parent / "docs")
        self.assertTrue(releases, "docs/changelog/ has no versions")
        keys = [changelog.version_key(r["version"]) for r in releases]
        self.assertEqual(keys, sorted(keys, reverse=True))
        for release in releases:
            self.assertTrue(release["entries"], release["version"])
            self.assertTrue(release["date"], release["version"])

    def test_dates_never_run_backwards(self):
        """Newest first by version must also read newest first by date, or the popup
        would show a 'newer' release dated before the one under it."""
        releases = changelog.load_changelog(
            Path(__file__).resolve().parent.parent.parent / "docs")
        dates = [r["date"] for r in releases]
        self.assertEqual(dates, sorted(dates, reverse=True))


if __name__ == "__main__":
    unittest.main()
