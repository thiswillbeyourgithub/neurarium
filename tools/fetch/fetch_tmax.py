#!/usr/bin/env python
"""Build the time-to-peak (Tmax) worklist from the four corpora already on disk.

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
``tools/generated_cache/tmax_worklist.json``. Four corpora are scanned, because none
covers the roster alone (measured over 301 drugs: Wikipedia prose reaches 102, Stahl 13,
and 190 state it nowhere, which is what the labels are here for):

* **#9 ``wikipedia_pharm``** (``page`` = the article slug), the drug's own stored
  English article, which states it as prose ("reaches peak levels after 1.0 to 2.5
  hours"). Every roster article is already stored, so this pass is fully offline.
* **#1 ``stahl``** (``page`` = a page number), the monograph's Pharmacokinetics
  bullets, which state it on the newer monographs only.
* **#14 ``dailymed``** (``page`` = a label set id), the US prescribing label's
  pharmacokinetics section, which states a Tmax for essentially every oral drug
  marketed in the US and is what reaches the drugs the two above miss. Stored by
  ``tools/fetch/fetch_dailymed.py``, which picks one label per drug; this pass only
  reads what that fetcher put on disk, so it stays offline too.
* **#16 ``bdpm``** (``page`` = a CIS code), the French summary of product
  characteristics (RCP) section 5.2, in French, stored by ``tools/fetch/fetch_bdpm.py``
  (one product per drug, like the labels above). It reaches the European-only drugs no
  US label exists for; its lines are parsed by ``durations_in_fr``.

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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))

from lib import drugs_io                                                 # noqa: E402
from lib import stahl_index                                              # noqa: E402 (the one INDEX.md reader)
from lib.page_file import page_file, page_path, read_page_file  # noqa: E402 (refuses a path-like page)
from lib import worklist_io  # noqa: E402
from lib.corpora import wikipedia as wikistore                            # noqa: E402 (page_for)
from lib.parse.durations import PEAK_RE, durations_in, durations_in_fr, sentences  # noqa: E402
import fetch_pharmacokinetics as pk                              # noqa: E402 (spans, units)

OUT_PATH = ROOT / "tools" / "generated_cache" / "tmax_worklist.json"
DAILYMED_PAGES = ROOT / "data_sources" / "dailymed" / "pages"
DAILYMED_LABELS = ROOT / "tools" / "generated_cache" / "dailymed_labels.json"

BDPM_PAGES = ROOT / "data_sources" / "bdpm" / "pages"
BDPM_LABELS = ROOT / "tools" / "generated_cache" / "bdpm_labels.json"

# Each fetcher's drug -> chosen-label map, read once per process (the worklist walks
# every drug, and the maps are small).
_LABELS: dict[Path, dict] = {}


# A candidate line longer than this is a paragraph the page happens to hold on one
# line, not a sentence: it would make a quote nobody can check by eye.
MAX_LINE = 400


def candidates_in(text: str, corpus: str, page, pattern=PEAK_RE,
                  durations=durations_in) -> list[dict]:
    """Every ``pattern``-naming, duration-carrying candidate of one page, deduplicated.

    ``pattern`` names the fact the line must be about (a peak here, a half-life for
    ``fetch_half_life.py``, which reuses this whole scan); ``durations`` parses the
    page's language (``durations_in_fr`` for a French RCP).
    """
    out: list[dict] = []
    seen: set[str] = set()
    for s in sentences(text):
        if len(s) > MAX_LINE or s in seen or not pattern.search(s):
            continue
        durs = durations(s)
        if not durs:
            continue
        seen.add(s)
        out.append({"corpus": corpus, "page": page, "line": s, "durations": durs})
    return out


def wikipedia_candidates(drug: dict, pattern=PEAK_RE) -> list[dict]:
    """Candidates from the drug's own stored English article (corpus #9)."""
    path = wikistore.page_for(drug)
    if not path or not os.path.exists(path):
        return []
    slug = os.path.splitext(os.path.basename(path))[0]
    return candidates_in(read_page_file(path), "wikipedia_pharm", slug, pattern)


def stahl_candidates(drug: dict, spans: dict, pattern=PEAK_RE) -> list[dict]:
    """Candidates from the drug's Stahl monograph span (corpus #1)."""
    span = spans.get(pk._norm_name(drug.get("name") or ""))
    if not span:
        return []
    out: list[dict] = []
    for page in range(span[0], span[1] + 1):
        path = page_path(stahl_index.PAGES, page)
        if path.exists():
            out += candidates_in(read_page_file(path),
                                 "stahl", page, pattern)
    return out


def _label_candidates(drug: dict, labels_path: Path, key: str, pages: Path,
                      corpus: str, pattern, durations=durations_in) -> list[dict]:
    """Candidates from the one label page a corpus fetcher chose for this drug.

    The choice is whichever entry the fetcher recorded in its ``*_labels.json``
    (``fetch_dailymed.py`` / ``fetch_bdpm.py``), so it is made once, reviewably, in the
    fetcher rather than re-litigated here. ``key`` names the page id field.
    """
    if labels_path not in _LABELS:
        _LABELS[labels_path] = (json.loads(labels_path.read_text(encoding="utf-8"))
                                if labels_path.exists() else {})
    page = (_LABELS[labels_path].get(drug["id"]) or {}).get(key)
    path = page_file(pages, page)
    if not path or not path.exists():
        return []
    return candidates_in(read_page_file(path),
                         corpus, page, pattern, durations)


def bdpm_candidates(drug: dict, pattern=PEAK_RE) -> list[dict]:
    """Candidates from the drug's stored French RCP section 5.2 (corpus #16)."""
    return _label_candidates(drug, BDPM_LABELS, "cis", BDPM_PAGES, "bdpm", pattern,
                             durations_in_fr)


def dailymed_candidates(drug: dict, pattern=PEAK_RE) -> list[dict]:
    """Candidates from the drug's stored US prescribing label (corpus #14)."""
    return _label_candidates(drug, DAILYMED_LABELS, "setid", DAILYMED_PAGES, "dailymed",
                             pattern)


def build(only: set[str] | None = None, pattern=PEAK_RE, skip=None) -> dict[str, dict]:
    """The worklist: ``drug id -> {name, candidates[]}``, drugs with none omitted.

    ``skip(drug)`` true leaves a drug out (a fact another pass already owns).
    """
    spans = pk.load_index() if stahl_index.INDEX.exists() else {}
    worklist: dict[str, dict] = {}
    for drug in drugs_io.load_drugs():
        if only and drug["id"] not in only:
            continue
        if skip and skip(drug):
            continue
        # The article first: it is where this fact overwhelmingly lives, so the judged
        # index usually lands on candidate 0 and a Stahl line only corroborates it.
        # The label comes last for the same reason and not because it is weaker: it is
        # the primary source, but it is also the verbose one (a whole 12.3 section),
        # and putting it first would push the one-sentence answers down the list.
        cands = (wikipedia_candidates(drug, pattern)
                 + stahl_candidates(drug, spans, pattern)
                 + dailymed_candidates(drug, pattern)
                 + bdpm_candidates(drug, pattern))
        if cands:
            worklist[drug["id"]] = {"name": drug.get("name") or drug["id"],
                                    "candidates": cands}
    return worklist


def write_worklist(worklist: dict, out: Path, what: str) -> None:
    """Write a worklist and print its per-corpus candidate counts."""
    worklist_io.write(out, worklist)
    n_cand = sum(len(v["candidates"]) for v in worklist.values())
    by_corpus: dict[str, int] = {}
    for v in worklist.values():
        for c in v["candidates"]:
            by_corpus[c["corpus"]] = by_corpus.get(c["corpus"], 0) + 1
    total = len(drugs_io.load_drugs())
    shown = worklist_io.shown(out.resolve(), ROOT)
    print(f"[ok] wrote {shown}: {len(worklist)} of {total} drugs "
          f"offer {what} line ({n_cand} candidates)")
    for corpus, n in sorted(by_corpus.items()):
        print(f"  {corpus:<18} {n}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated drug ids to scope the scan to")
    ap.add_argument("--out", type=Path, default=OUT_PATH, help="worklist output path")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None

    write_worklist(build(only), args.out, "a time-to-peak")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
