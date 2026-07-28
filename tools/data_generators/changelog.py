"""Per-version changelog: the "what's new" bullets the viewer pops up on an update.

Authored one file per released version, ``docs/changelog/<major>.<minor>.<patch>/
changelog.md``, and emitted (newest version first) to ``public/data/changelog.json``,
which the viewer fetches only when the popup opens. ``docs/`` is not web-exposed (only
``public/`` is served), so the emit is what makes the text reachable at all.

The file format, kept deliberately small so writing one is a two-minute job::

    # 3.39.0 (2026-07-28)

    ## Added
    - What a casual visitor gets out of it, one line (2e7c22f, 211e89f)
      fr: La meme chose en francais

* The ``# <version> (<date>)`` title is **required** and must name the directory's own
  version: it carries the release date (there is nowhere else to put it, the emit being
  a plain file copy rather than anything git-aware) and doubles as a copy-paste check.
* ``## <Category>`` opens a section; the category must be one of :data:`CATEGORIES`
  (a closed set so the viewer can label + translate it without parsing prose).
* ``- text`` is one bullet. A trailing ``(sha, sha)`` is the commits it came from;
  the viewer links each to the source repo when one is configured.
* The indented ``fr:`` line under a bullet is its French. It is **required**: every
  display string in this project ships in both languages or the build raises.

Written with the help of Claude Code.
"""
from __future__ import annotations

import re
from datetime import date as _date
from pathlib import Path
from typing import Any

# The categories a bullet can sit under. Closed on purpose: the labels are UI strings
# (`changelog.cat.*` in js/i18n.js), not data, so a new category is a deliberate
# two-file change rather than a typo in a heading. Within a release the viewer keeps
# the authored order, so this tuple is the vocabulary, not the running order.
CATEGORIES = ("added", "improved", "fixed", "data", "docs")

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_TITLE_RE = re.compile(r"^#\s+(\d+\.\d+\.\d+)\s+\((\d{4}-\d{2}-\d{2})\)\s*$")
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*?)\s*$")
_FR_RE = re.compile(r"^\s+fr:\s*(.+?)\s*$")
_COMMITS_RE = re.compile(r"\s*\(([0-9a-f]{7,40}(?:\s*,\s*[0-9a-f]{7,40})*)\)\s*$", re.I)


def version_key(version: str) -> tuple[int, int, int]:
    """``"3.39.0" -> (3, 39, 0)``, for ordering. Raises on a non-semver string."""
    if not _VERSION_RE.match(version):
        raise ValueError(f"changelog: {version!r} is not a major.minor.patch version")
    return tuple(int(p) for p in version.split("."))  # type: ignore[return-value]


def parse_changelog(text: str, where: str) -> dict[str, Any]:
    """Parse one ``changelog.md`` body into ``{"version", "date", "entries"}``.

    Every failure is loud and names the file + line: a changelog that silently ate a
    bullet would be worse than no changelog, since nobody re-reads the emitted JSON.
    """
    entries: list[dict[str, Any]] = []
    category: str | None = None
    version: str | None = None
    released: str | None = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("#") and not line.startswith("##"):
            title = _TITLE_RE.match(line)
            if not title:
                raise ValueError(
                    f"{where}:{lineno}: the title must read '# <version> (YYYY-MM-DD)', "
                    f"got {line!r}")
            if version is not None:
                raise ValueError(f"{where}:{lineno}: a second '# <version>' title")
            version, released = title.group(1), title.group(2)
            try:
                _date.fromisoformat(released)
            except ValueError:
                raise ValueError(f"{where}:{lineno}: {released!r} is not a real date") from None
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            category = heading.group(1).strip().lower()
            if category not in CATEGORIES:
                raise ValueError(
                    f"{where}:{lineno}: unknown category {heading.group(1)!r} "
                    f"(expected one of {', '.join(CATEGORIES)})")
            continue
        french = _FR_RE.match(raw)
        if french:
            if not entries:
                raise ValueError(f"{where}:{lineno}: 'fr:' line before any bullet")
            if entries[-1]["text"].get("fr"):
                raise ValueError(f"{where}:{lineno}: this bullet already has a French line")
            entries[-1]["text"]["fr"] = french.group(1)
            continue
        bullet = _BULLET_RE.match(line)
        if not bullet:
            raise ValueError(f"{where}:{lineno}: not a heading, a bullet or an 'fr:' "
                             f"line: {line!r}")
        if category is None:
            raise ValueError(f"{where}:{lineno}: bullet before any '## Category' heading")
        body = bullet.group(1)
        commits: list[str] = []
        found = _COMMITS_RE.search(body)
        if found:
            commits = [c.strip().lower() for c in found.group(1).split(",")]
            body = body[:found.start()].rstrip()
        if not body:
            raise ValueError(f"{where}:{lineno}: bullet has no text")
        entries.append({"category": category, "text": {"en": body}, "commits": commits})

    missing = [e["text"]["en"] for e in entries if not e["text"].get("fr")]
    if missing:
        raise ValueError(f"{where}: {len(missing)} bullet(s) have no 'fr:' line, "
                         f"starting with {missing[0]!r}")
    if not entries:
        raise ValueError(f"{where}: no bullets (an empty changelog is not a release note)")
    if version is None:
        raise ValueError(f"{where}: no '# <version> (YYYY-MM-DD)' title, so no release date")
    return {"version": version, "date": released, "entries": entries}


def load_changelog(docs_dir: Path) -> list[dict[str, Any]]:
    """Every ``docs/changelog/<version>/changelog.md``, newest version first.

    Returns ``[]`` when the tree does not exist yet, so a checkout without it still
    generates (the viewer then simply has nothing to show).
    """
    root = docs_dir / "changelog"
    if not root.is_dir():
        return []
    releases = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        key = version_key(entry.name)          # raises on a mis-named directory
        md = entry / "changelog.md"
        if not md.exists():
            raise ValueError(f"changelog: {entry.name}/ has no changelog.md")
        rel = f"docs/changelog/{entry.name}/changelog.md"
        parsed = parse_changelog(md.read_text(encoding="utf-8"), rel)
        if parsed["version"] != entry.name:
            raise ValueError(f"{rel}: titled {parsed['version']} but sits in "
                             f"{entry.name}/ (one of the two is a copy-paste slip)")
        releases.append((key, {
            "version": entry.name,
            "date": parsed["date"],
            # `text` is already the {en, fr} shape the serializer externalizes: the
            # French rides beside its English here rather than in i18n.py's global FR
            # table, because a release note is written once and never reused.
            "entries": parsed["entries"],
        }))
    releases.sort(key=lambda pair: pair[0], reverse=True)
    return [release for _key, release in releases]
