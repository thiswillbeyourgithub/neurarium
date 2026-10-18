#!/usr/bin/env python
"""Apply judged drug regulatory history (first approval + withdrawals), quote-gated.

Second half of the pass ``tools/fetch/fetch_drug_history.py`` starts. The LLM answered,
per drug, by candidate **index** into ``tools/generated_cache/drug_history_judged.json``::

    {"<drug id>": {
        "approval": {"index": 1, "year": 1994, "country": "us"|null, "agency": "fda"|null}
                    | null,
        "withdrawals": [{"index": 0, "year": 2004, "country": "most_markets",
                         "reason": "liver"}]}}

Every gate is re-derived here, never trusted from the judged file:

1. the drug is in the dataset and was **offered** by a fresh ``fetch_drug_history.build()``;
2. the index resolves into that drug's candidate list;
3. the year is one the quote itself contains (``history.YEAR_RE``);
4. an approval quote names an approval (``history.APPROVAL_RE``: a patent alone never
   passes), a withdrawal quote names a withdrawal (``history.WITHDRAWAL_RE``) of a
   marketed medicine: neither it nor the sentence before it (the candidate's ``context``)
   may be about a food / salt substitute / drink (``history.NOT_A_MEDICINE_RE``);
5. every vocabulary value published (country, agency, reason) is in its closed
   vocabulary AND attested by the quote (``history.attests``); a withdrawal needs a
   country and a reason (``unstated`` when the sentence gives no why);
6. the quote is verbatim on its page (``pipeline.gate.PageGate``, the checker's normalizer).

A drug's picks land all or nothing per node: a bad approval drops only the approval, a
bad withdrawal only that withdrawal. Sole writer of ``withdrawals`` and of a Wikipedia
``first_approval`` / ``first_approval_sources`` (a Drugs@FDA one, written by
``apply_drugsfda.py`` as the fallback, is kept unless a judged approval dated earlier
replaces it: ``history.earliest_wins``, the rule ``apply_drugsfda.py`` also applies), and
idempotent: a judged drug's history is replaced from the current judged file; a drug
absent from it is left untouched.

It writes no ``llm`` stamp, so ``tools/sourcing/recheck_quotes.py`` must run afterwards
(``--kinds drug_first_approval,drug_withdrawals``) or ``check_data.py`` family 5 flags the
citations as extracted-but-unjudged.

Usage (from the repo root)::

    python tools/sourcing/apply_drug_history.py --dry-run
    python tools/sourcing/apply_drug_history.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
from lib import drugs_io  # noqa: E402
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
from data_generators import history  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)
from pipeline.judged import resolve  # noqa: E402
import fetch_drug_history  # noqa: E402
import fetch_category_worklist as catwl  # noqa: E402 (PAGES_FR)

JUDGED_PATH = ROOT / "tools" / "generated_cache" / "drug_history_judged.json"
PAGES = {"wikipedia_pharm": ROOT / "data_sources" / "wikipedia" / "pages",
         "wikipedia_fr": catwl.PAGES_FR}


def _year(rec: dict, quote: str) -> int | None:
    try:
        year = int(rec.get("year"))
    except (TypeError, ValueError):
        return None
    return year if str(year) in history.YEAR_RE.findall(quote) else None


def _cand(rec: dict, cands: list[dict]) -> dict | None:
    """The candidate the judged pick names (index + qid, see ``pipeline.judged``), or None."""
    return resolve(cands, rec)[0]


def _source(cand: dict) -> dict:
    return {"corpus": cand["corpus"], "page": cand["page"], "quote": cand["line"],
            "provenance": "verified"}


def gate_approval(rec: dict, cands: list[dict], gate: PageGate) -> tuple[dict | None, str]:
    """``(first_approval with its sources, "")`` or ``(None, why)``."""
    cand = _cand(rec, cands)
    if cand is None:
        return None, f"index {rec.get('index')!r} out of range"
    quote = cand["line"]
    year = _year(rec, quote)
    if year is None:
        return None, f"year {rec.get('year')!r} not stated in the quote"
    if not history.APPROVAL_RE.search(quote):
        return None, "the quote names no approval / introduction"
    out: dict = {"year": year}
    for field, vocab in (("country", history.COUNTRIES), ("agency", history.AGENCIES)):
        val = rec.get(field)
        if val is None:
            continue
        if val not in vocab or not history.attests(vocab, val, quote):
            return None, f"{field} {val!r} unknown or not named by the quote"
        out[field] = val
    if not gate.on_page(cand["corpus"], cand["page"], quote):
        return None, f"quote not on {cand['corpus']}/{cand['page']}"
    return {"value": out, "sources": [_source(cand)]}, ""


def gate_withdrawal(rec: dict, cands: list[dict], gate: PageGate) -> tuple[dict | None, str]:
    """``(withdrawal record, "")`` or ``(None, why)``."""
    cand = _cand(rec, cands)
    if cand is None:
        return None, f"index {rec.get('index')!r} out of range"
    quote = cand["line"]
    year = _year(rec, quote)
    if year is None:
        return None, f"year {rec.get('year')!r} not stated in the quote"
    if not history.WITHDRAWAL_RE.search(quote):
        return None, "the quote names no withdrawal"
    if history.NOT_A_MEDICINE_RE.search(f"{cand.get('context', '')} {quote}"):
        return None, "the quote (or the sentence before it) is about a food, not a medicine"
    country, reason = rec.get("country"), rec.get("reason")
    if country not in history.COUNTRIES or not history.attests(history.COUNTRIES, country, quote):
        return None, f"country {country!r} unknown or not named by the quote"
    if reason not in history.WITHDRAWAL_REASONS or not history.attests(
            history.WITHDRAWAL_REASONS, reason, quote):
        return None, f"reason {reason!r} unknown or not named by the quote"
    if not gate.on_page(cand["corpus"], cand["page"], quote):
        return None, f"quote not on {cand['corpus']}/{cand['page']}"
    return {"year": year, "country": country, "reason": reason,
            "sources": [_source(cand)]}, ""


def apply(judged: dict, offered: dict, drugs: list[dict],
          gate: PageGate) -> tuple[int, list[str]]:
    """Gate every judged pick and write the survivors onto ``drugs`` in place.

    Returns ``(drugs touched, one line per rejection)``.
    """
    by_id = {d["id"]: d for d in drugs}
    touched, rejected = 0, []
    for did, rec in judged.items():
        drug = by_id.get(did)
        if drug is None:
            rejected.append(f"{did}: not a dataset drug")
            continue
        cands = (offered.get(did) or {}).get("candidates")
        if not cands:
            rejected.append(f"{did}: the fetcher offers no candidate for this drug")
            continue
        rec = rec or {}
        # A Drugs@FDA approval (apply_drugsfda.py) stays unless this pass now has an
        # approval of its own dated earlier (an earlier date proves the later one wrong).
        fda_kept = ((drug["first_approval"], drug["first_approval_sources"])
                    if any(s.get("corpus") == "drugsfda"
                           for s in drug.get("first_approval_sources") or []) else None)
        for key in ("first_approval", "first_approval_sources", "withdrawals"):
            drug.pop(key, None)
        if rec.get("approval"):
            got, why = gate_approval(rec["approval"], cands, gate)
            if not got:
                rejected.append(f"{did} approval: {why}")
            elif fda_kept and history.earliest_wins(fda_kept[0], got["value"]):
                rejected.append(f"{did} approval: {got['value']['year']} is later than "
                                f"the Drugs@FDA {fda_kept[0]['year']} (earliest wins)")
            else:
                drug["first_approval"] = got["value"]
                drug["first_approval_sources"] = got["sources"]
        if fda_kept and "first_approval" not in drug:
            drug["first_approval"], drug["first_approval_sources"] = fda_kept
        kept = []
        for w in rec.get("withdrawals") or []:
            got, why = gate_withdrawal(w, cands, gate)
            if got:
                kept.append(got)
            else:
                rejected.append(f"{did} withdrawal: {why}")
        if kept:
            drug["withdrawals"] = sorted(kept, key=lambda w: (w["year"], w["country"]))
        touched += 1
    return touched, rejected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judged", type=Path, default=JUDGED_PATH)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not PAGES["wikipedia_pharm"].is_dir():
        print("[error] data_sources/wikipedia/pages absent: the quote gate cannot run, "
              "refusing to write ungated quotes (see CLAUDE.local.md).", file=sys.stderr)
        return 1
    judged = worklist_io.read(args.judged)
    offered = fetch_drug_history.build()["drugs"]
    drugs = drugs_io.load_drugs()
    touched, rejected = apply(judged, offered, drugs, PageGate(PAGES))
    n_app = sum(1 for d in drugs if d.get("first_approval"))
    n_wd = sum(len(d.get("withdrawals") or []) for d in drugs)
    print(f"{'[dry-run] ' if args.dry_run else ''}{touched} drugs judged; dataset now "
          f"{n_app} first approvals, {n_wd} withdrawals; {len(rejected)} rejected")
    for r in rejected:
        print(f"  [reject] {r}")
    if not args.dry_run:
        drugs_io.save_drugs(drugs)
        print(f"wrote {drugs_io.DRUGS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
