#!/usr/bin/env python
"""Gate the judged seizure-threshold picks and write ``drug_seizure_threshold`` nodes.

Third of the four steps (worklist: ``tools/fetch/fetch_seizure_threshold.py``): reads the
LLM's ``tools/generated_cache/seizure_threshold_judged.json`` (``{drug: [{index, qid,
effect}]}``, ``[]`` = nothing to take) and writes
``tools/generated_cache/seizure_threshold.json``. Every pick is re-gated:

1. the drug is a dataset drug and the fetcher, rebuilt now, offers it candidates;
2. ``index`` + ``qid`` resolve to the candidate it was judged on (``pipeline.judged``);
3. ``effect`` is in ``seizure_threshold.EFFECTS`` and the line itself says it
   (``seizure_threshold.says``: a seizure word, plus a stopping word for ``withdrawal``,
   an anticonvulsant word for ``raises``);
4. the line is verbatim on the page it cites (``PageGate`` over every corpus's pages).

One node per (drug, effect): a second accepted line adds a source.

Example pick: ``{"index": 1, "qid": "5b0c11e2", "effect": "lowers"}``.

The applier writes no ``llm`` stamp, so ``tools/sourcing/recheck_quotes.py build --kinds
drug_seizure_threshold --unjudged`` + judge + apply must follow, or ``check_data.py``
family 5 fails on extracted-but-unjudged citations.

Usage (repo root)::

    python tools/sourcing/apply_seizure_threshold.py --dry-run
    python tools/sourcing/apply_seizure_threshold.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))

from lib import cache_io, drugs_io, worklist_io                 # noqa: E402
from pipeline.gate import PageGate, registry_pages              # noqa: E402
from pipeline.judged import resolve                             # noqa: E402
import fetch_seizure_threshold                                  # noqa: E402
from data_generators import seizure_threshold as S              # noqa: E402

JUDGED_PATH = ROOT / "tools" / "generated_cache" / "seizure_threshold_judged.json"


def gate(judged: dict, offered: dict, drug_ids: set[str], pages
         ) -> tuple[dict[str, list[dict]], list[str]]:
    """Gate every pick. Returns ``({drug: [{effect, sources}]}, rejections)``."""
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
        nodes: dict[str, dict] = {}
        for p in picks or []:
            effect = p.get("effect")
            what = f"{did}[{p.get('index')}] {effect}"
            cand, why = resolve(entry["candidates"], p)
            if why:
                rejected.append(f"{what}: {why}")
                continue
            line = cand["quote"]
            if effect not in S.EFFECTS:
                rejected.append(f"{what}: not in seizure_threshold.EFFECTS")
                continue
            if not S.says(effect, line):
                rejected.append(f"{what}: the line does not say it")
                continue
            if not pages.on_page(cand["corpus"], cand["page"], line):
                rejected.append(f"{what}: quote not found on {cand['corpus']} page {cand['page']}")
                continue
            src = {"corpus": cand["corpus"], "page": cand["page"], "quote": line,
                   "provenance": "verified"}
            node = nodes.setdefault(effect, {"effect": effect, "sources": []})
            if src not in node["sources"]:
                node["sources"].append(src)
        if nodes:
            out[did] = list(nodes.values())
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
    offered = fetch_seizure_threshold.build()
    drug_ids = {d["id"] for d in drugs_io.load_drugs()}
    out, rejected = gate(judged, offered, drug_ids, PageGate(registry_pages()))
    for r in rejected:
        print(f"[reject] {r}")
    pending = undecided(judged, offered)
    if pending:
        print(f"[warn] {len(pending)} offered drug(s) not judged: {', '.join(pending)}")
    n = sum(len(v) for v in out.values())
    print(f"[ok] {n} seizure-threshold node(s) over {len(out)} drug(s), {len(rejected)} rejected")
    if not args.dry_run:
        cache_io.write(S.CACHE, {"drugs": out})
        print(f"[ok] wrote {S.CACHE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
