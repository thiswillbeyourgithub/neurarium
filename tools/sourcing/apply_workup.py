#!/usr/bin/env python
"""Apply the judged pre-prescription workup picks, quote-gated: the ``drug_workup`` nodes.

Second half of the pass started by ``tools/fetch/fetch_workup.py``: the fetcher wrote
the RCP 4.2 / 4.3 / 4.4 lines that may state a test (no verdict), an LLM answered per
drug with ``[{index, test, timing}]`` into ``tools/generated_cache/workup_judged.json``,
and this applier is the **sole writer** of ``tools/generated_cache/workup.json``.

An index, never a quote string (a paraphrase is then not expressible), and every pick
re-gated here rather than trusted from the judged file:

1. the drug is in the dataset;
2. the drug is **offered** by a fresh ``fetch_workup.build()``;
3. the index resolves into that drug's candidate list;
4. ``test`` is in ``workup.TESTS`` and the quote itself names it (``workup.attests``);
5. ``timing`` is in ``workup.TIMINGS`` and the quote, or the RCP sub-heading it sits
   under (re-read off the page by the fetcher, not taken from the judged file), carries
   that timing's wording;
6. the quote is verbatim, under ``lib.quote_match.normalize_for_match``, on the corpus #24
   page it cites (``data_sources/bdpm/pages_rcp4/<page>.md``);
7. an optional ``condition`` (the label asks for the check only in some patients:
   "chez les patients diabétiques") is a verbatim span of that same quote.

The judged file holds a key for **every** offered drug, ``[]`` meaning "judged, the
label asks for nothing the vocabulary covers", so an undecided drug (absent) is told
apart from a judged one: :func:`undecided` lists them and the run reports them.

One node per (drug, test, timing): a second accepted quote for the same node is
appended to its sources, never a second node. An unconditional pick outranks a
conditional one for the same node (``_merge``). Idempotent: the output is rebuilt from
the judged file on every run. It writes no ``llm`` stamp, so
``tools/sourcing/recheck_quotes.py`` (``--kinds drug_workup``) must run afterwards or
``check_data.py`` family 5 flags the citations as extracted-but-unjudged.

Usage (repo root)::

    python tools/sourcing/apply_workup.py --dry-run
    python tools/sourcing/apply_workup.py

Stdlib only; author-side (refuses to write when the page tree is missing, since the
quote gate could not run). Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))

from lib import drugs_io  # noqa: E402
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
from lib.quote_match import normalize_for_match  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402
from pipeline.judged import resolve  # noqa: E402
import fetch_workup  # noqa: E402
from data_generators import workup as W  # noqa: E402
from data_generators.corpora import SOURCE_CORPORA  # noqa: E402
from lib import cache_io  # noqa: E402

JUDGED_PATH = ROOT / "tools" / "generated_cache" / "workup_judged.json"
CORPUS = fetch_workup.CORPUS



def gate(judged: dict, offered: dict, drug_ids: set[str], pages: PageGate
         ) -> tuple[dict[str, list[dict]], list[str]]:
    """Gate every judged pick, re-finding each quote on its ``pages`` (corpus #24).

    Returns ``({drug: [{test, timing, sources}]}, rejections)``.
    """
    out: dict[str, list[dict]] = {}
    rejected: list[str] = []
    for did, picks in sorted(judged.items()):
        if did not in drug_ids:
            rejected.append(f"{did}: not a dataset drug")
            continue
        entry = offered.get(did)
        if not entry:
            rejected.append(f"{did}: the fetcher offers no candidate for this drug")
            continue
        nodes: dict[tuple[str, str], dict] = {}
        for p in picks:
            what = f"{did}[{p.get('index')}] {p.get('test')}/{p.get('timing')}"
            cand, why = resolve(entry["candidates"], p)
            if why:
                rejected.append(f"{what}: {why}")
                continue
            test, timing = p.get("test"), p.get("timing")
            if not W.attests(W.TESTS, test, cand["quote"]):
                rejected.append(f"{what}: the quote does not name this test")
                continue
            if not W.attests(W.TIMINGS, timing, cand["quote"], cand["under"]):
                rejected.append(f"{what}: neither the quote nor its heading states this timing")
                continue
            if not pages.on_page(CORPUS, entry["page"], cand["quote"]):
                rejected.append(f"{what}: the quote is not verbatim on its page")
                continue
            cond = " ".join((p.get("condition") or "").split())
            if p.get("condition") is not None and (
                    len(cond) < 4 or normalize_for_match(cond) not in normalize_for_match(cand["quote"])):
                rejected.append(f"{what}: condition is not a span of the quote")
                continue
            src = {"corpus": CORPUS, "page": entry["page"], "quote": cand["quote"],
                   "provenance": "verified"}
            node = nodes.setdefault((test, timing), {"test": test, "timing": timing,
                                                     "plain": [], "conditional": []})
            if cond:
                node["conditional"].append((cond, src))
            elif src not in node["plain"]:
                node["plain"].append(src)
        if nodes:
            out[did] = [_merge(n) for n in nodes.values()]
    return out, rejected


def undecided(judged: dict, offered: dict) -> list[str]:
    """The offered drugs the judged file holds no decision for (not even ``[]``)."""
    return sorted(set(offered) - set(judged))


def _merge(node: dict) -> dict:
    """One (test, timing) node: an unconditional ask outranks a conditional one (the
    check applies to everyone, so its conditional quotes add nothing); otherwise the
    node is conditional, carrying each distinct condition once."""
    row = {"test": node["test"], "timing": node["timing"]}
    if node["plain"]:
        return {**row, "sources": node["plain"]}
    conds, srcs = [], []
    for cond, src in node["conditional"]:
        if cond not in conds:
            conds.append(cond)
        if src not in srcs:
            srcs.append(src)
    return {**row, "conditions": conds, "sources": srcs}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()
    pages_dir = ROOT / SOURCE_CORPORA[CORPUS]["pages_dir"]
    if not pages_dir.is_dir():
        print(f"[error] {pages_dir.relative_to(ROOT)} missing: the quote gate cannot run",
              file=sys.stderr)
        return 1
    judged = worklist_io.read(JUDGED_PATH)
    pages = PageGate({CORPUS: pages_dir})
    drug_ids = {d["id"] for d in drugs_io.load_drugs()}
    offered = fetch_workup.build()
    out, rejected = gate(judged, offered, drug_ids, pages)
    for r in rejected:
        print(f"[reject] {r}")
    pending = undecided(judged, offered)
    if pending:
        print(f"[warn] {len(pending)} offered drug(s) never judged: {', '.join(pending)}")
    n = sum(len(v) for v in out.values())
    print(f"[ok] {n} workup node(s) over {len(out)} drug(s); {len(rejected)} rejected")
    if not args.dry_run:
        cache_io.write(W.CACHE, {"drugs": out})
        print(f"[ok] wrote {W.CACHE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
