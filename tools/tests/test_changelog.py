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


class ParseTest(unittest.TestCase):
    def parse(self, text):
        return changelog.parse_changelog(text, "test.md")

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

    def test_blank_lines_and_a_title_are_ignored(self):
        entries = self.parse("# 3.39.0\n\n## Added\n\n- A\n  fr: A\n\n")
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


if __name__ == "__main__":
    unittest.main()
