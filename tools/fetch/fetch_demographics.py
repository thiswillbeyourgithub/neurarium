#!/usr/bin/env python
"""Build the ``receptor_demographic`` worklist: candidate sentences per receptor / target.

Fetch / candidate-extraction half of the usual four-step pipeline (see CLAUDE.md "Drugs"),
and it states **no verdict**. Per owner it lists, indexed, every abstract sentence of the
human PET / SPECT papers :data:`PAPERS_BY_OWNER` routes to it (Europe PMC, corpus #17,
``data_sources/europepmc/pages/<pmid>.md``) that carries an age or sex cue. Each candidate
carries the factors its cues hit (``factors``), so the pick (answering by index into
``tools/generated_cache/demographics_judged.json``) and the applier
(``tools/sourcing/apply_demographics.py``) can both check the factor was offered.

Only the abstract is read (the lines before ``fetch_europepmc.FULL_TEXT_MARKER``): it is
where a paper states its finding as a finding.

Usage (from the repo root)::

    python tools/fetch/fetch_europepmc.py          # fetch any new paper first (network)
    python tools/fetch/fetch_demographics.py
    python tools/fetch/fetch_demographics.py --only d2,dat

Stdlib only, offline; author-side (needs the gitignored ``data_sources/europepmc/`` tree).

Built with the help of Claude Code.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
from lib.page_file import read_page  # noqa: E402 (refuses a path-like page)
import fetch_receptor_effects as fre  # noqa: E402 (owners, run_cli)
from fetch_europepmc import FULL_TEXT_MARKER, PAGES_DIR, PAPERS  # noqa: E402

OUT_PATH = ROOT / "tools" / "generated_cache" / "demographics_worklist.json"

# owner id -> the PMIDs (each in fetch_europepmc.PAPERS, with the claim it was added for)
# whose abstract measures that owner's availability across age or sex, in humans.
PAPERS_BY_OWNER: dict[str, tuple[str, ...]] = {
    "d1": ("28599217",),
    "d2": ("28599217", "8684263", "8797238", "7475891", "11016537", "9619148"),
    "d3": ("11016537",),
    "dat": ("28599217", "8053661", "7790941", "10952500"),
    "5ht1a": ("21849982", "11282252", "12414100", "18036835"),
    "5ht2a": ("7475891", "21849982"),
    "sert": ("10924762", "18036835"),
    "net": ("19728366",),
    "mao_b": ("9330975",),
    "mu": ("10360121",),
    "cb1": ("18077184",),
}
assert all(p in PAPERS for ps in PAPERS_BY_OWNER.values() for p in ps), \
    "PAPERS_BY_OWNER names a PMID missing from fetch_europepmc.PAPERS"

# factor -> the words a sentence must carry to be offered for it. Recall over precision:
# the pick step discards a weak hit, a sentence never offered can never be picked.
FACTOR_CUES: dict[str, re.Pattern[str]] = {k: re.compile(v, re.I) for k, v in {
    "age": r"\bage[ds]?\b|\baging|\bageing|age-related|age-associated|older|elderly|"
           r"younger|decade|postmenopausal",
    "sex": r"\bsex|gender|\bwomen\b|\bmen\b|\bfemales?\b|\bmales?\b|postmenopausal",
}.items()}


def factor_hits(line: str) -> list[str]:
    """The factors whose cues ``line`` carries, in vocabulary order."""
    return [f for f, rx in FACTOR_CUES.items() if rx.search(line)]


def abstract_lines(pmid: str, pages: Path = PAGES_DIR) -> list[str]:
    """The abstract sentences of a stored page: after the header block (title +
    ``key: value`` lines, up to the first blank line), before the full-text marker."""
    text = read_page(pages, pmid)
    if text is None:
        return []
    text = text.split(FULL_TEXT_MARKER, 1)[0]
    _, _, body = text.partition("\n\n")
    return [ln.strip() for ln in body.splitlines() if ln.strip()]


def candidates(oid: str, pages: Path = PAGES_DIR) -> list[dict]:
    """Indexed candidate sentences for one owner, in routing order, deduplicated."""
    out, seen = [], set()
    for pmid in PAPERS_BY_OWNER.get(oid, ()):
        for line in abstract_lines(pmid, pages):
            hit = factor_hits(line)
            if hit and (pmid, line) not in seen:
                seen.add((pmid, line))
                out.append({"corpus": "europepmc", "page": pmid, "line": line,
                            "factors": hit})
    return out


def build(only: set[str] | None = None) -> dict:
    """``{"owners": {id: {kind, name, wikipedia, candidates}}}`` for every routed owner
    that is a current receptor / target and has at least one candidate."""
    work = {}
    for oid, owner in fre.owners().items():
        if oid not in PAPERS_BY_OWNER or (only and oid not in only):
            continue
        cands = candidates(oid)
        if cands:
            work[oid] = {**owner, "candidates": cands}
    return {"owners": work}


def main() -> int:
    return fre.run_cli(__doc__, OUT_PATH, build)


if __name__ == "__main__":
    raise SystemExit(main())
