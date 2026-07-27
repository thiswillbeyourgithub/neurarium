#!/usr/bin/env python
"""Merge the GtoPdb interaction proposals (corpus #11 ``gtopdb_ki``) into
``tools/data/drugs_data.jsonl``.

Reads ``tools/generated_cache/gtopdb_ki.json`` (written by
``tools/fetch/fetch_gtopdb_ki.py``) and fills the two gaps PDSP structurally leaves,
under the same guarantees as every other applier here:

* **confirm-only** - only bindings the drug already has are touched; a target GtoPdb
  knows and we do not model is never added.
* **PDSP first** - a Ki is written only onto a binding that has none. An existing
  measured affinity (PDSP #5 or the Wikipedia fallback #9) is never overwritten.
* **direction only where there is none** - an ``affinity_only`` binding (a measured
  Ki, no known direction) gains the curated ``action``; a binding that already states
  one is left alone, so a Stahl-sourced direction always wins. Where the two disagree
  the conflict is reported, not silently resolved.
* **re-gated** - each quote is re-confirmed verbatim on
  ``data_sources/gtopdb/pages_ki/<slug>.md`` through ``check_data.normalize_for_match``,
  so a stale cache cannot smuggle an unsourced claim through.
* **idempotent, sole writer** - its own prior writes (recognised by the
  ``provisional_action`` marker, see ``strip_previous``) are rebuilt from scratch
  each run, leaving a hand-authored ``gtopdb_ki`` citation untouched.

A direction written here is marked ``provisional_action``, which exists purely for
that rollback: ``generate_data.py`` does not emit it, so such a binding behaves like
any other in the panel and the 3D animation (its ``sources`` already name the corpus,
which is what a reader weighs it by).

Run from the repo root, then regenerate + check::

    python tools/fetch/fetch_gtopdb_ki.py
    python tools/sourcing/apply_gtopdb_ki.py
    python tools/generate_data.py && python tools/check_data.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent    # tools/ (script lives in tools/sourcing/)
REPO = TOOLS.parent
PAGES = REPO / "data_sources" / "gtopdb" / "pages_ki"
CACHE = TOOLS / "generated_cache" / "gtopdb_ki.json"

sys.path.insert(0, str(TOOLS))
from check_data import normalize_for_match        # noqa: E402  (reuse the gate's normalizer)
import drugs_io                                   # noqa: E402

CORPUS = "gtopdb_ki"

# Two directions that differ in *precision*, not in what the drug does to the target:
# an inverse agonist is an antagonist with constitutive-activity detail, a partial
# agonist is an agonist with efficacy detail, a channel blocker of an ionotropic
# receptor is an antagonist. Reported separately from a real disagreement.
COMPATIBLE = [
    {"antagonist", "inverse_agonist"},
    {"antagonist", "blocker"},
    {"agonist", "partial_agonist"},
    {"releaser", "reuptake_inhibitor"},
    {"modulator", "blocker"},
]


def gate(quote: str, slug: str, cache: dict[str, str]) -> bool:
    """True when the quote really is on the cited page (the hallucination backstop).

    Missing page tree (a clone without the author-side corpus) means the gate cannot
    run; the caller treats that as a hard stop rather than waving claims through.
    """
    if slug not in cache:
        md = PAGES / f"{slug}.md"
        cache[slug] = normalize_for_match(md.read_text("utf-8")) if md.exists() else ""
    page = cache[slug]
    return bool(page) and normalize_for_match(quote) in page


def strip_previous(binding: dict) -> None:
    """Undo this script's own prior write, so a re-run rebuilds rather than stacks.

    Only *our* write. The corpus alone cannot identify it: a binding that already
    states its direction may cite ``gtopdb_ki`` by hand (furosemide's GABA-A alpha6
    NAM does), and that is precisely the case this script never writes, so dropping
    every ``gtopdb_ki`` source would silently delete a hand-authored one on each run.
    The ``provisional_action`` flag is the reliable marker: it is set on exactly the
    bindings whose direction (and the single source appended with it) came from here.
    """
    if (binding.get("ki") or {}).get("source", {}).get("corpus") == CORPUS:
        binding.pop("ki")
    if binding.pop("provisional_action", None):
        # The action came from us, so it goes back to being affinity-only, and the
        # source appended alongside it goes with it (the last one we added).
        binding.pop("action", None)
        binding["affinity_only"] = True
        sources = binding.get("sources", [])
        for i in range(len(sources) - 1, -1, -1):
            if sources[i].get("corpus") == CORPUS:
                sources.pop(i)
                break
        if not sources:
            binding.pop("sources", None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    if not CACHE.exists():
        raise SystemExit(f"error: {CACHE} missing; run tools/fetch/fetch_gtopdb_ki.py first")
    if not PAGES.exists():
        raise SystemExit(f"error: {PAGES} missing (author-side corpus); "
                         f"run tools/fetch/fetch_gtopdb_ki.py first")

    proposals = json.loads(CACHE.read_text("utf-8"))["drugs"]
    drugs = drugs_io.load_drugs()
    page_cache: dict[str, str] = {}
    n_ki = n_action = n_gate_fail = 0
    kept_ki = kept_action = 0
    conflicts: list[str] = []
    refinements: list[str] = []

    for drug in drugs:
        per_target = proposals.get(drug["id"], {})
        for binding in drug.get("bindings", []):
            strip_previous(binding)
            entry = per_target.get(binding.get("target"))
            if not entry:
                continue
            src = entry["source"]
            if not gate(src["quote"], src["page"], page_cache):
                n_gate_fail += 1
                continue
            source = {k: v for k, v in src.items() if v is not None}

            if entry.get("ki") and not binding.get("ki"):
                ki = dict(entry["ki"])
                param = ki.pop("param", None)
                ki["source"] = {**source,
                                # The affinity is a pKi/pKd converted to nM; keep the
                                # original parameter visible so a reader knows which.
                                **({"note": f"GtoPdb {param}"} if param else {}),
                                "value_nm": ki["median"]}
                binding["ki"] = ki
                n_ki += 1
            elif entry.get("ki"):
                kept_ki += 1

            action = entry.get("action")
            if action and binding.get("affinity_only"):
                binding.pop("affinity_only")
                binding["action"] = action
                binding["provisional_action"] = True
                binding.setdefault("sources", []).append(source)
                n_action += 1
            elif action and binding.get("action") and action != binding["action"]:
                kept_action += 1
                line = (f"{drug['id']} {binding['target']}: "
                        f"ours {binding['action']!r} vs GtoPdb {action!r}")
                if {action, binding["action"]} in COMPATIBLE:
                    refinements.append(line)
                else:
                    conflicts.append(line)

    print(f"affinity: {n_ki} binding(s) given a Ki, {kept_ki} left alone (already measured)")
    print(f"direction: {n_action} affinity-only binding(s) given a provisional action")
    if n_gate_fail:
        print(f"gate: {n_gate_fail} proposal(s) dropped, quote not verbatim on its page")
    if refinements:
        print(f"\n{len(refinements)} compatible refinement(s) (same effect, finer wording):")
        for c in refinements:
            print(f"  {c}")
    if conflicts:
        print(f"\n{len(conflicts)} genuine direction conflict(s) left as-is (ours wins):")
        for c in conflicts:
            print(f"  {c}")
    if args.dry_run:
        print("\n(dry run: nothing written)")
        return 0
    drugs_io.save_drugs(drugs)
    print(f"\nwrote {drugs_io.DRUGS_PATH.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
