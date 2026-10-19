#!/usr/bin/env python
"""Build the elimination half-life worklist for the drugs Stahl gives none.

``fetch_pharmacokinetics.py`` sources a drug's T½ from its Stahl monograph only, so a
drug Stahl never covers (caffeine, nicotine, MDMA, the dopamine agonists, every
recreational substance) or whose monograph states none (phenelzine, perospirone) has
no ``half_life`` at all. This pass fills that gap from the same three corpora the
time-to-peak pass reads (#9 Wikipedia prose, #1 Stahl, #14 DailyMed, #16 BDPM), reusing
``fetch_tmax``'s scan wholesale: only the fact a line must name changes.

Stahl stays the owner of the T½ it states: a drug whose ``half_life_sources`` already
cite Stahl, on the molecule or on one of its ``formulations[]`` (where the formulation pass
moves a release-specific Stahl T½), is not offered, so this pass never revises a Stahl value and a re-run of
``apply_pharmacokinetics.py`` never collides with it.

Pipeline (the usual four steps)::

    python tools/fetch/fetch_half_life.py            # -> half_life_worklist.json
    <one LLM pass>                                   # -> half_life_judged.json (by index)
    python tools/sourcing/apply_half_life.py --dry-run
    python tools/sourcing/recheck_quotes.py build --kinds drug_half_life ...

Stdlib only; author-side (needs the gitignored ``data_sources/`` trees).

Built with the help of Claude Code.
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fetch_tmax                                                # noqa: E402

OUT_PATH = fetch_tmax.ROOT / "tools" / "generated_cache" / "half_life_worklist.json"

# A line worth offering names an elimination half-life. Permissive like the peak
# pattern (a worklist vetoes nothing): a distribution or absorption half-life is
# offered too and left for the judge to refuse.
HALF_LIFE_RE = re.compile(r"(half[\s-]?li(?:fe|ves)|\bt\s*(?:½|1/2|_?\{?1/2\}?)|"
                          r"\bt-half\b|demi[\s-]?vies?)", re.IGNORECASE)  # FR: #16 RCPs


def stahl_owned(drug: dict) -> bool:
    """Whether the drug's T½ already comes from Stahl, on the molecule or a formulation."""
    holders = [drug, *(drug.get("formulations") or [])]
    return any(s.get("corpus") == "stahl"
               for h in holders for s in h.get("half_life_sources") or [])


def build(only: set[str] | None = None) -> dict[str, dict]:
    """The worklist: ``drug id -> {name, candidates[]}`` for every non-Stahl T½."""
    return fetch_tmax.build(only, HALF_LIFE_RE, stahl_owned)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated drug ids to scope the scan to")
    ap.add_argument("--out", type=Path, default=OUT_PATH, help="worklist output path")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None
    fetch_tmax.write_worklist(build(only), args.out, "a half-life", OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
