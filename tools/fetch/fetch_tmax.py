#!/usr/bin/env python
"""Build the time-to-peak (Tmax) worklist from the two corpora already on disk.

The simulation gives **every** drug one assumed 2 h time-to-peak (``TMAX_HOURS`` in
``js/sim-model.js``), so a drug that peaks in 20 minutes and one that peaks in 8 hours
draw the same plasma curve. Tmax is the per-drug fact that fixes it, and it is the only
piece of the missing pharmacokinetics that is actually sourceable (see
``docs/SOURCING_GAPS.md``: the rest of the chain to a real concentration needs Kp,uu,
which has no open source at all).

This is the fetch / candidate-extraction half of the usual four-step pipeline, and it
states **no verdict of its own**: it offers, per drug, every line of the drug's own
pages that names a peak AND carries a duration, already confirmed verbatim on a real
page, and leaves the choosing to the LLM pass that reads
``tools/generated_cache/tmax_worklist.json``. Two corpora are scanned, because neither
covers the roster alone (measured over 301 drugs: Wikipedia prose reaches 102, Stahl
13, and 190 state it nowhere):

* **#9 ``wikipedia_pharm``** (``page`` = the article slug), the drug's own stored
  English article, which states it as prose ("reaches peak levels after 1.0 to 2.5
  hours"). Every roster article is already stored, so this pass is fully offline.
* **#1 ``stahl``** (``page`` = a page number), the monograph's Pharmacokinetics
  bullets, which state it on the newer monographs only.

The drugbox is deliberately NOT read. It has no Tmax row at all, and its ``Onset of
action`` row is a different fact: on 60 of its 76 rows it is the clinical onset
(alprazolam's "30-60 minutes" is when it works, not when it peaks), so taking that row
would publish onset as peak. Only a row explicitly annotated as a peak is a Tmax, and
those 16 come through the prose scan anyway, as the flattened table line.

Each candidate is pre-parsed into every ``{hours, hours_max?}`` duration it contains
(reusing ``fetch_pharmacokinetics.parse_duration``'s unit table), because the applier
gates the judged number against the durations actually present in the quote: the LLM's
job is to pick WHICH line is the drug's own oral time-to-peak, never to compute a
number.

Usage (from the repo root)::

    python tools/fetch/fetch_tmax.py                  # -> the worklist
    python tools/fetch/fetch_tmax.py --only olanzapine,fluoxetine

Stdlib only; author-side (needs the gitignored ``data_sources/`` trees).

Built with the help of Claude Code.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))

import drugs_io                                                 # noqa: E402
import fetch_cyp_wikipedia as cypwiki                            # noqa: E402 (page_for)
import fetch_pharmacokinetics as pk                              # noqa: E402 (spans, units)

OUT_PATH = ROOT / "tools" / "generated_cache" / "tmax_worklist.json"

# A line worth offering: it names a PEAK. Kept permissive on purpose (a worklist
# vetoes nothing), but it must name the peak itself, never merely an "onset", which is
# the clinical-effect fact this pass must not confuse with a Tmax.
PEAK_RE = re.compile(
    r"(t\s*_?max\b|\bc\s*max\b|peak\s+(?:plasma|serum|blood)|"
    r"peak\s+(?:plasma\s+|serum\s+)?(?:concentration|level)|"
    r"maximum\s+(?:plasma\s+|serum\s+)?concentration|time\s+to\s+peak|"
    r"reach(?:es|ed|ing)?\s+(?:its\s+)?peak)", re.IGNORECASE)

# A candidate line longer than this is a paragraph the page happens to hold on one
# line, not a sentence: it would make a quote nobody can check by eye.
MAX_LINE = 400


def durations_in(line: str) -> list[dict]:
    """Every ``{hours, hours_max?}`` duration stated in one line, left to right.

    The applier gates a judged Tmax against this list, so a number the quote does not
    contain cannot be written. Reuses ``fetch_pharmacokinetics``'s unit table rather
    than restating it, since the two passes must agree on what "2-4 h" means.

    Parameters
    ----------
    line
        A candidate line.

    Returns
    -------
    list of dict
        One record per duration found; empty when the line states none.
    """
    out: list[dict] = []
    for m in pk._DURATION.finditer(line):
        unit = pk._UNIT_HOURS[m.group("unit").lower()]
        lo = float(m.group("lo")) * unit
        rec = {"hours": round(lo, 3)}
        hi = m.group("hi")
        if hi:
            hi_h = float(hi) * unit
            if hi_h >= lo:
                rec["hours_max"] = round(hi_h, 3)
        out.append(rec)
    return out


def sentences(text: str):
    """Yield the page's checkable units: one sentence, or one flattened table row.

    A stored article keeps each table as ``"cell | cell | ..."`` lines, which carry no
    sentence punctuation, so splitting on ``.``/``;`` leaves such a row whole and it
    stays quotable verbatim exactly as the Ki passes quote it.
    """
    for raw in text.splitlines():
        line = raw.strip().lstrip("#*->").strip()
        if not line:
            continue
        for part in re.split(r"(?<=[.;])\s+", line):
            part = part.strip()
            if part:
                yield part


def candidates_in(text: str, corpus: str, page) -> list[dict]:
    """Every peak-naming, duration-carrying candidate of one page, deduplicated."""
    out: list[dict] = []
    seen: set[str] = set()
    for s in sentences(text):
        if len(s) > MAX_LINE or s in seen or not PEAK_RE.search(s):
            continue
        durs = durations_in(s)
        if not durs:
            continue
        seen.add(s)
        out.append({"corpus": corpus, "page": page, "line": s, "durations": durs})
    return out


def wikipedia_candidates(drug: dict) -> list[dict]:
    """Candidates from the drug's own stored English article (corpus #9)."""
    path = cypwiki.page_for(drug)
    if not path or not os.path.exists(path):
        return []
    slug = os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8", errors="replace") as f:
        return candidates_in(f.read(), "wikipedia_pharm", slug)


def stahl_candidates(drug: dict, spans: dict) -> list[dict]:
    """Candidates from the drug's Stahl monograph span (corpus #1)."""
    span = spans.get(pk._norm_name(drug.get("name") or ""))
    if not span:
        return []
    out: list[dict] = []
    for page in range(span[0], span[1] + 1):
        path = pk.PAGES_DIR / f"{page}.md"
        if path.exists():
            out += candidates_in(path.read_text(encoding="utf-8", errors="replace"),
                                 "stahl", page)
    return out


def build(only: set[str] | None = None) -> dict[str, dict]:
    """The worklist: ``drug id -> {name, candidates[]}``, drugs with none omitted."""
    spans = pk.load_index() if pk.INDEX_PATH.exists() else {}
    worklist: dict[str, dict] = {}
    for drug in drugs_io.load_drugs():
        if only and drug["id"] not in only:
            continue
        # The article first: it is where this fact overwhelmingly lives, so the judged
        # index usually lands on candidate 0 and a Stahl line only corroborates it.
        cands = wikipedia_candidates(drug) + stahl_candidates(drug, spans)
        if cands:
            worklist[drug["id"]] = {"name": drug.get("name") or drug["id"],
                                    "candidates": cands}
    return worklist


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated drug ids to scope the scan to")
    ap.add_argument("--out", type=Path, default=OUT_PATH, help="worklist output path")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None

    worklist = build(only)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(worklist, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    n_cand = sum(len(v["candidates"]) for v in worklist.values())
    by_corpus: dict[str, int] = {}
    for v in worklist.values():
        for c in v["candidates"]:
            by_corpus[c["corpus"]] = by_corpus.get(c["corpus"], 0) + 1
    total = len(drugs_io.load_drugs())
    print(f"[ok] wrote {args.out.relative_to(ROOT)}: {len(worklist)} of {total} drugs "
          f"offer a time-to-peak line ({n_cand} candidates)")
    for corpus, n in sorted(by_corpus.items()):
        print(f"  {corpus:<18} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
