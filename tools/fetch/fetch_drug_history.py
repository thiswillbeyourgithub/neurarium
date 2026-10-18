#!/usr/bin/env python
"""Build the drug regulatory-history worklist (first approval + withdrawals).

Two node kinds (``drug_first_approval``, ``drug_withdrawals``; vocabularies in
``tools/data_generators/history.py``) come from the stored Wikipedia articles: the
English one (corpus #9 ``wikipedia_pharm``, ``data_sources/wikipedia/pages/<slug>.md``)
first, the French one (corpus #10 ``wikipedia_fr``, ``pages_fr/<slug>.md``) as fallback.

This is the fetch / candidate-extraction half of the usual four-step pipeline and states
**no verdict of its own**: per drug it lists, indexed, every sentence of the article's
lead and history-like sections (EN ``History`` / ``Society and culture`` / ``Legal
status``; FR ``Histoire`` / ``Historique`` / ``Législation`` / ``Société et culture`` /
``Spécialités`` / ``Divers``) that carries a year AND names an approval or a withdrawal
(``history.APPROVAL_RE`` / ``history.WITHDRAWAL_RE``). The LLM pass answers by index
into ``drug_history_judged.json``; ``tools/sourcing/apply_drug_history.py`` gates + writes.

Usage (from the repo root)::

    python tools/fetch/fetch_drug_history.py
    python tools/fetch/fetch_drug_history.py --only nefazodone,sertraline   # merges

Stdlib only, offline; author-side (needs the gitignored ``data_sources/`` trees).

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent   # repo root
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))
import drugs_io  # noqa: E402
import worklist_io  # noqa: E402
from pipeline.judged import ECHO_QID  # noqa: E402
from worklist_io import merge_scoped  # noqa: E402
from lib.corpora import wikipedia as wikistore  # noqa: E402 (page_for)
import fetch_category_worklist as catwl  # noqa: E402 (_fr_slug, PAGES_FR, BRAND_WORKLIST)
from lib.parse import durations  # noqa: E402
from data_generators import history  # noqa: E402

OUT_PATH = ROOT / "tools" / "generated_cache" / "drug_history_worklist.json"

# The level-2 sections (plus the lead, before any) whose sentences are offered. A
# deeper heading (### Legal status) stays inside its level-2 parent.
SECTIONS = {
    "wikipedia_pharm": {"history", "society and culture", "legal status"},
    "wikipedia_fr": {"histoire", "historique", "législation", "société et culture",
                     "spécialités", "divers"},
}
MAX_LINE = 600
INSTRUCTIONS = (
    "Per drug, answer {approval: {index, year, country|null, agency|null} | null, "
    "withdrawals: [{index, year, country, reason}]} by candidate index; each candidate's "
    "`context` is the sentence before it. A withdrawal counts ONLY when the substance "
    "was pulled AS A MARKETED MEDICINE: not a ban of it as a food, a table-salt "
    "substitute or a drink, not a recreational-drug scheduling of a substance that was "
    "never marketed there as a medicine, not a patent expiry or a single product's "
    "brand being discontinued while the drug stays on the market. Omit what does not "
    "qualify.")


def section_sentences(text: str, corpus: str) -> list[str]:
    """Sentences of the lead and of the history-like level-2 sections.

    A page's ``# ...`` level-1 lines are navbox residue (``# WHO-EM ‡ Withdrawn from
    market``), never a section: they close the current one.
    """
    keep = SECTIONS[corpus]
    current: str | None = ""          # "" = the lead
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            current = line[3:].strip().lower()
            continue
        if line.startswith("# "):
            current = None
            continue
        if line.startswith("#") or " | " in line:
            continue
        if current == "" or current in keep:
            lines.append(line)
    return list(durations.sentences("\n".join(lines)))


def candidates_in(text: str, corpus: str, page: str) -> list[dict]:
    """Every offered sentence of one page: a year plus an approval/withdrawal word."""
    out, seen = [], set()
    sents = section_sentences(text, corpus)
    for i, s in enumerate(sents):
        if s in seen or len(s) > MAX_LINE or not history.YEAR_RE.search(s):
            continue
        if not (history.APPROVAL_RE.search(s) or history.WITHDRAWAL_RE.search(s)):
            continue
        seen.add(s)
        # The sentence before, so the judge (and the applier's not-a-medicine gate) can
        # read what a "This practice was banned" refers to.
        out.append({"corpus": corpus, "page": page, "line": s,
                    "context": sents[i - 1] if i else ""})
    return out


def candidates(drug: dict, brand: dict) -> list[dict]:
    """The drug's EN candidates, then its FR ones."""
    out: list[dict] = []
    en = wikistore.page_for(drug)
    if en and os.path.exists(en):
        slug = os.path.splitext(os.path.basename(en))[0]
        out += candidates_in(Path(en).read_text("utf-8", errors="replace"),
                             "wikipedia_pharm", slug)
    fr = catwl._fr_slug(drug, brand)
    if fr:
        out += candidates_in((catwl.PAGES_FR / f"{fr}.md").read_text("utf-8", errors="replace"),
                             "wikipedia_fr", fr)
    return out


def build(only: set[str] | None = None) -> dict:
    """``{vocabulary: {...}, drugs: {id: {name, candidates[]}}}``."""
    brand = (json.loads(catwl.BRAND_WORKLIST.read_text("utf-8"))
             if catwl.BRAND_WORKLIST.exists() else {})
    drugs: dict[str, dict] = {}
    for drug in drugs_io.load_drugs():
        if only and drug["id"] not in only:
            continue
        cands = candidates(drug, brand)
        if cands:
            drugs[drug["id"]] = {"name": drug.get("name") or drug["id"], "candidates": cands}
    vocab = {name: {k: v["en"] for k, v in voc.items()}
             for name, voc in (("countries", history.COUNTRIES),
                               ("agencies", history.AGENCIES),
                               ("reasons", history.WITHDRAWAL_REASONS))}
    return {"instructions": INSTRUCTIONS + ECHO_QID, "vocabulary": vocab, "drugs": drugs}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated drug ids to scope the scan to")
    ap.add_argument("--out", type=Path, default=OUT_PATH, help="worklist output path")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None
    wl = build(only)
    if only and args.out.exists():
        wl = merge_scoped(json.loads(args.out.read_text("utf-8")), wl, "drugs")
    worklist_io.write(args.out, wl)
    n = sum(len(v["candidates"]) for v in wl["drugs"].values())
    print(f"[ok] wrote {args.out}: {len(wl['drugs'])} drugs, {n} candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
