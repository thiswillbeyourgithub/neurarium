#!/usr/bin/env python
"""Build the prodrug worklist: which drugs are inactive until metabolised, and into what.

A **prodrug** (node kind ``drug_prodrug``) carries no binding of its own: its pharmacology
is its active metabolite's (``metabolites[]``, a linked modeled drug or the metabolite's own
``bindings[]``). The claim is data, not inference, so it needs a quote. This is the
candidate half of the usual four-step pipeline and states **no verdict of its own**: per
drug it lists, indexed, every sentence of the drug's stored English Wikipedia article
(corpus #9 ``wikipedia_pharm``) that says prodrug / inactive / converted, plus the drug's
current metabolites for context. The LLM answers by index into
``tools/generated_cache/prodrug_judged.json``; ``tools/sourcing/apply_prodrug.py`` gates
and writes.

Usage (from the repo root)::

    python tools/fetch/fetch_prodrug_worklist.py
    python tools/fetch/fetch_prodrug_worklist.py --only psilocybin   # merges

Stdlib only, offline; author-side (needs the gitignored ``data_sources/`` tree).

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from lib.page_file import read_page_file  # noqa: E402
from lib import drugs_io  # noqa: E402
from lib import worklist_io  # noqa: E402
from pipeline.judged import ECHO_QID  # noqa: E402
from lib.worklist_io import merge_scoped  # noqa: E402
from lib.corpora import wikipedia as wikistore  # noqa: E402
from lib.parse import durations  # noqa: E402

OUT_PATH = ROOT / "tools" / "generated_cache" / "prodrug_worklist.json"
# Words a prodrug sentence uses. Broad on purpose: the judge and the applier's own
# gate (PRODRUG_RE, re-checked on the picked quote) are the real filter.
PRODRUG_RE = re.compile(
    r"\bpro-?drugs?\b|\b(?:biologically|pharmacologically) inactive\b"
    r"|\binactive (?:until|before|itself)\b", re.I)
MAX_LINE = 600


def candidates(drug: dict) -> list[dict]:
    """Every offered sentence of the drug's own English article."""
    path = wikistore.page_for(drug)
    if not path or not os.path.exists(path):
        return []
    slug = os.path.splitext(os.path.basename(path))[0]
    out, seen = [], set()
    for s in durations.sentences(read_page_file(path)):
        if "|" in s or len(s) > MAX_LINE or s in seen or not PRODRUG_RE.search(s):
            continue
        seen.add(s)
        out.append({"corpus": "wikipedia_pharm", "page": slug, "line": s})
    return out


def build(only: set[str] | None = None) -> dict:
    drugs = {}
    store = {m["id"]: m for m in drugs_io.load_metabolites()}
    for d in drugs_io.load_drugs():
        if only and d["id"] not in only:
            continue
        cands = candidates(d)
        if cands:
            drugs[d["id"]] = {
                "name": d["name"],
                "bindings": len(d.get("bindings") or []),
                "metabolites": [{"name": store[r["id"]]["name"],
                                 "drug_id": store[r["id"]].get("drug_id")}
                                for r in d.get("metabolites") or []],
                "candidates": cands}
    return {"instructions": (
        "Mark a drug a prodrug ONLY when a candidate says the drug ITSELF is inactive "
        "(or is a prodrug) and its effect comes from a named active metabolite. A drug "
        "that is active itself AND has an active metabolite is NOT a prodrug; a sentence "
        "about a different prodrug (an ester of this drug, another molecule) does not "
        "count. Answer {drug_id: {index, metabolite, drug_id|null}} with the metabolite "
        "named in that very sentence; omit a drug that is not a prodrug.") + ECHO_QID,
        "drugs": drugs}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated drug ids (merged into the worklist)")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None
    wl = build(only)
    if only and args.out.exists():
        wl = merge_scoped(json.loads(args.out.read_text("utf-8")), wl, "drugs")
    worklist_io.write(args.out, wl)
    print(f"{len(wl['drugs'])} drugs with candidates -> {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
