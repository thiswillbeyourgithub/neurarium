#!/usr/bin/env python
"""Offer the paper sentences that may say what a drug does to sleep (no verdict).

First of the four steps behind ``drug_sleep`` nodes (``data_generators/sleep.py``): this
fetcher writes ``tools/generated_cache/sleep_worklist.json``, one LLM pass answers per
drug ``[{index, qid, effect, species?}]`` into ``sleep_judged.json``,
``tools/sourcing/apply_sleep.py`` gates and writes, ``recheck_quotes.py`` judges.

One input: every full-text review of corpus #25 ``papers`` (``fetch_papers.PAPERS``),
read through ``lib.corpora.papers.sentences`` (whole verbatim sentences). A sentence is
offered to a roster drug when it speaks of sleep (``sleep.about_sleep``) AND names that
drug by its INN (``drugs_io.unique_name_patterns``), e.g. Wichniak 2017's "Agomelatine
does not suppress REM sleep" goes to agomelatine. A class sentence ("SSRIs strongly
suppress REM sleep") names no roster drug and is never offered. Each candidate carries
its ``pdf_page`` so the picker can read the context (species, dose).

Usage (repo root), offline::

    python tools/fetch/fetch_sleep.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
import fetch_papers  # noqa: E402 (PAPERS)
from data_generators import sleep as S  # noqa: E402
from lib import drugs_io, worklist_io  # noqa: E402
from lib.corpora import papers  # noqa: E402 (sentences)

WORKLIST = ROOT / "tools" / "generated_cache" / "sleep_worklist.json"


def build(drugs: list[dict] | None = None, sentences=papers.sentences,
          paper_keys=None) -> dict[str, dict]:
    """``{drug_id: {candidates: [{index, corpus, page, pdf_page, quote}]}}``, papers in
    ``fetch_papers.PAPERS`` order so a new paper appended there never shifts an index."""
    if drugs is None:
        drugs = drugs_io.load_drugs()
    pats = drugs_io.unique_name_patterns(drugs)
    merged: dict[str, list[dict]] = defaultdict(list)
    for key in paper_keys if paper_keys is not None else fetch_papers.PAPERS:
        for pdf_page, line in sentences(key):
            if not S.about_sleep(line):
                continue
            for did, pat in pats.items():
                if pat.search(line):
                    merged[did].append({"corpus": "papers", "page": key,
                                        "pdf_page": pdf_page, "quote": line})
    out = {}
    for did in sorted(merged):
        seen, cands = set(), []
        for c in merged[did]:
            if (c["page"], c["quote"]) not in seen:
                seen.add((c["page"], c["quote"]))
                cands.append({"index": len(cands), **c})
        out[did] = {"candidates": cands}
    return out


def main() -> int:
    wl = build()
    worklist_io.write(WORKLIST, wl)
    n = sum(len(v["candidates"]) for v in wl.values())
    print(f"[ok] {n} candidate sentence(s) over {len(wl)} drug(s) -> {WORKLIST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
