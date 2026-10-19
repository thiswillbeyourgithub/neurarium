#!/usr/bin/env python
"""Merge Ki values quoted from cited papers (corpus #17 ``europepmc``) into ``drugs_data.jsonl``.

The last step of the ``--ki-prose`` pass (``tools/fetch/fetch_europepmc.py``): the fetcher
offers, with no verdict, every line of a cited paper that may state an affinity (an
abstract sentence, a full-text paragraph, a table caption or a table row) in
``tools/generated_cache/ki_prose_worklist.json``; one LLM pass answers **by index** in
``tools/generated_cache/ki_prose_judged.json``::

    {"drugs": {"viloxazine": [
        {"target": "5ht2b", "candidate": 10, "quote": "<verbatim span of that line>",
         "value_nm": 3900, "param": "Ki", "note": "<optional caveat>"}]}}

This script is the sole writer and gates every pick before it lands:

* **confirm-only, Ki-less only** - the target must be one the worklist listed as missing
  for that drug, and the binding must still carry no Ki: a PDSP (#5), GtoPdb (#11) or
  Wikipedia (#9) affinity is never overwritten, and no binding is ever added.
* **an affinity, not a potency** - ``param`` must be a Ki or Kd (or their p-forms). An
  IC50 / EC50 / KB is a functional potency, the same line the GtoPdb pass draws.
* **verbatim** - the quote must lie inside the picked candidate line and be found on the
  stored page (``lib.quote_match.normalize_for_match``, the quote gate's own normalizer).
* **the number is in the quote** - ``value_nm`` (or, for a pKi, the value it converts
  from) must be written in the quote, so a correct sentence cannot carry a made-up value.

The written Ki follows the Wikipedia fallback's shape (``median`` = ``min`` = ``max`` = the
one value, plus a quote-bearing ``source``), with ``reference`` = the Europe PMC article and,
when the quote comes from the open-access full text, its ``licence`` (e.g. ``CC BY-NC``)
so the reuse is credited. The source is stamped ``provenance: "verified"`` and ``extraction:
"llm"`` (the quote was picked by a model, unlike a table-copied Ki), so ``tools/sourcing/recheck_quotes.py`` must judge it afterwards (it walks
binding Ki quotes), or ``check_data.py`` family 5 flags it as extracted but unjudged.
Idempotent: a re-run first strips every Ki this script wrote (``source.corpus ==
"europepmc"``), then re-applies the judged picks.

Usage (from the repo root)::

    python tools/sourcing/apply_ki_prose.py --dry-run
    python tools/sourcing/apply_ki_prose.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent                 # tools/
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "fetch"))

from lib.page_file import page_file  # noqa: E402 (refuses a path-like page)
from lib.quote_match import normalize_for_match                     # noqa: E402
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
from pipeline.judged import resolve  # noqa: E402
from lib import drugs_io                                                # noqa: E402
from fetch_europepmc import (ARTICLE_URL, FULL_TEXT_MARKER, KI_PROSE_WORKLIST,  # noqa: E402
                             PAGES_DIR)

CORPUS = "europepmc"
JUDGED = TOOLS / "generated_cache" / "ki_prose_judged.json"
# A true binding affinity. A pKi/pKd is converted (10^(9 - p) nM).
PARAMS = {"Ki", "Kd", "pKi", "pKd"}


def _numbers(text: str) -> set[float]:
    """Every number written in ``text`` (thousands commas dropped: "3,900" -> 3900)."""
    return {float(m.replace(",", "")) for m in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def check_pick(pick: dict, cand: dict | None, page: str, missing: set[str]) -> str | None:
    """Why the pick fails its gate, or None when it may be written. Pure, for tests."""
    if pick.get("target") not in missing:
        return f"target {pick.get('target')!r} is not a Ki-less binding of this drug"
    if cand is None:
        return f"no candidate {pick.get('candidate')!r}"
    if pick.get("param") not in PARAMS:
        return f"param {pick.get('param')!r} is not an affinity (Ki / Kd)"
    quote = pick.get("quote") or cand["line"]
    nq = normalize_for_match(quote)
    if nq not in normalize_for_match(cand["line"]):
        return "quote is not a span of the picked candidate line"
    if not page or nq not in normalize_for_match(page):
        return "quote not found on the stored page"
    value = pick.get("value_nm")
    if not isinstance(value, (int, float)) or value <= 0:
        return f"value_nm {value!r} is not a positive number"
    stated = pick.get("p_value") if pick["param"].startswith("p") else value
    if stated is None or float(stated) not in _numbers(quote):
        return f"the value {stated!r} is not written in the quote"
    if pick["param"].startswith("p") and abs(10 ** (9 - float(stated)) - value) > 0.01 * value:
        return f"value_nm {value} does not convert from p{pick['param'][1:]} {stated}"
    return None


def ki_object(pick: dict, cand: dict, page: str) -> dict:
    """The binding's ``ki`` object, in the Wikipedia fallback's shape."""
    quote = pick.get("quote") or cand["line"]
    value = float(pick["value_nm"])
    source = {"corpus": CORPUS, "page": cand["page"], "quote": quote,
              "value_nm": value, "param": pick["param"],
              "reference": ARTICLE_URL.format(pmid=cand["page"]),
              "provenance": "verified", "extraction": "llm"}
    full = page.partition(FULL_TEXT_MARKER)[2]
    if full and normalize_for_match(quote) in normalize_for_match(full):
        m = re.search(r"^licence: (.+)$", page, re.MULTILINE)
        if m:
            source["licence"] = m.group(1).strip()
    if pick.get("note"):
        source["note"] = pick["note"]
    return {"median": value, "min": value, "max": value, "source": source}


def page_of(cand: dict | None) -> str:
    """The candidate's stored page text; "" when absent or its page id is path-like
    (``page_file`` refuses ``../../README``, which would otherwise gate a quote
    against a file outside the corpus)."""
    path = page_file(PAGES_DIR, cand["page"]) if cand else None
    return path.read_text("utf-8") if path and path.is_file() else ""


def strip_previous(drugs: list[dict]) -> None:
    for d in drugs:
        for b in d.get("bindings", []):
            if (b.get("ki") or {}).get("source", {}).get("corpus") == CORPUS:
                b.pop("ki")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()
    if not PAGES_DIR.exists():
        print("[error] data_sources/europepmc/pages is missing (author-side): the gate "
              "cannot run", file=sys.stderr)
        return 1
    worklist = worklist_io.read(KI_PROSE_WORKLIST)["drugs"]
    judged = worklist_io.read(JUDGED)["drugs"]
    drugs = drugs_io.load_drugs()
    strip_previous(drugs)
    by_id = {d["id"]: d for d in drugs}
    written, failed = 0, 0
    for drug_id, picks in judged.items():
        work = worklist.get(drug_id) or {}
        cands = work.get("candidates", [])
        drug = by_id.get(drug_id)
        bindings = {b["target"]: b for b in (drug or {}).get("bindings", [])}
        missing = {t for t in work.get("missing", {}) if t in bindings
                   and not bindings[t].get("ki")}
        for pick in picks:
            cand = resolve(cands, pick, key="candidate")[0]
            page = page_of(cand)
            why = check_pick(pick, cand, page, missing)
            if why:
                print(f"[gate] {drug_id} {pick.get('target')}: {why}")
                failed += 1
                continue
            bindings[pick["target"]]["ki"] = ki_object(pick, cand, page)
            missing.discard(pick["target"])
            written += 1
            print(f"[ki] {drug_id} {pick['target']}: {pick['value_nm']} nM "
                  f"({pick['param']}, PMID {cand['page']})")
    print(f"{written} Ki written, {failed} pick(s) failed the gate"
          + (" (dry run, nothing written)" if args.dry_run else ""))
    if not args.dry_run:
        drugs_io.save_drugs(drugs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
