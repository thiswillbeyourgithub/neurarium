#!/usr/bin/env python
"""Build the work-list for the per-binding source-extraction workflow.

For every drug binding that does NOT yet carry a source, emit one work item with
everything an extraction agent needs: the drug name, its Stahl page range (from
``data_sources/books/stahl/INDEX.md``) and, per un-sourced binding, the target's human name, the
action label and a one-line claim to find supporting text for. Bindings that are
already sourced are skipped, so the workflow is resumable: re-run after a partial
pass and only the remainder is listed.

This is an *authoring* helper (it reads the author-side ``data_sources/books/stahl/INDEX.md``); it is
not part of the served site. Stdlib only.

Usage:
    python tools/sourcing/build_source_worklist.py [--limit N] [--out PATH]

``--limit`` keeps only the first N drugs (a cheap validation slice before the full
run). Output is JSON: a list of {id, name, pages:[start,end], bindings:[...]}.

Built with the help of Claude Code.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent   # repo root (script in tools/sourcing/)
DATA = ROOT / "public" / "data"
sys.path.insert(0, str(ROOT / "tools"))                # reach the shared text_fold module
from lib.text_fold import alnum_key  # noqa: E402
from lib import stahl_index  # noqa: E402 (the one INDEX.md reader + span search)


_norm = alnum_key  # lowercase alphanumerics only (tools/text_fold.py)


def load_jsonl(name):
    return [json.loads(l) for l in (DATA / f"{name}.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]


def claim_for(drug_name, target_name, action_label):
    """A plain-language claim the quote must support (judge input)."""
    return f"{drug_name} acts on {target_name} ({action_label})."


def _en(v, fallback):
    """meta is English-only (a plain string); tolerate the legacy {en,fr} shape."""
    if isinstance(v, dict):
        return v.get("en", fallback)
    return v if v else fallback


def worklist_items(drug, targets, actions):
    """The work items for one drug's bindings that still need a source.

    Returns ``(items, n_directionless)``. A binding already carrying ``sources`` is
    skipped (the list is resumable). So is one with no ``action``: an
    ``affinity_only`` binding is a measured Ki with no direction, so there is no
    "acts on X (action)" claim for a quote to back here; its direction is the job of
    the binding-directions pass (``tools/fetch/fetch_binding_directions.py``). Those
    are counted, not listed.
    """
    items, directionless = [], 0
    for idx, b in enumerate(drug.get("bindings", [])):
        if b.get("sources"):
            continue  # already sourced -> skip (resumable)
        if not b.get("action"):
            directionless += 1
            continue
        tgt = targets.get(b["target"], {})
        act = actions.get(b["action"], {})
        tname = _en(tgt.get("name"), b["target"])
        alabel = _en(act.get("label"), b["action"])
        items.append({
            "idx": idx,
            "target": b["target"],
            "target_name": tname,
            "action": b["action"],
            "action_label": alabel,
            "claim": claim_for(drug["name"], tname, alabel),
        })
    return items, directionless


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="first N drugs only")
    ap.add_argument("--out", default="/tmp/claude/source_worklist.json")
    args = ap.parse_args()

    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    targets = meta["drug_targets"]
    actions = meta["drug_actions"]
    ranges = stahl_index.ranges()
    drugs = load_jsonl("drugs")

    worklist = []
    n_bindings = 0
    n_directionless = 0
    missing_range = []
    for d in drugs:
        rng = ranges.get(_norm(d["name"]))
        if not rng:
            if d.get("bindings"):
                missing_range.append(d["name"])
            continue
        items, directionless = worklist_items(d, targets, actions)
        n_directionless += directionless
        if items:
            worklist.append({"id": d["id"], "name": d["name"],
                             "pages": rng, "bindings": items})
            n_bindings += len(items)

    if args.limit:
        worklist = worklist[:args.limit]
        n_bindings = sum(len(w["bindings"]) for w in worklist)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(worklist, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"wrote {args.out}: {len(worklist)} drugs, {n_bindings} un-sourced bindings "
          f"({n_directionless} direction-less affinity_only bindings skipped)")
    if missing_range:
        print(f"WARNING: no page range for {len(missing_range)} drug(s): "
              f"{missing_range}")


if __name__ == "__main__":
    main()
