#!/usr/bin/env python
"""Offer the excretion lines of every drug's stored pharmacokinetics prose (no verdict).

First of the four steps behind the ``drug_excretion`` nodes (``data_generators/excretion.py``):
this fetcher writes ``tools/generated_cache/excretion_worklist.json``, an LLM answers per
drug with ``[{index, qid, aspect, value, amount?}]`` into ``excretion_judged.json``,
``tools/sourcing/apply_excretion.py`` gates and writes, ``recheck_quotes.py`` judges.

The scan is ``fetch_tmax.build`` (Wikipedia #9, Stahl #1, DailyMed #14, BDPM #16, each
drug's one chosen page), with a line offered when it is about elimination
(:data:`EXCRETION_RE`) and names at least one vocabulary value (``excretion.named``, the
very patterns the applier gates on, so "offered" and "accepted" cannot drift). Example
offered line: ``"Excretion | Kidney (80%, mostly as metabolites)"`` ->
``named = ["route:renal"]``.

Usage (repo root), offline::

    python tools/fetch/fetch_excretion.py [--only lithium,amphetamine]

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fetch_tmax  # noqa: E402
from data_generators import excretion as X  # noqa: E402

OUT_PATH = fetch_tmax.ROOT / "tools" / "generated_cache" / "excretion_worklist.json"

# A line worth offering is about the drug leaving the body: an excretion / elimination
# verb, a recovery figure, a clearance, a urine pH, or the drugbox "Excretion" row.
EXCRETION_RE = re.compile(
    r"excret|eliminat|recover|clearance|\burin|f(?:a|ae)?eces|\bpH\b|"
    r"excr[ée]t|[ée]limin|retrouv|clairance", re.IGNORECASE)


def build(only: set[str] | None = None) -> dict[str, dict]:
    """The worklist: ``drug id -> {name, candidates[{corpus, page, line, named}]}``."""
    return fetch_tmax.build(only, EXCRETION_RE, values=X.named)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated drug ids to scope the scan to")
    ap.add_argument("--out", type=Path, default=OUT_PATH, help="worklist output path")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None
    fetch_tmax.write_worklist(build(only), args.out, "an excretion", OUT_PATH, only=only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
