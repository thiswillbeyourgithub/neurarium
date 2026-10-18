#!/usr/bin/env python
"""Apply drug-class (category) source quotes to ``tools/data/drugs_data.jsonl``.

A drug's **class classification** ("this drug is an SSRI / TCA / atypical
antipsychotic / ...") is its own graded node (kind ``drug_categories``), one per
drug, defaulting to ``llm``. Stahl's Prescriber's Guide states each drug's class
verbatim in the bullet(s) under its "## Class" heading (e.g. "Tricyclic
antidepressant (TCA)", "Atypical antipsychotic (...)", "Benzodiazepine
(hypnotic)"). This tool sources that node against those verbatim lines.

Unlike ``apply_nbn_sources.py`` (a pure verbatim-substring gate on a single fixed
field), mapping Stahl's free-text class line onto our coarse ``categories``
taxonomy needs a judgement step, so the accepted quotes come from an
extract-then-judge pass (Haiku extracts each drug's verbatim Class-section
descriptor line; Sonnet judges whether it supports our category IDs and picks the
line(s) to cite; a genuine contradiction is flagged, not sourced). That pass'
output is a results file ``[{id, quotes:[...]}]``; this tool then, for each drug:

* re-searches the drug's Stahl page range (from ``data_sources/books/stahl/INDEX.md``)
  for each accepted (normalized) quote, so the *page is found locally* rather than
  trusted from the agent;
* only when a quote is genuinely present does it write
  ``{corpus: stahl, page, quote, provenance: verified}`` onto ``category_sources``.

This is the local twin of ``check_data.py``'s source-quote gate (which then
re-confirms every stored quote is on its cited page). A quote the agent
paraphrased or mislocated simply fails to match and is skipped, so nothing
untrustworthy is written. Idempotent: a drug already carrying ``category_sources``
is left untouched. Stdlib only; authoring helper, not served.

**Wikipedia mode** (``--wikipedia``), for the drugs Stahl has no monograph for: the
candidates are the lead sentences ``tools/fetch/fetch_category_worklist.py`` offered from the
stored English (corpus #9 ``wikipedia_pharm``) and French (corpus #10 ``wikipedia_fr``)
articles, and the LLM answered by **index** into ``category_judged.json`` (``{id: [idx, ...]
| null}``, confirm-only: it never changes a category). This tool re-finds each picked line
verbatim on its cited page and writes ``{corpus, page, quote, provenance: verified}``, with
no ``llm`` stamp, so ``tools/sourcing/recheck_quotes.py`` must judge it next (``check_data.py``
family 5 fails an extracted-but-unjudged citation). A drug already carrying
``category_sources`` (Stahl's above all) is never touched.

Usage:
    python tools/sourcing/apply_category_sources.py RESULTS.json [--dry-run]
    python tools/sourcing/apply_category_sources.py --wikipedia [--dry-run]

Built with the help of Claude Code.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent   # repo root (script in tools/sourcing/)
sys.path.insert(0, str(ROOT / "tools"))                # reach the shared drugs_io module
from lib import drugs_io  # noqa: E402
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
from pipeline.judged import resolve  # noqa: E402
from lib.text_fold import alnum_key  # noqa: E402
from lib import stahl_index  # noqa: E402 (the one INDEX.md reader + span search)
DRUGS_JSON = drugs_io.DRUGS_PATH
CACHE = ROOT / "tools" / "generated_cache"
WORKLIST = CACHE / "category_worklist.json"
JUDGED = CACHE / "category_judged.json"
# The stored-article trees the Wikipedia mode may cite, keyed by corpus.
WIKI_PAGES = {
    "wikipedia_pharm": ROOT / "data_sources" / "wikipedia" / "pages",
    "wikipedia_fr": ROOT / "data_sources" / "wikipedia" / "pages_fr",
}

# Reuse the exact normalization the checker uses, so "accepted here" == "passes
# check_data" by construction (no second, drifting implementation).
from lib.quote_match import normalize_for_match  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)


_norm = alnum_key  # lowercase alphanumerics only (tools/text_fold.py)


def apply_wikipedia(drugs, worklist, judged, pages=WIKI_PAGES):
    """Write judged Wikipedia lead sentences onto ``category_sources``, gated.

    Parameters
    ----------
    drugs : list[dict]
        The roster, mutated in place.
    worklist : dict
        ``fetch_category_worklist.py``'s ``drugs`` map: ``id -> {candidates: [...]}``.
    judged : dict
        ``id -> [candidate index, ...] | None``.
    pages : dict
        ``corpus -> pages dir``; only these corpora can be cited.

    Returns
    -------
    tuple[int, list[str]]
        Drugs written, and one rejection line per refused pick.
    """
    by_id = {d["id"]: d for d in drugs}
    gate = PageGate(pages)
    applied, misses = 0, []
    for did, picks in judged.items():
        if not picks:
            continue
        d = by_id.get(did)
        if d is None:
            misses.append(f"{did}: no such drug in drugs_data.jsonl")
            continue
        if d.get("category_sources"):
            misses.append(f"{did}: already carries category_sources, left untouched")
            continue
        cands = (worklist.get(did) or {}).get("candidates", [])
        sources = []
        for pick in picks:
            c, why = resolve(cands, pick)
            if why:
                misses.append(f"{did}: {why}")
                continue
            # An empty needle would be "in" any page: refuse it before the page gate.
            if not normalize_for_match(c["line"]) or \
                    not gate.on_page(c["corpus"], c["page"], c["line"]):
                misses.append(f"{did}: quote not on {c['corpus']}/{c['page']}: {c['line'][:80]!r}")
                continue
            sources.append({"corpus": c["corpus"], "page": c["page"],
                            "quote": c["line"], "provenance": "verified"})
        if sources:
            d["category_sources"] = sources
            applied += 1
    return applied, misses


def _report(applied, misses, dry_run, drugs, header):
    print(header)
    for line in misses[:60]:
        print(f"  [miss] {line}")
    if len(misses) > 60:
        print(f"  ... and {len(misses) - 60} more")
    if dry_run:
        print("dry-run: drugs_data.jsonl not written")
        return
    if applied:
        drugs_io.save_drugs(drugs)
        print(f"wrote {DRUGS_JSON}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="?", help="JSON: [{id, quotes:[...]}] (Stahl mode)")
    ap.add_argument("--wikipedia", action="store_true",
                    help="apply category_judged.json against category_worklist.json")
    ap.add_argument("--worklist", type=Path, default=WORKLIST)
    ap.add_argument("--judged", type=Path, default=JUDGED)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    drugs = drugs_io.load_drugs()
    if args.wikipedia:
        worklist = worklist_io.read(args.worklist)["drugs"]
        judged = worklist_io.read(args.judged)
        applied, misses = apply_wikipedia(drugs, worklist, judged)
        _report(applied, misses, args.dry_run, drugs,
                f"applied {applied}, misses {len(misses)}")
        return
    if not args.results:
        ap.error("RESULTS.json is required unless --wikipedia")

    results = worklist_io.read(args.results)
    by_id = {d["id"]: d for d in drugs}
    ranges = stahl_index.ranges()

    applied = skipped = no_range = 0
    misses = []
    for r in results:
        did = r["id"]
        d = by_id.get(did)
        if d is None:
            misses.append(f"{did}: no such drug in drugs_data.jsonl")
            continue
        if d.get("category_sources"):
            skipped += 1
            continue
        rng = ranges.get(_norm(d["name"]))
        if not rng:
            no_range += 1
            misses.append(f"{did}: no page range in INDEX.md")
            continue
        sources = []
        for quote in r.get("quotes", []):
            page = stahl_index.find_page(rng[0], rng[1], quote)
            if page is None:
                misses.append(f"{did}: quote not found in pp.{rng[0]}-{rng[1]}: {quote!r}")
                continue
            sources.append({"corpus": "stahl", "page": page,
                            "quote": quote, "provenance": "verified"})
        if sources:
            d["category_sources"] = sources
            applied += 1

    _report(applied, misses, args.dry_run, drugs,
            f"applied {applied}, skipped {skipped} (already sourced), "
            f"no-range {no_range}, misses {len(misses)}")


if __name__ == "__main__":
    main()
