#!/usr/bin/env python
"""Build the work-list for the per-binding source-extraction workflow.

For every drug binding that does NOT yet carry a source, emit one work item with
everything an extraction agent needs: the drug name, its Stahl page range (from
``stahl/INDEX.md``) and, per un-sourced binding, the target's human name, the
action label and a one-line claim to find supporting text for. Bindings that are
already sourced are skipped, so the workflow is resumable: re-run after a partial
pass and only the remainder is listed.

This is an *authoring* helper (it reads the author-side ``stahl/INDEX.md``); it is
not part of the served site. Stdlib only.

Usage:
    python tools/build_source_worklist.py [--limit N] [--out PATH]

``--limit`` keeps only the first N drugs (a cheap validation slice before the full
run). Output is JSON: a list of {id, name, pages:[start,end], bindings:[...]}.

Built with the help of Claude Code.
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
INDEX = ROOT / "stahl" / "INDEX.md"

# "| 54 | Fluoxetine | [329-334](pages/329.md) |"
_ROW = re.compile(r"^\|\s*\d+\s*\|\s*(.+?)\s*\|\s*\[(\d+)-(\d+)\]")


def _norm(name):
    """Lowercase + alphanumerics only, so the dataset's drug name reconciles with
    the INDEX heading despite punctuation/spacing differences ("Amphetamine D" vs
    "Amphetamine (D)", "Naltrexonebupropion" vs "Naltrexone-Bupropion")."""
    return "".join(c for c in name.lower() if c.isalnum())


def page_ranges():
    """Normalized drug name -> [start, end] from the generated INDEX.md."""
    out = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if m:
            out[_norm(m.group(1))] = [int(m.group(2)), int(m.group(3))]
    return out


def load_jsonl(name):
    return [json.loads(l) for l in (DATA / f"{name}.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]


def claim_for(drug_name, target_name, action_label):
    """A plain-language claim the quote must support (judge input)."""
    return f"{drug_name} acts on {target_name} ({action_label})."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="first N drugs only")
    ap.add_argument("--out", default="/tmp/claude/source_worklist.json")
    args = ap.parse_args()

    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    targets = meta["drug_targets"]
    actions = meta["drug_actions"]
    ranges = page_ranges()
    drugs = load_jsonl("drugs")

    worklist = []
    n_bindings = 0
    missing_range = []
    for d in drugs:
        rng = ranges.get(_norm(d["name"]))
        if not rng:
            if d.get("bindings"):
                missing_range.append(d["name"])
            continue
        items = []
        for idx, b in enumerate(d.get("bindings", [])):
            if b.get("sources"):
                continue  # already sourced -> skip (resumable)
            tgt = targets.get(b["target"], {})
            act = actions.get(b["action"], {})
            tname = (tgt.get("name") or {}).get("en", b["target"])
            alabel = (act.get("label") or {}).get("en", b["action"])
            items.append({
                "idx": idx,
                "target": b["target"],
                "target_name": tname,
                "action": b["action"],
                "action_label": alabel,
                "claim": claim_for(d["name"], tname, alabel),
            })
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
    print(f"wrote {args.out}: {len(worklist)} drugs, {n_bindings} un-sourced bindings")
    if missing_range:
        print(f"WARNING: no page range for {len(missing_range)} drug(s): "
              f"{missing_range}")


if __name__ == "__main__":
    main()
