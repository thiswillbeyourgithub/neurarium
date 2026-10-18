"""Family 9: the release notes per version.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import json
import re
from datetime import date

# The changelog category vocabulary, imported rather than restated: the authoring
# module owns it (adding one there must not need an edit here).
from data_generators.changelog import CATEGORIES as CHANGELOG_CATEGORIES

from .common import DATA_DIR, REPO_ROOT


_APP_VERSION_RE = re.compile(r"""__APP_VERSION__\s*=\s*["']([^"']+)["']""")


def check_changelog(report):
    """Family 9: the release notes the viewer pops up after an update.

    Cheap structural checks (well-formed, ordered, no duplicates), plus the one that
    actually matters: the running version must have notes. Bumping version.js without
    writing them ships an update that announces nothing, and nobody notices until a
    visitor sees an empty popup."""
    report.header("9. Changelog (release notes per version)")
    before = report.errors
    path = DATA_DIR / "changelog.json"
    version_js = REPO_ROOT / "public" / "version.js"
    if not path.exists():
        report.error("public/data/changelog.json is missing (run generate_data.py)")
        return
    try:
        releases = json.loads(path.read_text(encoding="utf-8")).get("versions") or []
    except json.JSONDecodeError as exc:
        report.error(f"changelog.json is not valid JSON: {exc}")
        return

    keys, dates, seen = [], [], set()
    for release in releases:
        version = release.get("version")
        try:
            key = tuple(int(p) for p in re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version).groups())
        except (AttributeError, TypeError):
            report.error(f"changelog: {version!r} is not a major.minor.patch version")
            continue
        if version in seen:
            report.error(f"changelog: version {version} appears twice")
        seen.add(version)
        keys.append(key)
        released = str(release.get("date") or "")
        try:
            date.fromisoformat(released)
            dates.append(released)
        except ValueError:
            report.error(f"changelog {version}: {released!r} is not a YYYY-MM-DD date")
        if not release.get("entries"):
            report.error(f"changelog {version}: no entries (an empty release note)")
        for entry in release.get("entries") or []:
            if entry.get("category") not in CHANGELOG_CATEGORIES:
                report.error(f"changelog {version}: unknown category "
                             f"{entry.get('category')!r}")
            if not str(entry.get("text") or "").strip():
                report.error(f"changelog {version}: an entry has no text")
            for sha in entry.get("commits") or []:
                if not re.fullmatch(r"[0-9a-f]{7,40}", str(sha)):
                    report.error(f"changelog {version}: {sha!r} is not a commit sha")
    if keys != sorted(keys, reverse=True):
        report.error("changelog: versions are not newest-first (the viewer relies on "
                     "the order to show the releases since a visitor's last one)")
    if dates != sorted(dates, reverse=True):
        report.error("changelog: the release dates run backwards somewhere, so a "
                     "release would sit above an older version but carry an earlier date")

    match = _APP_VERSION_RE.search(version_js.read_text(encoding="utf-8")) \
        if version_js.exists() else None
    if not match:
        # An error, not a warning: version.js is committed and required, so an
        # unreadable one is a real defect (it once shipped EMPTY for two releases,
        # unnoticed because this only warned). With no version the panel header and
        # loading overlay lose their version tag and the What's new popup can never
        # decide a release is new, so a visitor is never told anything shipped.
        report.error("public/version.js: could not read __APP_VERSION__. The version "
                     "is what a visitor's browser compares against to see what is new, "
                     "so a build without one announces nothing")
    elif match.group(1) not in seen:
        report.error(f"version.js is {match.group(1)} but docs/changelog/{match.group(1)}/"
                     f"changelog.md does not exist. Every released version needs notes, "
                     f"else the What's new popup announces an update it cannot describe")
    if report.errors == before:
        report.ok(f"{len(releases)} version(s) of release notes, newest first, "
                  f"current version covered")
