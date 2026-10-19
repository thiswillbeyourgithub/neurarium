#!/usr/bin/env python
"""Build the formulation worklist: which product a brand / Tmax / T½ belongs to.

A drug's ``formulations[]`` (node kind ``drug_formulations``, see
``tools/data_generators/formulations.py``) hold the brands, time-to-peak and half-life a
source ties to ONE release type. Two kinds of evidence decide where a claim goes:

* **structured fields, read by code** (no verdict needed, nothing offered here): a brand
  whose own quote carries a release suffix ("Seroquel XR", "Lithobid slow-release
  tablets"); a BDPM brand, whose product denomination names its form ("SEROQUEL LP 50 mg,
  comprimé à libération prolongée"); a Tmax / T½ read off a DailyMed label or a BDPM RCP
  whose own sentence names no formulation, which then belongs to the product that page
  is the label of (its SPL title / denomination). :func:`code_brand_release` and
  :func:`code_claim_release` are that read, shared with the applier;
* **prose, picked by an LLM**: everything else that mentions a formulation. This is the
  candidate half of the usual four-step pipeline and states **no verdict of its own**:
  per drug it offers (a) each molecule-level brand code cannot place, with every sentence
  of the drug's stored English (#9) and French (#10) Wikipedia articles that names the
  brand AND a release type, and (b) each molecule-level Tmax / T½ whose own quote names
  a release type, with that quote and the durations it states. The LLM answers by index
  into ``tools/generated_cache/formulation_judged.json``;
  ``tools/sourcing/apply_formulations.py`` gates and writes; ``recheck_quotes.py`` stamps
  the judge.

A claim nothing places stays at molecule level: no formulation is ever guessed.

Usage (from the repo root)::

    python tools/fetch/fetch_formulation_worklist.py
    python tools/fetch/fetch_formulation_worklist.py --only quetiapine   # merges

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
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))
from lib.page_file import read_page_file  # noqa: E402
from lib import drugs_io  # noqa: E402
from lib import worklist_io  # noqa: E402
from pipeline.judged import ECHO_QID  # noqa: E402
from lib.worklist_io import merge_scoped  # noqa: E402
from data_generators import formulations as F  # noqa: E402
from data_generators.provenance import corpus_page_path  # noqa: E402
from lib.corpora import wikipedia as wikistore  # noqa: E402
from lib.parse import durations as dur  # noqa: E402  (sentences(), durations_in / durations_in_fr)
from lib.corpora import bdpm  # noqa: E402  (the product table, its folding)
import fetch_dailymed  # noqa: E402  (spl_routes: a label's route codes)

OUT_PATH = ROOT / "tools" / "generated_cache" / "formulation_worklist.json"
FIELDS = ("tmax", "half_life")
# The two corpora whose page IS one product's label, so a sentence of it naming no
# formulation is about that product.
LABEL_CORPORA = ("dailymed", "bdpm")
MAX_LINE = 600
# A brand listed as several names in one entry ("Depakote, Depakote ER") is two
# products: its suffix belongs to one of them only.
MULTI_BRAND = re.compile(r",|/|\bor\b")


def durations(corpus: str, line: str) -> list[dict]:
    """The durations a quote states, parsed in its page's language."""
    fr = corpus in ("bdpm", "wikipedia_fr")
    return (dur.durations_in_fr if fr else dur.durations_in)(line)


def product_line(corpus: str, page) -> tuple[str, str] | None:
    """``(quote, release)`` of the product a label page is about, or None.

    The quote is the page's own first line (the SPL title / the BDPM denomination),
    verbatim, so it gates like any quote; the release is read off it by code.
    """
    if corpus not in LABEL_CORPORA:
        return None
    path = corpus_page_path(corpus, page)
    if not path or not path.exists():
        return None
    lines = read_page_file(path).splitlines()
    if not lines or not lines[0].startswith("# "):
        return None
    title = lines[0][2:].strip()
    if corpus == "dailymed":
        rel = F.classify_label_title(title, fetch_dailymed.spl_routes(str(page)))
    else:
        route = next((ln.split(":", 1)[1] for ln in lines[1:8]
                      if ln.startswith("route:")), "")
        rel = F.classify_denomination(title, route)
    return (title, rel) if rel else None


def code_brand_release(brand: dict) -> tuple[str, dict] | None:
    """``(release, release source)`` code reads off a brand, or None.

    Its own quote when that carries a release suffix (the source is the brand quote
    itself), else, for a BDPM brand, its product's denomination.
    """
    name = brand.get("name") or ""
    if MULTI_BRAND.search(name):
        return None
    for src in brand.get("sources") or []:
        rel = F.classify(name)
        if rel and F.attests(rel, src.get("quote") or ""):
            return rel, _code_source(src["corpus"], src["page"], src["quote"])
    for src in brand.get("sources") or []:
        got = product_line(src.get("corpus"), src.get("page"))
        # The brand pass cites ONE product per brand, but a French brand often spans
        # several (Sifrol is a tablet AND a prolonged-release tablet): the brand is one
        # formulation only when every marketed product carrying its name is.
        if got and bdpm_brand_releases().get(bdpm.fold(src["quote"])) == {got[1]}:
            return got[1], _code_source(src["corpus"], src["page"], got[0])
    return None


_BRAND_RELEASES: dict[str, set] | None = None


def bdpm_brand_releases() -> dict[str, set]:
    """Folded brand word -> the set of releases of its marketed BDPM products.

    A product whose form code cannot read adds ``None``, so its brand never reads as
    one formulation. Empty when the author-side product table is absent.
    """
    global _BRAND_RELEASES
    if _BRAND_RELEASES is None:
        _BRAND_RELEASES = {}
        path = bdpm.BASE_DIR / bdpm.PRODUCTS_FILE
        rows = bdpm.read_table(path) if path.exists() else []
        for p in bdpm.load_products(rows).values():
            if not p["marketed"] or "active" not in p["status"].lower():
                continue
            m = re.match(r"[^\W\d_][\w'’.-]*", p["denomination"])
            if m:
                _BRAND_RELEASES.setdefault(bdpm.fold(m.group(0).rstrip(".-")),
                                           set()).add(
                    F.classify_denomination(p["denomination"], p["route"]))
    return _BRAND_RELEASES


def code_claim_release(src: dict) -> tuple[str, dict] | None:
    """``(release, release source)`` for a Tmax / T½ source code can place, or None.

    Only a label sentence that names no formulation itself: one that does ("after IV
    valproate ... after oral divalproex") may describe another product than the page
    title's, so it goes to the LLM instead.
    """
    if F.releases_in(src.get("quote") or ""):
        return None
    got = product_line(src.get("corpus"), src.get("page"))
    if not got:
        return None
    return got[1], _code_source(src["corpus"], src["page"], got[0])


def _code_source(corpus: str, page, quote: str) -> dict:
    return {"corpus": corpus, "page": page, "quote": quote, "provenance": "verified",
            "extraction": "code"}


def _pages(drug: dict) -> list[tuple[str, str, Path]]:
    """``(corpus, slug, path)`` of the drug's stored EN and FR Wikipedia articles."""
    out = []
    path = wikistore.page_for(drug)
    if path and os.path.exists(path):
        out.append(("wikipedia_pharm", Path(path).stem, Path(path)))
    fr = {s["page"] for b in drug.get("brands") or [] for s in b.get("sources") or []
          if s.get("corpus") == "wikipedia_fr"}
    for slug in sorted(fr):
        p = corpus_page_path("wikipedia_fr", slug)
        if p and p.exists():
            out.append(("wikipedia_fr", slug, p))
    return out


def brand_candidates(drug: dict, name: str) -> list[dict]:
    """Every article sentence naming this brand AND some release type."""
    word = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE)
    out, seen = [], set()
    for corpus, slug, path in _pages(drug):
        for s in dur.sentences(read_page_file(path)):
            if len(s) > MAX_LINE or s in seen or not word.search(s):
                continue
            rels = F.releases_in(s)
            if rels:
                seen.add(s)
                out.append({"corpus": corpus, "page": slug, "line": s, "releases": rels})
    return out


def items_for(drug: dict) -> dict:
    """The drug's undecided claims: ``{key: item}`` (key ``brand:<name>`` / field)."""
    items = {}
    for b in drug.get("brands") or []:
        if code_brand_release(b):
            continue
        cands = brand_candidates(drug, b["name"])
        if cands:
            items[f"brand:{b['name']}"] = {"brand": b["name"], "candidates": cands}
    for field in FIELDS:
        for src in drug.get(f"{field}_sources") or []:
            rels = F.releases_in(src.get("quote") or "")
            if rels:
                items[field] = {"value": drug.get(field), "candidates": [{
                    "corpus": src["corpus"], "page": src["page"], "line": src["quote"],
                    "releases": rels, "durations": durations(src["corpus"], src["quote"])}]}
                break
    return items


INSTRUCTIONS = (
    "Place each claim under the formulation (release type) its candidate sentence ties "
    "it to, or leave it at molecule level. Release ids: " + ", ".join(
        f"{k} = {v['en']}" for k, v in F.RELEASES.items()) + ". "
    "A 'brand:<name>' item: answer {index, release} only when that sentence says THIS "
    "brand is that kind of product (e.g. 'Concerta, an extended-release tablet'); a "
    "sentence listing the brand beside a release word that describes another product "
    "does not count. A 'tmax' / 'half_life' item: answer {picks: [{release, hours, "
    "hours_max?}]}, one per formulation the sentence gives a value for (a sentence "
    "stating IR 2-3 h and CR 4.5 h gives two picks), each value one the sentence states "
    "for that formulation; answer {molecule: true} when the value is not tied to one "
    "formulation (a sentence naming a formulation only for another fact, or a product "
    "whose release type it does not name). Omit what you cannot decide.")


def build(only: set[str] | None = None) -> dict:
    drugs = {}
    for d in drugs_io.load_drugs():
        if only and d["id"] not in only:
            continue
        items = items_for(d)
        if items:
            drugs[d["id"]] = {"name": d["name"], "items": items}
    return {"instructions": INSTRUCTIONS + ECHO_QID, "drugs": drugs}


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
    n = sum(len(v["items"]) for v in wl["drugs"].values())
    print(f"{len(wl['drugs'])} drugs, {n} undecided claims -> {worklist_io.shown(args.out.resolve(), ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
