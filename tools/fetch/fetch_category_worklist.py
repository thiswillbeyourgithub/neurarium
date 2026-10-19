#!/usr/bin/env python
"""Build the drug-class (category) worklist from the Wikipedia articles already on disk.

A drug's class classification is its own graded node (kind ``drug_categories``). Stahl's
"## Class" bullets source most of the roster (``apply_category_sources.py``), but a drug
with no Stahl monograph has no class line there. An article's opening paragraph almost
always states the class instead ("X is a typical antipsychotic", "un agoniste
dopaminergique"), so this pass offers those sentences.

This is the fetch / candidate-extraction half of the usual four-step pipeline and states
**no verdict of its own**: per drug whose category is not yet verified it lists, indexed,

* the ``Drug class | ...`` infobox row of the English article, when there is one;
* every lead sentence of the English article (corpus #9 ``wikipedia_pharm``,
  ``data_sources/wikipedia/pages/<slug>.md``), i.e. the prose before its first ``##``;
* then every lead sentence of the French article (corpus #10 ``wikipedia_fr``,
  ``data_sources/wikipedia/pages_fr/<slug>.md``), as a fallback.

plus the drug's stored ``categories`` and their human labels. The LLM pass reads
``tools/generated_cache/category_worklist.json`` and answers by candidate index into
``category_judged.json`` (confirm-only: it never changes a category, only points at the
sentence asserting it); ``apply_category_sources.py --wikipedia`` gates and writes.

Usage (from the repo root)::

    python tools/fetch/fetch_category_worklist.py
    python tools/fetch/fetch_category_worklist.py --only ropinirole,tiapride   # merges

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
sys.path.insert(0, str(ROOT / "tools"))
from lib.page_file import page_path  # noqa: E402 (refuses a path-like page)
from lib import drugs_io  # noqa: E402
from lib import worklist_io  # noqa: E402
from lib.worklist_io import merge_scoped  # noqa: E402
from lib.corpora import wikipedia as wikistore  # noqa: E402 (page_for, SENTENCE_SPLIT)
from data_generators.drugs import DRUG_CATEGORY_LABELS  # noqa: E402

OUT_PATH = ROOT / "tools" / "generated_cache" / "category_worklist.json"
PAGES_FR = ROOT / "data_sources" / "wikipedia" / "pages_fr"
# The brand pass already resolved each drug's FR article (via the EN langlink) and
# recorded its slug; reuse that rather than guessing a French title.
BRAND_WORKLIST = ROOT / "tools" / "generated_cache" / "brand_worklist.json"

MIN_LINE = 30    # shorter lead lines are infobox captions ("Identification", "modifier")
MAX_LINE = 600
# Infobox residue that survives the ``cell | cell`` filter: bullets, the page stamp, and
# the chemistry identifiers flattened without a separator.
INFOBOX_PREFIXES = ("- ", "<!--", "source:", "InChI", "SMILES", "Key:")


def _verified(drug: dict) -> bool:
    return any(s.get("provenance") == "verified" for s in drug.get("category_sources", []))


def lead_sentences(text: str) -> list[str]:
    """The prose sentences before the article's first ``##`` heading.

    A stored page opens with the infobox flattened to ``cell | cell`` rows and ``- ``
    bullets; neither is lead prose, so both are skipped, as are short caption lines.
    """
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            break
        if (len(line) < MIN_LINE or " | " in line or line.startswith(INFOBOX_PREFIXES)):
            continue
        for part in wikistore.SENTENCE_SPLIT.split(line):
            part = part.strip()
            if MIN_LINE <= len(part) <= MAX_LINE:
                out.append(part)
    return out


def drug_class_rows(text: str) -> list[str]:
    """The infobox ``Drug class | ...`` row(s), kept whole (they are verbatim lines)."""
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("Drug class |")]


def _fr_slug(drug: dict, brand: dict) -> str | None:
    slug = (brand.get(drug["id"]) or {}).get("fr_slug")
    if slug and page_path(PAGES_FR, slug).exists():
        return slug
    en = wikistore.page_for(drug)
    if en:
        guess = os.path.splitext(os.path.basename(en))[0]
        if page_path(PAGES_FR, guess).exists():
            return guess
    return None


def candidates(drug: dict, brand: dict) -> list[dict]:
    out: list[dict] = []
    en = wikistore.page_for(drug)
    if en and os.path.exists(en):
        slug = os.path.splitext(os.path.basename(en))[0]
        text = Path(en).read_text(encoding="utf-8", errors="replace")
        for line in drug_class_rows(text) + lead_sentences(text):
            out.append({"corpus": "wikipedia_pharm", "page": slug, "line": line})
    fr = _fr_slug(drug, brand)
    if fr:
        text = page_path(PAGES_FR, fr).read_text(encoding="utf-8", errors="replace")
        for line in lead_sentences(text):
            out.append({"corpus": "wikipedia_fr", "page": fr, "line": line})
    seen: set[tuple] = set()
    uniq = []
    for c in out:
        key = (c["corpus"], c["line"])
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def build(only: set[str] | None = None) -> dict:
    """``{vocabulary: {cat: en label}, drugs: {id: {name, categories, labels, candidates}}}``."""
    brand = json.loads(BRAND_WORKLIST.read_text(encoding="utf-8")) if BRAND_WORKLIST.exists() else {}
    drugs: dict[str, dict] = {}
    for drug in drugs_io.load_drugs():
        if (only and drug["id"] not in only) or _verified(drug):
            continue
        cands = candidates(drug, brand)
        if cands:
            drugs[drug["id"]] = {
                "name": drug.get("name") or drug["id"],
                "categories": list(drug.get("categories", [])),
                "labels": [DRUG_CATEGORY_LABELS[c]["en"] for c in drug.get("categories", [])],
                "candidates": cands,
            }
    return {"vocabulary": {k: v["en"] for k, v in DRUG_CATEGORY_LABELS.items()},
            "drugs": drugs}


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
