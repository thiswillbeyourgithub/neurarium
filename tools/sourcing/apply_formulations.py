#!/usr/bin/env python
"""Move each brand / Tmax / T½ under the formulation its source ties it to.

Sole writer of a drug's ``formulations[]`` (node kind ``drug_formulations``, see
``tools/data_generators/formulations.py``). Two inputs, both re-derived or re-gated
here, never trusted:

* the **code** read of ``tools/fetch/fetch_formulation_worklist.py``
  (``code_brand_release`` / ``code_claim_release``): a brand's own release suffix, a
  BDPM brand whose every marketed product is one release type, a label sentence naming
  no formulation placed under the product its page is the label of. Release source
  stamped ``extraction: "code"``, no judge needed;
* the **LLM picks** in ``tools/generated_cache/formulation_judged.json``, answered by
  index over that fetcher's worklist::

      {"<drug>": {"brand:Concerta": {"index": 2, "release": "xr"},
                  "half_life": {"picks": [{"release": "ir", "hours": 2, "hours_max": 3},
                                          {"release": "xr", "hours": 4.5}]},
                  "tmax": {"molecule": true}}}

  Gates: the drug and the item are **offered** by a fresh ``build()``; the index
  resolves; the release is one the sentence itself names (``formulations.attests``); a
  brand pick's sentence names the brand; a Tmax / T½ pick's value is one the sentence
  states (re-parsed by code, as in ``apply_tmax.py``) and the sentence is still the
  claim's current quote; the sentence is verbatim on its page (``pipeline.gate.PageGate``).

What is placed leaves the molecule level (a brand merges by name into its formulation;
a Tmax / T½ moves with its source, the release quote joining the formulation's
``release_sources``). What nothing places stays where it is. Idempotent: a re-run
finds nothing left to move, and a brand / Tmax / T½ applier that re-adds a moved claim
at molecule level is undone by re-running this (``generate_data.py`` refuses the
duplicate until then). Writes no ``llm`` stamp, so ``tools/sourcing/recheck_quotes.py``
must judge the picked release quotes afterwards (``--kinds drug_formulations``).

Usage (from the repo root)::

    python tools/sourcing/apply_formulations.py --dry-run
    python tools/sourcing/apply_formulations.py

Stdlib only; author-side (needs the gitignored ``data_sources/`` tree).

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
from lib import drugs_io  # noqa: E402
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
from data_generators import formulations as F  # noqa: E402
from pipeline.gate import PageGate, registry_pages  # noqa: E402 (the applier's page gate)
from pipeline.judged import resolve  # noqa: E402
from apply_tmax import clean_value, same_duration  # noqa: E402
import fetch_formulation_worklist as W  # noqa: E402

JUDGED_PATH = ROOT / "tools" / "generated_cache" / "formulation_judged.json"
PAGES = registry_pages()


def _same_src(a: dict, b: dict) -> bool:
    return (a.get("corpus"), str(a.get("page")), a.get("quote")) == (
        b.get("corpus"), str(b.get("page")), b.get("quote"))


def _add_src(bucket: list, src: dict) -> None:
    if not any(_same_src(s, src) for s in bucket):
        bucket.append(src)


def judged_brand(item: dict | None, pick: dict | None, gate: PageGate,
                 reject) -> tuple[str, dict] | None:
    """``(release, release source)`` of a gated brand pick, or None."""
    if not (item and pick) or pick.get("molecule"):
        return None
    cand, why = resolve(item["candidates"], pick)
    if why:
        return reject(f"index {pick.get('index')!r}: {why}")
    rel = pick.get("release")
    if rel not in F.RELEASES or not F.attests(rel, cand["line"]):
        return reject(f"release {rel!r} is not named by the sentence")
    if not re.search(rf"(?<!\w){re.escape(item['brand'])}(?!\w)", cand["line"], re.I):
        return reject("the sentence does not name the brand")
    if not gate.on_page(cand["corpus"], cand["page"], cand["line"]):
        return reject("the sentence is not verbatim on its page")
    return rel, {"corpus": cand["corpus"], "page": cand["page"], "quote": cand["line"],
                 "provenance": "verified"}


def judged_claim(item: dict | None, pick: dict | None, src: dict, gate: PageGate,
                 reject) -> list[tuple[str, dict, dict]]:
    """``[(release, release source, value)]`` of a gated Tmax / T½ pick, or ``[]``."""
    if not (item and pick) or pick.get("molecule"):
        return []
    cand = item["candidates"][0]
    if cand["line"] != src.get("quote"):
        return reject("the claim's quote changed since the worklist was built") or []
    if not gate.on_page(cand["corpus"], cand["page"], cand["line"]):
        return reject("the sentence is not verbatim on its page") or []
    out, rels = [], set()
    for p in pick.get("picks") or []:
        rel, value = p.get("release"), clean_value(p)
        if rel not in F.RELEASES or not F.attests(rel, cand["line"]) or rel in rels:
            return reject(f"release {rel!r} not named by the sentence (or twice)") or []
        if not value or not any(same_duration(value, d) for d in cand["durations"]):
            return reject(f"{value} is not a duration the sentence states") or []
        rels.add(rel)
        out.append((rel, {"corpus": cand["corpus"], "page": cand["page"],
                          "quote": cand["line"], "provenance": "verified"}, value))
    return out


def apply(drugs: list[dict], judged: dict, offered: dict, gate: PageGate) -> dict:
    """Place every claim it can; returns counters + rejection lines."""
    stats = {"brands": 0, "tmax": 0, "half_life": 0, "rejected": []}
    for drug in drugs:
        did = drug["id"]
        items = (offered.get(did) or {}).get("items", {})
        picks = judged.get(did) or {}

        def reject(why, key=""):
            stats["rejected"].append(f"{did} {key}: {why}")
            return None

        forms = {f["release"]: f for f in drug.get("formulations") or []}

        def form(rel: str) -> dict:
            return forms.setdefault(rel, {"release": rel, "release_sources": []})

        keep = []
        for b in drug.get("brands") or []:
            key = f"brand:{b['name']}"
            got = W.code_brand_release(b) or judged_brand(
                items.get(key), picks.get(key), gate, lambda w: reject(w, key))
            if not got:
                keep.append(b)
                continue
            f = form(got[0])
            _add_src(f["release_sources"], got[1])
            have = next((x for x in f.setdefault("brands", [])
                         if x["name"].lower() == b["name"].lower()), None)
            if have:
                for s in b.get("sources") or []:
                    _add_src(have.setdefault("sources", []), s)
            else:
                f["brands"].append(b)
            stats["brands"] += 1
        if keep:
            drug["brands"] = keep
        else:
            drug.pop("brands", None)

        for field in W.FIELDS:
            srcs = drug.get(f"{field}_sources") or []
            if not drug.get(field) or len(srcs) != 1:
                continue
            code = W.code_claim_release(srcs[0])
            placed = ([(code[0], code[1], drug[field])] if code else judged_claim(
                items.get(field), picks.get(field), srcs[0], gate,
                lambda w: reject(w, field)))
            if not placed:
                continue
            for rel, rsrc, value in placed:
                f = form(rel)
                _add_src(f["release_sources"], rsrc)
                f[field] = value
                f[f"{field}_sources"] = [srcs[0]]
            drug.pop(field)
            drug.pop(f"{field}_sources")
            stats[field] += 1

        if forms:
            order = list(F.RELEASES)
            drug["formulations"] = sorted(forms.values(),
                                          key=lambda f: order.index(f["release"]))
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judged", type=Path, default=JUDGED_PATH)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not PAGES["wikipedia_pharm"].is_dir():
        print("[error] data_sources/ absent: the quote gate cannot run.", file=sys.stderr)
        return 1
    judged = worklist_io.read(args.judged, required=False, default={})
    offered = W.build()["drugs"]                       # freshly re-derived
    drugs = drugs_io.load_drugs()
    stats = apply(drugs, judged, offered, PageGate(PAGES))
    n_drugs = sum(1 for d in drugs if d.get("formulations"))
    n_multi = sum(1 for d in drugs if len(d.get("formulations") or []) > 1)
    verb = "[dry-run] would place" if args.dry_run else "[ok] placed"
    print(f"{verb} {stats['brands']} brand(s), {stats['tmax']} Tmax, "
          f"{stats['half_life']} T½; {n_drugs} drug(s) with formulations, "
          f"{n_multi} with more than one; {len(stats['rejected'])} rejected.")
    for r in stats["rejected"]:
        print(f"  [reject] {r}")
    if not args.dry_run:
        drugs_io.save_drugs(drugs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
