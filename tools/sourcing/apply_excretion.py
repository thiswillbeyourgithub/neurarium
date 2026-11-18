#!/usr/bin/env python
"""Apply judged excretion picks, quote-gated: the ``drug_excretion`` nodes.

Third of the four steps (see ``tools/fetch/fetch_excretion.py``): an LLM answered per
drug ``[{index, qid, aspect, value, amount?}]`` into
``tools/generated_cache/excretion_judged.json`` (``[]`` = judged, nothing usable), and
this applier is the **sole writer** of ``tools/generated_cache/excretion.json``. Every
pick is re-gated, never trusted from the judged file:

1. the drug is in the dataset and the fresh ``fetch_excretion.build()`` offers it;
2. ``index`` + ``qid`` resolve to the candidate it was judged on (``pipeline.judged``);
3. ``value`` is in ``excretion.ASPECTS[aspect]`` and the line itself names it
   (``excretion.says``), so "renal" cannot ride a sentence about faeces;
4. the line is verbatim on the page it cites (``PageGate`` over every corpus's
   ``pages_dir``);
5. ``amount``, when given, is a verbatim span of that line ("80%", "less than 1%").

One node per (drug, aspect, value): a second accepted line adds a source, and the
first ``amount`` seen is kept (a later pick's figure is dropped, not merged). Example
pick: ``{"index": 2, "qid": "82e5435e", "aspect": "unchanged", "value": "urine"}``.

The applier writes no ``llm`` stamp, so ``tools/sourcing/recheck_quotes.py build --kinds
drug_excretion --unjudged`` + judge + apply must follow, or ``check_data.py`` family 5
fails on extracted-but-unjudged citations.

Usage (repo root)::

    python tools/sourcing/apply_excretion.py --dry-run
    python tools/sourcing/apply_excretion.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))

from lib import cache_io, drugs_io, worklist_io                 # noqa: E402
from pipeline.gate import PageGate, registry_pages              # noqa: E402
from pipeline.judged import resolve                             # noqa: E402
import fetch_excretion                                          # noqa: E402
from data_generators import excretion as X                      # noqa: E402

JUDGED_PATH = ROOT / "tools" / "generated_cache" / "excretion_judged.json"


def gate(judged: dict, offered: dict, drug_ids: set[str], pages
         ) -> tuple[dict[str, list[dict]], list[str]]:
    """Gate every pick. Returns ``({drug: [{aspect, value, amount?, sources}]}, rejections)``."""
    out: dict[str, list[dict]] = {}
    rejected: list[str] = []
    for did, picks in sorted(judged.items()):
        if did.startswith("_"):
            continue
        if did not in drug_ids:
            rejected.append(f"{did}: not a dataset drug")
            continue
        entry = offered.get(did)
        if not entry:
            rejected.append(f"{did}: the fetcher offers no candidate for this drug")
            continue
        nodes: dict[tuple[str, str], dict] = {}
        for p in picks or []:
            aspect, value = p.get("aspect"), p.get("value")
            what = f"{did}[{p.get('index')}] {aspect}:{value}"
            cand, why = resolve(entry["candidates"], p)
            if why:
                rejected.append(f"{what}: {why}")
                continue
            line = cand["line"]
            if value not in X.values(aspect):
                rejected.append(f"{what}: not in excretion.ASPECTS")
                continue
            if not X.says(aspect, value, line):
                rejected.append(f"{what}: the line does not name it")
                continue
            if not pages.on_page(cand["corpus"], cand["page"], line):
                rejected.append(f"{what}: quote not found on {cand['corpus']} page {cand['page']}")
                continue
            amount = p.get("amount")
            if amount is not None and not X.is_span(amount, line):
                rejected.append(f"{what}: amount {amount!r} is not a span of the line")
                continue
            src = {"corpus": cand["corpus"], "page": cand["page"], "quote": line,
                   "provenance": "verified"}
            node = nodes.setdefault((aspect, value), {"aspect": aspect, "value": value,
                                                      "sources": []})
            if amount is not None and "amount" not in node:
                node["amount"] = amount
            if src not in node["sources"]:
                node["sources"].append(src)
        if nodes:
            # Stable key order (aspect, value, amount?, sources), what the generator reads.
            out[did] = [{k: n[k] for k in ("aspect", "value", "amount", "sources") if k in n}
                        for n in nodes.values()]
    return out, rejected


def undecided(judged: dict, offered: dict) -> list[str]:
    """The offered drugs the judged file holds no decision for (not even ``[]``)."""
    return sorted(set(offered) - set(judged))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--judged", type=Path, default=JUDGED_PATH)
    args = ap.parse_args()
    judged = worklist_io.read(args.judged)
    offered = fetch_excretion.build()
    drug_ids = {d["id"] for d in drugs_io.load_drugs()}
    out, rejected = gate(judged, offered, drug_ids, PageGate(registry_pages()))
    for r in rejected:
        print(f"[reject] {r}")
    pending = undecided(judged, offered)
    if pending:
        print(f"[warn] {len(pending)} offered drug(s) not judged: {', '.join(pending)}")
    n = sum(len(v) for v in out.values())
    print(f"[ok] {n} excretion node(s) over {len(out)} drug(s), {len(rejected)} rejected")
    if not args.dry_run:
        cache_io.write(X.CACHE, {"drugs": out})
        print(f"[ok] wrote {X.CACHE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
