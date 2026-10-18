#!/usr/bin/env python
"""Apply Drugs@FDA first US approvals (corpus #18 ``drugsfda``), quote-gated.

Second half of ``tools/fetch/fetch_drugsfda.py``, which wrote, per drug, the earliest
NDA it could date into ``tools/generated_cache/drugsfda_approvals.json``. No model sits
in between (the row is code-copied from the export, ``extraction: "code"``), so no
``recheck_quotes.py`` run follows.

Fallback, and earliest dated approval wins: Drugs@FDA knows the US alone, so its year is
the first **US** approval (``first_approval = {year, country: "us", agency: "fda",
national: true}``, shown as "first national approval"), written onto a drug that has no
first approval at all, whose one is already this corpus's (a refresh), or whose
Wikipedia-sourced one (``apply_drug_history.py``) is dated LATER than the FDA one: an
earlier dated approval proves the later one was not the first, so it replaces it, and
the wording follows the source that won (``national``, since a US date is not proven
first worldwide). ``apply_drug_history.py`` applies the same rule the other way round
(``history.earliest_wins``), so the two appliers agree whatever order they run in.

Gates, re-derived from the cache and the stored page, never trusted: the record is
``found``, the year sits in the quote, the quote is verbatim on its page.

    python tools/sourcing/apply_drugsfda.py --dry-run
    python tools/sourcing/apply_drugsfda.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
from lib import drugs_io  # noqa: E402
from data_generators import history  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)
import fetch_drugsfda as fda  # noqa: E402

CORPUS = "drugsfda"


def owned(drug: dict) -> bool:
    """Whether the drug's first approval is empty or this corpus's own."""
    if not drug.get("first_approval"):
        return True
    return any(s.get("corpus") == CORPUS for s in drug.get("first_approval_sources") or [])


def gate(rec: dict, pages: PageGate) -> tuple[dict | None, str]:
    """``({first_approval, first_approval_sources}, "")`` or ``(None, why)``."""
    if rec.get("status") != "found":
        return None, rec.get("status") or "no record"
    quote, year = rec["quote"], rec["year"]
    if str(year) not in quote:
        return None, f"year {year} not in the quote"
    if not pages.on_page(CORPUS, rec["application"], quote):
        return None, f"quote not on {CORPUS}/{rec['application']}"
    return {"first_approval": {"year": year, "country": "us", "agency": "fda",
                               "national": True},
            "first_approval_sources": [{"corpus": CORPUS, "page": rec["application"],
                                        "quote": quote, "provenance": "verified",
                                        "extraction": "code"}]}, ""


def apply(cache: dict, drugs: list[dict], pages: PageGate):
    """Mutate ``drugs``; return (filled ids, cleared ids, replaced-as-later lines)."""
    filled, cleared, earlier = [], [], []
    for drug in drugs:
        rec = cache.get(drug["id"]) or {}
        if not owned(drug):
            ours = drug["first_approval"]
            got, _ = gate(rec, pages)
            if got and history.earliest_wins(got["first_approval"], ours):
                earlier.append(f"{drug['id']}: FDA {rec['date']} ({rec['application']}) "
                               f"replaces later {ours['year']} {ours.get('country') or ''}")
                drug.update(got)
                filled.append(drug["id"])
            continue
        got, _ = gate(rec, pages)
        had = bool(drug.get("first_approval"))
        if got is None:
            if had:
                drug.pop("first_approval")
                drug.pop("first_approval_sources", None)
                cleared.append(drug["id"])
            continue
        drug.update(got)
        filled.append(drug["id"])
    return filled, cleared, earlier


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not fda.PAGES_DIR.is_dir():
        print("[error] data_sources/drugsfda/pages absent: run fetch_drugsfda.py first.",
              file=sys.stderr)
        return 1
    cache = json.loads(fda.CACHE_PATH.read_text("utf-8"))["drugs"]
    drugs = drugs_io.load_drugs()
    before = sum(1 for d in drugs if d.get("first_approval"))
    filled, cleared, earlier = apply(cache, drugs, PageGate({CORPUS: fda.PAGES_DIR}))
    after = sum(1 for d in drugs if d.get("first_approval"))
    tag = "[dry-run] " if args.dry_run else ""
    print(f"{tag}first approvals {before} -> {after}: {len(filled)} from Drugs@FDA, "
          f"{len(cleared)} cleared")
    for line in earlier:
        print(f"  [replaced] {line}")
    if not args.dry_run:
        drugs_io.save_drugs(drugs)
        print(f"wrote {drugs_io.DRUGS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
