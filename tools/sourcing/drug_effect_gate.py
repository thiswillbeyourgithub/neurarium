"""The applier shared by every drug-level effect kind (``data_generators.drug_effects``).

A judged file ``{drug: [{index, qid, effect}]}`` is re-gated against the fetcher's freshly
built worklist: the drug is a dataset drug and is offered; ``index`` + ``qid`` resolve to
the candidate it was judged on; ``effect`` is in the kind's vocabulary and the line itself
says it (``DrugEffectKind.says``); the line is verbatim on its page. One node per (drug,
effect); a second accepted line adds a source. Writes no ``llm`` stamp, so
``recheck_quotes.py`` must judge the new citations afterwards.

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from lib import cache_io, drugs_io, worklist_io
from pipeline.gate import PageGate, registry_pages
from pipeline.judged import resolve


def gate(kind, judged: dict, offered: dict, drug_ids: set[str], pages
         ) -> tuple[dict[str, list[dict]], list[str]]:
    """Returns ``({drug: [{effect, sources}]}, rejections)``."""
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
            if effect not in kind.effects:
                rejected.append(f"{what}: not in the {kind.kind} vocabulary")
                continue
            if not kind.says(effect, line):
                rejected.append(f"{what}: the line does not say it")
                continue
            if not pages.on_page(cand["corpus"], cand["page"], line):
                rejected.append(f"{what}: quote not found on {cand['corpus']} page {cand['page']}")
                continue
            src = {"corpus": cand["corpus"], "page": cand["page"], "quote": line,
                   "provenance": "verified"}
            if p.get("species"):
                src["species"] = p["species"]
            node = nodes.setdefault(effect, {"effect": effect, "sources": []})
            if src not in node["sources"]:
                node["sources"].append(src)
        if nodes:
            out[did] = list(nodes.values())
    return out, rejected


def main(kind, judged_path: Path, build, doc: str) -> int:
    ap = argparse.ArgumentParser(description=doc,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--judged", type=Path, default=judged_path)
    args = ap.parse_args()
    judged = worklist_io.read(args.judged)
    offered = build()
    drug_ids = {d["id"] for d in drugs_io.load_drugs()}
    out, rejected = gate(kind, judged, offered, drug_ids, PageGate(registry_pages()))
    for r in rejected:
        print(f"[reject] {r}")
    pending = sorted(set(offered) - set(judged))
    if pending:
        print(f"[warn] {len(pending)} offered drug(s) not judged: {', '.join(pending)}")
    n = sum(len(v) for v in out.values())
    print(f"[ok] {n} {kind.kind} node(s) over {len(out)} drug(s), {len(rejected)} rejected")
    if not args.dry_run:
        cache_io.write(kind.cache, {"drugs": out})
        print(f"[ok] wrote {kind.cache.name}")
    return 0
