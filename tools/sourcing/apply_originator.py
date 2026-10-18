#!/usr/bin/env python
"""Apply a drug's originator, its current name and its country (four-step pass).

Step three of the usual pipeline: ``tools/fetch/fetch_originator.py`` offered indexed
candidates with no verdict, an LLM answered by index into
``tools/generated_cache/originator_judged.json``::

    {"drugs":     {"<drug id>": {"index": 0, "qid": "...", "name": "Lundbeck",
                                 "company": "lundbeck"}},
     "companies": {"<slug>": {"country": {"index": 2, "qid": "...", "country": "dk"} | null,
                              "now": {"index": 5, "qid": "...", "name": "Novartis"} | null}}}

Every ``index`` echoes its candidate's ``qid`` (``pipeline.judged.resolve``). ``now``
may instead be ``{"picks": [{index, qid}, ...], "name": ...}`` when the chain takes two sentences (CIBA merged into
Ciba-Geigy, which merged into Novartis): every one must be a successor sentence and
one must carry the name; all are cited.

and this applier is the **sole writer** of ``originator`` / ``originator_sources`` /
``originator_now_sources`` / ``originator_country`` / ``originator_country_sources``.
Every gate is re-derived from a fresh build of the worklist, never trusted from the
judged file:

* the drug (or company) is still offered and the index resolves to a candidate;
* the drug quote matches ``origin.ORIGINATOR_RE`` and carries ``name`` verbatim;
* a ``company`` slug is listed in ``fetch_originator.COMPANY_ARTICLES`` and the picked
  ``name`` is one of the names listed for it (so a drug never borrows an unrelated
  company's country), else the drug gets the originator only;
* a country is a :data:`history.COUNTRIES` id (not a scope) that its quote attests
  (``history.attests``); a ``now`` name sits verbatim in one of its ``origin.SUCCESSOR_RE`` quotes;
* every quote is verbatim on its stored page (``pipeline.gate.PageGate``).

Writes ``provenance: "verified"`` with no ``llm`` stamp, so
``tools/sourcing/recheck_quotes.py`` (``--kinds drug_originator,drug_originator_country``)
must run afterwards or ``check_data.py`` family 5 flags the citations as unjudged.
Idempotent: every drug's originator fields are rebuilt on each run.

    python tools/sourcing/apply_originator.py --dry-run
    python tools/sourcing/apply_originator.py

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
import drugs_io  # noqa: E402
import worklist_io  # noqa: E402 (the one judged / worklist reader)
from lib.corpora import wikipedia as wikistore  # noqa: E402
import fetch_originator as fo  # noqa: E402
from data_generators import history, origin  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)
from pipeline.judged import resolve  # noqa: E402

JUDGED_PATH = ROOT / "tools" / "generated_cache" / "originator_judged.json"
FIELDS = ("originator", "originator_sources", "originator_now_sources",
          "originator_country", "originator_country_sources")


def _pick(cands: list[dict], pick) -> dict | None:
    """The candidate a judged ``{index, qid}`` pick names, or None."""
    return resolve(cands, pick)[0]


def _source(cand: dict, pages: PageGate) -> dict | None:
    if not pages.on_page(cand["corpus"], cand["page"], cand["line"]):
        return None
    return {"corpus": cand["corpus"], "page": cand["page"], "quote": cand["line"],
            "provenance": "verified"}


def company_facts(slug: str, offered: dict, judged: dict, pages: PageGate) -> dict:
    """``{country, country_sources, now, now_sources}`` keys that pass, for one company."""
    cands = (offered.get(slug) or {}).get("candidates") or []
    out: dict = {}
    c = judged.get("country") or {}
    cand = _pick(cands, c)
    country = c.get("country")
    if (cand and country in history.COUNTRIES and country not in history.SCOPES
            and history.attests(history.COUNTRIES, country, cand["line"])):
        src = _source(cand, pages)
        if src:
            out["country"], out["country_sources"] = country, [src]
    n = judged.get("now") or {}
    # one successor sentence, or several (``picks``) when it takes two to name it
    picks = [_pick(cands, p) for p in n.get("picks") or [n]]
    name = n.get("name")
    if (picks and all(picks) and isinstance(name, str) and name
            and any(name in c["line"] for c in picks)
            and all(origin.SUCCESSOR_RE.search(c["line"]) for c in picks)):
        srcs = [_source(c, pages) for c in picks]
        if all(srcs):
            out["now"], out["now_sources"] = name, srcs
    return out


def apply(worklist: dict, judged: dict, drugs: list[dict], pages: PageGate,
          companies: dict[str, list[str]] | None = None) -> dict[str, int]:
    """Rebuild every drug's originator fields in place; return per-kind counts."""
    companies = fo.COMPANY_ARTICLES if companies is None else companies
    facts = {slug: company_facts(slug, worklist.get("companies") or {}, j or {}, pages)
             for slug, j in (judged.get("companies") or {}).items() if slug in companies}
    counts = {"drug_originator": 0, "drug_originator_country": 0, "now": 0}
    offered = worklist.get("drugs") or {}
    for drug in drugs:
        for k in FIELDS:
            drug.pop(k, None)
        j = (judged.get("drugs") or {}).get(drug["id"])
        if not j:
            continue
        cand = _pick((offered.get(drug["id"]) or {}).get("candidates") or [], j)
        name = j.get("name")
        if not (cand and isinstance(name, str) and name and name in cand["line"]
                and origin.ORIGINATOR_RE.search(cand["line"])):
            print(f"  [skip] {drug['id']}: pick fails the quote gate", file=sys.stderr)
            continue
        src = _source(cand, pages)
        if not src:
            print(f"  [skip] {drug['id']}: quote not on page {cand['page']}", file=sys.stderr)
            continue
        drug["originator"] = {"name": name}
        drug["originator_sources"] = [src]
        counts["drug_originator"] += 1
        slug = j.get("company")
        if not slug:
            continue
        if name not in companies.get(slug, []):
            print(f"  [skip] {drug['id']}: {name!r} is not a listed name of {slug}",
                  file=sys.stderr)
            continue
        f = facts.get(slug) or {}
        if f.get("now") and f["now"] != name:
            drug["originator"]["now"] = f["now"]
            drug["originator_now_sources"] = f["now_sources"]
            counts["now"] += 1
        if f.get("country"):
            drug["originator_country"] = f["country"]
            drug["originator_country_sources"] = f["country_sources"]
            counts["drug_originator_country"] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judged", type=Path, default=JUDGED_PATH)
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()
    if not Path(wikistore.PAGES_DIR).is_dir():
        print("[error] data_sources/wikipedia/pages missing (author-side)", file=sys.stderr)
        return 1
    judged = worklist_io.read(args.judged)
    drugs = drugs_io.load_drugs()
    counts = apply(fo.build(), judged, drugs,
                   PageGate({fo.CORPUS: Path(wikistore.PAGES_DIR)}))
    print(("[dry-run] " if args.dry_run else "") + ", ".join(
        f"{k} {v}" for k, v in counts.items()))
    if not args.dry_run:
        drugs_io.save_drugs(drugs)
        print(f"[ok] wrote {drugs_io.DRUGS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
