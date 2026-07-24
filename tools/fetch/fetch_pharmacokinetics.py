#!/usr/bin/env python
"""Build the pharmacokinetics worklist (T½ + active metabolites) from Stahl.

This is the fetch / candidate-extraction half of an LLM-extract / quote-gate pipeline
(mirroring the FR-brand pipeline in fetch_brand_names.py -> apply_brand_names.py) for
two new sourced node kinds on each drug:

* ``half_life`` (kind ``drug_half_life``): the elimination half-life (T½), stored as
  canonical hours (+ optional range); and
* ``metabolites`` (kind ``drug_metabolites``): the drug's named active metabolites,
  each an identity node ("<name> is an active metabolite of <drug>").

Stahl's Prescriber's Guide states both in every monograph's Pharmacokinetics prose,
e.g. "Elimination half-life approximately 24-48 hours", "active metabolite
(norfluoxetine)", or the explicit negative "No active metabolites". This pass, for
every dataset drug that maps to a Stahl monograph (recreational / non-Stahl drugs are
skipped; their PK comes from a later Wikipedia pass):

* resolves the drug's Stahl page span from ``data_sources/books/stahl/INDEX.md``;
* scans those pages for every line mentioning a half-life or a metabolite, keeping the
  verbatim line + its page (the quote-gate needs the exact on-page text); and
* deterministically PRE-PARSES each half-life line into ``{hours, hours_max?}`` as a
  hint (unit-converting days / weeks / minutes), so the downstream LLM mostly confirms
  rather than computes.

The worklist (``tools/generated_cache/pk_worklist.json``) then goes to a single LLM
pass that reads only these short candidate lines and returns, per drug, the drug's own
elimination T½ (picking the parent line, not a metabolite's) and its active-metabolite
names (+ each metabolite's own T½ when stated); ``apply_pharmacokinetics.py`` then
quote-gates every returned quote verbatim on the Stahl page before writing it. No book
bytes are redistributed: only the worklist of short candidate lines is emitted, and it
lives in the gitignored generated_cache alongside the other author-side worklists.

Usage (from the repo root): python tools/fetch/fetch_pharmacokinetics.py
Stdlib only; author-side (needs the gitignored data_sources/books/stahl tree).
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
sys.path.insert(0, str(ROOT / "tools"))
import drugs_io                                                 # noqa: E402

STAHL_DIR = ROOT / "data_sources" / "books" / "stahl"
INDEX_PATH = STAHL_DIR / "INDEX.md"
PAGES_DIR = STAHL_DIR / "pages"
OUT_PATH = ROOT / "tools" / "generated_cache" / "pk_worklist.json"

# INDEX.md row: "| 5 | Amitriptyline | [39-46](pages/39.md) |" (or a single "[39]").
_INDEX_ROW = re.compile(
    r"^\|\s*\d+\s*\|\s*(?P<name>[^|]+?)\s*\|\s*\[(?P<start>\d+)(?:-(?P<end>\d+))?\]")

# A line worth keeping for the T½ node: mentions a half-life.
_HALF_LIFE = re.compile(r"half-?life", re.IGNORECASE)
# A line worth keeping for the metabolite node: mentions a metabolite / metabolized to
# (the negative "no active metabolites" is kept too: it is a real, useful signal).
_METABOLITE = re.compile(r"metaboli", re.IGNORECASE)

# One number, optionally a range "X-Y" / "X to Y", then a time unit. Handles the en
# dash Stahl uses for ranges ("24-48") and decimals ("2.7 hours").
_DURATION = re.compile(
    r"(?P<lo>\d+(?:\.\d+)?)\s*(?:[-–]|to)?\s*(?P<hi>\d+(?:\.\d+)?)?\s*"
    r"(?P<unit>minute|min|hour|hr|day|week)s?\b",
    re.IGNORECASE,
)
_UNIT_HOURS = {
    "minute": 1 / 60, "min": 1 / 60,
    "hour": 1.0, "hr": 1.0,
    "day": 24.0, "week": 168.0,
}


def _norm_name(s: str) -> str:
    """Fold a drug name for matching (lowercase, alphanumerics only)."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def parse_duration(line: str) -> dict | None:
    """Parse the first duration in ``line`` into ``{hours, hours_max?}`` (or None).

    Chooses the unit from the matched token and converts to canonical hours; a range
    ("24-48 hours") yields ``hours`` + ``hours_max``. Returns None when the line names
    no ``<number> <time-unit>`` duration.

    Parameters
    ----------
    line
        A candidate half-life line.

    Returns
    -------
    dict or None
        ``{"hours": float, "hours_max": float?}`` or None.
    """
    m = _DURATION.search(line)
    if not m:
        return None
    unit = _UNIT_HOURS[m.group("unit").lower()]
    lo = float(m.group("lo")) * unit
    rec = {"hours": round(lo, 3)}
    if m.group("hi"):
        hi = float(m.group("hi")) * unit
        if hi >= lo:
            rec["hours_max"] = round(hi, 3)
    return rec


def load_index() -> dict[str, tuple[int, int]]:
    """Parse INDEX.md into ``normalized drug name -> (start_page, end_page)``."""
    spans: dict[str, tuple[int, int]] = {}
    for line in INDEX_PATH.read_text(encoding="utf-8").splitlines():
        m = _INDEX_ROW.match(line)
        if not m:
            continue
        start = int(m.group("start"))
        end = int(m.group("end") or start)
        spans[_norm_name(m.group("name"))] = (start, end)
    return spans


def scan_pages(start: int, end: int) -> tuple[list[dict], list[dict]]:
    """Scan pages ``start..end`` for half-life + metabolite candidate lines.

    Parameters
    ----------
    start, end
        Inclusive Stahl page range (the ``pages/<n>.md`` files).

    Returns
    -------
    (half_life_candidates, metabolite_candidates)
        Each a list of ``{"page": int, "line": str, "parsed": {...}?}`` (``parsed``
        only on half-life lines that yielded a duration). Duplicate lines are dropped.
    """
    hl: list[dict] = []
    met: list[dict] = []
    seen_hl: set[str] = set()
    seen_met: set[str] = set()
    for page in range(start, end + 1):
        path = PAGES_DIR / f"{page}.md"
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip().lstrip("#*-> ").strip()
            if not line:
                continue
            if _HALF_LIFE.search(line) and line not in seen_hl:
                seen_hl.add(line)
                cand = {"page": page, "line": line}
                parsed = parse_duration(line)
                if parsed:
                    cand["parsed"] = parsed
                hl.append(cand)
            if _METABOLITE.search(line) and line not in seen_met:
                seen_met.add(line)
                met.append({"page": page, "line": line})
    return hl, met


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT_PATH,
                    help="worklist output path")
    args = ap.parse_args()

    if not INDEX_PATH.exists():
        print(f"[error] Stahl INDEX not found at {INDEX_PATH} (author-side tree "
              f"missing); nothing to do.", file=sys.stderr)
        return 1

    spans = load_index()
    drugs = drugs_io.load_drugs()
    worklist: dict[str, dict] = {}
    matched = skipped = 0
    for d in drugs:
        span = spans.get(_norm_name(d["name"]))
        if span is None:
            skipped += 1                                        # non-Stahl drug
            continue
        matched += 1
        hl, met = scan_pages(*span)
        worklist[d["id"]] = {
            "name": d["name"],
            "pages": list(span),
            "half_life_candidates": hl,
            "metabolite_candidates": met,
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(worklist, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    n_hl = sum(1 for v in worklist.values() if v["half_life_candidates"])
    n_met = sum(1 for v in worklist.values() if v["metabolite_candidates"])
    print(f"[ok] wrote {args.out.relative_to(ROOT)}: {matched} Stahl drugs "
          f"({skipped} non-Stahl skipped); {n_hl} have half-life lines, "
          f"{n_met} have metabolite lines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
