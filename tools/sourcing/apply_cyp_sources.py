#!/usr/bin/env python
"""Quote-gate the judged CYP roles and write the two committed enzyme caches.

The apply half of the ``drug_enzymes`` pipeline: ``fetch_cyp_worklist.py`` offers
candidate sentences, an LLM pass answers with the ones that state a role, and this
script is what decides whether that answer is allowed into the dataset.

Input ``tools/generated_cache/cyp_judged.json``::

    {"fluoxetine": [{"n": 3, "enzyme": "cyp2d6", "role": "inhibitor",
                     "strength": "strong"}, ...], ...}

``n`` indexes the drug's candidate list in the worklist, so the judge never supplies a
quote and this script resolves corpus / page / quote itself. Five gates stand between
that answer and the caches, each of which fails the row loudly rather than quietly
writing something weaker:

1. the drug and the index must exist (a hallucinated id or an off-by-one is a rejection,
   not a silent drop);
2. the enzyme must be one the dataset models, the role one of the three, and the
   strength one the role may take (``primarily`` is not a tier an inhibitor has);
3. **the quote must name the isoform the row claims.** The judge picks a sentence and
   an enzyme separately, so this is what stops the two being paired wrongly, and it is
   the check the index scheme cannot make redundant;
4. the quote must be verbatim on the cited page, re-derived here under
   ``check_data.normalize_for_match`` rather than trusted from the worklist, so a judge
   that edited a string fails instead of shipping a paraphrase;
5. one (enzyme, role) pair per drug per corpus, so a claim an article states twice is
   one node. The kept quote is the **more specific** one: a later row carrying a
   strength tier replaces a plain one, since an article that first says "metabolized by
   CYP2D6" and later "mainly by CYP2D6" states one fact at two resolutions, and reading
   order is no reason to keep the weaker reading.

Output: ``tools/generated_cache/drug_enzymes.json`` (corpus #1) and
``drug_enzymes_wikipedia.json`` (corpus #9), the shape ``generate_data.py`` already
reads, split by corpus because it merges them in that order and lets Stahl win a pair
both state. This script is their **sole writer**: a re-run replaces them from the
current judged file rather than accumulating.

Usage (from the repo root):
    python tools/sourcing/apply_cyp_sources.py [--dry-run] [--verbose]

Stdlib only; author-side (the gate needs the gitignored corpora, so on a clone without
them the script refuses rather than writing ungated quotes).

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "tools", "fetch"))

from fetch_cyp import ENZYME_RE, isoforms  # noqa: E402

# Reuse check_data's canonical quote-gate normalization (a single source of truth), so
# a quote accepted here is one check_data.py accepts too.
_spec = importlib.util.spec_from_file_location("cd", os.path.join(REPO, "tools", "check_data.py"))
_cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cd)
normalize = _cd.normalize_for_match

CACHE = os.path.join(REPO, "tools", "generated_cache")
WORKLIST = os.path.join(CACHE, "cyp_worklist.json")
JUDGED = os.path.join(CACHE, "cyp_judged.json")
OUT = {"stahl": os.path.join(CACHE, "drug_enzymes.json"),
       "wikipedia_pharm": os.path.join(CACHE, "drug_enzymes_wikipedia.json")}
PAGE_DIR = {"stahl": os.path.join(REPO, "data_sources", "books", "stahl", "pages"),
            "wikipedia_pharm": os.path.join(REPO, "data_sources", "wikipedia", "pages")}


def page_text(corpus: str, page) -> str | None:
    """The stored page a quote cites, normalized, or None when there is no such file."""
    path = os.path.join(PAGE_DIR[corpus], f"{page}.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return normalize(f.read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--verbose", action="store_true", help="list every rejected row")
    ap.add_argument("--judged", default=JUDGED, help="judged file to apply")
    args = ap.parse_args()

    for path in PAGE_DIR.values():
        if not os.path.isdir(path):
            print(f"missing the author-side corpus tree ({path}); see CLAUDE.local.md",
                  file=sys.stderr)
            return 1
    for path in (WORKLIST, args.judged):
        if not os.path.exists(path):
            print(f"missing {os.path.relpath(path, REPO)}", file=sys.stderr)
            return 1

    work = json.load(open(WORKLIST, encoding="utf-8"))
    vocab = work["vocabulary"]
    drugs = work["drugs"]
    judged = json.load(open(args.judged, encoding="utf-8"))

    out: dict[str, dict[str, list[dict]]] = {c: {} for c in OUT}
    seen: dict[tuple[str, str, str, str], dict] = {}
    stats: collections.Counter = collections.Counter()
    rejected: list[str] = []
    pages: dict[tuple[str, str], str | None] = {}

    def reject(why: str, detail: str) -> None:
        stats[f"rejected: {why}"] += 1
        rejected.append(f"[{why}] {detail}")

    for drug_id in sorted(judged):
        entry = drugs.get(drug_id)
        if entry is None:
            reject("drug not in the worklist", drug_id)
            continue
        cands = entry["candidates"]
        for row in judged[drug_id]:
            n, enzyme = row.get("n"), (row.get("enzyme") or "").lower()
            role, strength = row.get("role"), row.get("strength")
            label = f"{drug_id} {enzyme}/{role} n={n}"
            if not isinstance(n, int) or not 0 <= n < len(cands):
                reject("candidate index out of range", label)
                continue
            if enzyme not in vocab["enzymes"]:
                reject("enzyme not modeled", label)
                continue
            if role not in vocab["roles"]:
                reject("unknown role", label)
                continue
            if strength is not None and strength not in vocab["strengths"][role]:
                reject("strength not available to this role", f"{label} ({strength})")
                continue
            cand = cands[n]
            corpus, page, quote = cand["corpus"], cand["page"], cand["quote"]
            if enzyme not in isoforms(quote):
                reject("quote does not name the claimed isoform", f"{label}: {quote[:80]}")
                continue
            key = (corpus, str(page))
            if key not in pages:
                pages[key] = page_text(corpus, page)
            body = pages[key]
            if body is None:
                reject("no stored page for the citation", label)
                continue
            if normalize(quote) not in body:
                reject("quote not verbatim on the cited page", f"{label}: {quote[:80]}")
                continue
            rec = {"enzyme": enzyme, "role": role}
            if strength:
                rec["strength"] = strength
            rec["sources"] = [{"corpus": corpus, "page": page, "quote": quote,
                               "provenance": "verified"}]
            dedup = (corpus, drug_id, enzyme, role)
            kept = seen.get(dedup)
            if kept is not None:
                if strength and "strength" not in kept:
                    kept.clear()
                    kept.update(rec)
                    stats["merged: pair restated with a strength tier"] += 1
                else:
                    stats["dropped: pair already claimed from this corpus"] += 1
                continue
            seen[dedup] = rec
            out[corpus].setdefault(drug_id, []).append(rec)
            stats[f"node: {role} ({corpus})"] += 1

    for corpus in out:
        for drug_id in out[corpus]:
            out[corpus][drug_id].sort(key=lambda r: (r["enzyme"], r["role"]))

    for corpus, path in OUT.items():
        print(f"{os.path.basename(path)}: {len(out[corpus])} drugs, "
              f"{sum(len(v) for v in out[corpus].values())} rows")
    for key, n in sorted(stats.items()):
        print(f"  {key:<48} {n}")
    if args.verbose and rejected:
        print("\nrejected rows:")
        for line in rejected:
            print(f"  {line}")
    elif rejected:
        print(f"\n({len(rejected)} rejected rows; --verbose to list them)")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    for corpus, path in OUT.items():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out[corpus], f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        print(f"wrote {os.path.relpath(path, REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
