#!/usr/bin/env python
"""Apply judged prodrug claims (node kind ``drug_prodrug``), quote-gated.

Second half of the pass ``tools/fetch/fetch_prodrug_worklist.py`` starts. The LLM
answered, per drug, by candidate **index** into
``tools/generated_cache/prodrug_judged.json``::

    {"<drug id>": {"index": 1, "metabolite": "Psilocin", "drug_id": null}}

Every gate is re-derived here, never trusted from the judged file:

1. the drug is **offered** by a fresh ``fetch_prodrug_worklist.build()``;
2. the index resolves into that drug's candidate list;
3. the quote itself says prodrug / inactive (``fetch_prodrug_worklist.PRODRUG_RE``);
4. the quote names the active metabolite (its name, or its parenthesised synonym);
5. a ``drug_id`` link, when given, is another drug of the dataset;
6. the quote is verbatim on its page (``pipeline.gate.PageGate``, the checker's normalizer).

A gated drug gets ``prodrug: true`` + ``prodrug_sources``, its active metabolite (added,
sourced by the same quote, when the drug did not list it yet; linked to a modeled drug
via ``drug_id``), and **loses its own bindings** (bar ``PRODRUG_OWN_ACTIONS``: levodopa
stays AADC's substrate, the conversion itself): a prodrug's pharmacology is its
metabolite's (a linked drug's bindings, or the metabolite's own ``bindings[]`` written by
``apply_metabolite_bindings.py``). Every dropped binding is printed so it can be re-sourced
on the metabolite. Sole writer of ``prodrug`` / ``prodrug_sources``; idempotent.

Writes no ``llm`` stamp, so ``tools/sourcing/recheck_quotes.py`` must run afterwards
(``--kinds drug_prodrug``) or ``check_data.py`` family 5 flags the citations.

    python tools/sourcing/apply_prodrug.py --dry-run
    python tools/sourcing/apply_prodrug.py

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
from data_generators.drugs import PRODRUG_OWN_ACTIONS  # noqa: E402
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)
from pipeline.judged import resolve  # noqa: E402
import fetch_prodrug_worklist as wl  # noqa: E402

JUDGED_PATH = ROOT / "tools" / "generated_cache" / "prodrug_judged.json"
PAGES = {"wikipedia_pharm": ROOT / "data_sources" / "wikipedia" / "pages"}


names_of = drugs_io.names_of
_fold = drugs_io._fold


def gate(did: str, rec: dict, cands: list[dict], ids: set[str],
         pages: PageGate) -> tuple[dict | None, str]:
    """``(source, "")`` or ``(None, why)`` for one judged drug."""
    cand, why = resolve(cands, rec)
    if why:
        return None, f"index {rec.get('index')!r}: {why}"
    quote = cand["line"]
    if not wl.PRODRUG_RE.search(quote):
        return None, "the quote does not say prodrug / inactive"
    if not any(n in _fold(quote) for n in names_of(rec.get("metabolite") or "")):
        return None, f"metabolite {rec.get('metabolite')!r} not named by the quote"
    link = rec.get("drug_id")
    if link is not None and (link not in ids or link == did):
        return None, f"drug_id {link!r} is not another drug of the dataset"
    if not pages.on_page(cand["corpus"], cand["page"], quote):
        return None, f"quote not on {cand['corpus']}/{cand['page']}"
    return {"corpus": cand["corpus"], "page": cand["page"], "quote": quote,
            "provenance": "verified"}, ""


def apply(judged: dict, offered: dict, drugs: list[dict], pages: PageGate,
          metabolites: list[dict] | None = None) -> tuple[list[str], list[str], list[str]]:
    """Mutate ``drugs`` + the ``metabolites`` store (a new active metabolite is one
    store record + one sourced reference on the drug); return (applied ids, dropped
    bindings, rejections)."""
    metabolites = [] if metabolites is None else metabolites
    by_id = {d["id"]: d for d in drugs}
    applied, dropped, rejected = [], [], []
    for did, rec in judged.items():
        drug = by_id.get(did)
        if drug is None or did not in offered:
            rejected.append(f"{did}: not offered")
            continue
        src, why = gate(did, rec, offered[did]["candidates"], set(by_id), pages)
        if src is None:
            rejected.append(f"{did}: {why}")
            continue
        drug["prodrug"] = True
        drug["prodrug_sources"] = [src]
        ref, met = drugs_io.attach_metabolite(drug, metabolites, rec["metabolite"])
        if not ref.get("sources"):
            ref["sources"] = [dict(src)]
        if rec.get("drug_id"):
            met["drug_id"] = rec["drug_id"]
        kept = []
        for b in drug.get("bindings") or []:
            if b.get("action") in PRODRUG_OWN_ACTIONS:
                kept.append(b)
            else:
                dropped.append(f"{did}: {b['target']} {b.get('action') or 'affinity-only'}")
        drug["bindings"] = kept
        applied.append(did)
    return applied, dropped, rejected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judged", type=Path, default=JUDGED_PATH)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not PAGES["wikipedia_pharm"].is_dir():
        print("[error] data_sources/wikipedia/pages absent: quote gate cannot run.",
              file=sys.stderr)
        return 1
    judged = worklist_io.read(args.judged)
    drugs = drugs_io.load_drugs()
    metabolites = drugs_io.load_metabolites()
    applied, dropped, rejected = apply(judged, wl.build()["drugs"], drugs,
                                       PageGate(PAGES), metabolites)
    tag = "[dry-run] " if args.dry_run else ""
    print(f"{tag}{len(applied)} prodrug(s): {', '.join(applied)}")
    for line in dropped:
        print(f"  dropped own binding  {line}")
    for line in rejected:
        print(f"  [rejected] {line}")
    if not args.dry_run:
        drugs_io.save_drugs(drugs)
        drugs_io.save_metabolites(metabolites)
        print(f"wrote {drugs_io.DRUGS_PATH.relative_to(ROOT)} + "
              f"{drugs_io.METABOLITES_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
