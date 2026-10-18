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
   ``lib.quote_match.normalize_for_match`` rather than trusted from the worklist, so a judge
   that edited a string fails instead of shipping a paraphrase;
5. one (enzyme, role) pair per drug per corpus, so a claim an article states twice is
   one node. The kept quote is the **more specific** one: a later row carrying a
   strength tier replaces a plain one, since an article that first says "metabolized by
   CYP2D6" and later "mainly by CYP2D6" states one fact at two resolutions, and reading
   order is no reason to keep the weaker reading.

A second, optional judged file ``tools/generated_cache/cyp_strength_judged.json`` (same
row shape, ``strength`` required) answers a narrower question over the same worklist:
"which candidate states THIS row's tier in words". It never creates a row or changes a
tier (confirm-only). Each pick passes gates 1 to 4, then must restate a pair the role pass
kept, with the same strength (a different one is rejected and reported as a
contradiction), and its quote must carry the tier word the generator attests by
(``attestation.pattern_for``). It is then appended as an extra source on the row that
wins the pair at generation time (Stahl's when both corpora hold it, mirroring
``generate_data._load_drug_enzymes``), so the row's strength claim can cite it. These
sources carry **no** ``llm`` stamp: ``recheck_quotes.py build --kinds drug_enzymes
--unjudged`` must judge them, as for every other prose pass.

Output: ``tools/generated_cache/drug_enzymes.json`` (corpus #1) and
``drug_enzymes_wikipedia.json`` (corpus #9), the shape ``generate_data.py`` already
reads, split by corpus because it merges them in that order and lets Stahl win a pair
both state. This script is their **sole writer**: a re-run replaces them from the
current judged file rather than accumulating.

Usage (from the repo root):
    python tools/sourcing/apply_cyp_sources.py [--dry-run] [--verbose]
    python tools/sourcing/apply_cyp_sources.py --strength-judged PATH  (default: the
        committed cyp_strength_judged.json when present)

Stdlib only; author-side (the gate needs the gitignored corpora, so on a clone without
them the script refuses rather than writing ungated quotes).

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "tools", "fetch"))
sys.path.insert(0, HERE)

from fetch_cyp import isoforms  # noqa: E402  (one definition of the isoform vocabulary)
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
from data_generators.quotes.attestation import pattern_for  # noqa: E402  (the tier word test)

# The shared prose gate re-finds a quote under check_data's own normalization, so a quote
# accepted here is one check_data.py accepts too.
from lib.quote_match import normalize_for_match  # noqa: E402 (the gate's normalizer)
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)
from prose_gate import add_source  # noqa: E402
from pipeline.judged import resolve  # noqa: E402
from lib.io_atomic import atomic_write_json  # noqa: E402

CACHE = os.path.join(REPO, "tools", "generated_cache")
WORKLIST = os.path.join(CACHE, "cyp_worklist.json")
JUDGED = os.path.join(CACHE, "cyp_judged.json")
STRENGTH_JUDGED = os.path.join(CACHE, "cyp_strength_judged.json")
OUT = {"stahl": os.path.join(CACHE, "drug_enzymes.json"),
       "wikipedia_pharm": os.path.join(CACHE, "drug_enzymes_wikipedia.json")}
PAGE_DIR = {"stahl": os.path.join(REPO, "data_sources", "books", "stahl", "pages"),
            "wikipedia_pharm": os.path.join(REPO, "data_sources", "wikipedia", "pages")}


def apply(work: dict, judged: dict, gate: PageGate, llm: str = "opus",
          strength_judged: dict | None = None) -> tuple[dict, "collections.Counter", list]:
    """Run the gates over a judged file. Pure: `gate.text(corpus, page)` is the only IO.

    Returns the per-corpus caches, a tally, and one line per rejected row. Split out of
    ``main`` so the gates can be tested without the author-side corpora, which are
    gitignored and so absent from a clone. ``strength_judged`` is the optional tier pass
    (see the module docstring), applied after the role pass it confirms.
    """
    vocab, drugs = work["vocabulary"], work["drugs"]
    out: dict[str, dict[str, list[dict]]] = {c: {} for c in OUT}
    seen: dict[tuple[str, str, str, str], dict] = {}
    stats: collections.Counter = collections.Counter()
    rejected: list[str] = []

    def reject(why: str, detail: str) -> None:
        stats[f"rejected: {why}"] += 1
        rejected.append(f"[{why}] {detail}")

    def gated(judged_file: dict):
        """Yield ``(drug_id, row fields, candidate)`` for each row passing gates 1 to 4."""
        for drug_id in sorted(judged_file):
            entry = drugs.get(drug_id)
            if entry is None:
                reject("drug not in the worklist", drug_id)
                continue
            cands = entry["candidates"]
            for row in judged_file[drug_id]:
                n, enzyme = row.get("n"), (row.get("enzyme") or "").lower()
                role, strength = row.get("role"), row.get("strength")
                label = f"{drug_id} {enzyme}/{role} n={n}"
                cand, why = resolve(cands, row, key="n")
                if why:
                    reject(why, label)
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
                corpus, page, quote = cand["corpus"], cand["page"], cand["quote"]
                if enzyme not in isoforms(quote):
                    reject("quote does not name the claimed isoform", f"{label}: {quote[:80]}")
                    continue
                body = gate.text(corpus, page)
                if body is None:
                    reject("no stored page for the citation", label)
                    continue
                if normalize_for_match(quote) not in body:
                    reject("quote not verbatim on the cited page", f"{label}: {quote[:80]}")
                    continue
                yield drug_id, (enzyme, role, strength, label), cand

    for drug_id, (enzyme, role, strength, _label), cand in gated(judged):
        corpus, page, quote = cand["corpus"], cand["page"], cand["quote"]
        rec = {"enzyme": enzyme, "role": role}
        if strength:
            rec["strength"] = strength
        # Stamp the model that read the candidate list, so a reader can weigh the
        # quote against what that model can do (see provenance.SOURCING_LLMS).
        rec["sources"] = [{"corpus": corpus, "page": page, "quote": quote,
                           "provenance": "verified", "llm": llm}]
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

    stamps = {(s["corpus"], str(s["page"]), s["quote"]): s["llm"]
              for rec in seen.values() for s in rec["sources"] if s.get("llm")}
    for drug_id, (enzyme, role, strength, label), cand in gated(strength_judged or {}):
        # The row the generator keeps: Stahl's cache is merged first and wins a pair both
        # corpora state, so a tier quote must ride that row or it would be shadowed.
        target = next((seen[(c, drug_id, enzyme, role)] for c in OUT
                       if (c, drug_id, enzyme, role) in seen), None)
        if target is None:
            reject("tier pick restates no kept pair", label)
            continue
        if not strength:
            reject("tier pick names no strength", label)
            continue
        if target.get("strength") != strength:
            reject("tier pick contradicts the stored strength",
                   f"{label}: stored {target.get('strength')}, quote says {strength}: "
                   f"{cand['quote'][:120]}")
            continue
        if not pattern_for("strength", strength).search(cand["quote"]):
            reject("quote states no tier word", f"{label}: {cand['quote'][:80]}")
            continue
        src = {"corpus": cand["corpus"], "page": cand["page"], "quote": cand["quote"],
               "provenance": "verified"}
        # A quote is one node whatever cites it, so a sentence the role pass already
        # cites keeps that citation's stamp (two stamps on one quote id is a collision
        # the generator refuses). Its tier claim still needs judging: the recheck reads
        # every claim a quote backs, this one included.
        stamp = stamps.get((cand["corpus"], str(cand["page"]), cand["quote"]))
        if stamp:
            src["llm"] = stamp
        if not add_source(target["sources"], src, key=normalize_for_match):
            stats["dropped: tier quote already cited by the row"] += 1
            continue
        stats[f"tier source: {strength} ({cand['corpus']})"] += 1

    for corpus in out:
        for drug_id in out[corpus]:
            out[corpus][drug_id].sort(key=lambda r: (r["enzyme"], r["role"]))
    return out, stats, rejected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--verbose", action="store_true", help="list every rejected row")
    ap.add_argument("--judged", default=JUDGED, help="judged file to apply")
    ap.add_argument("--strength-judged", default=STRENGTH_JUDGED,
                    help="tier pass to apply on top (skipped when the file is absent)")
    ap.add_argument("--llm", default="opus", choices=("haiku", "sonnet", "opus"),
                    help="the model that judged this file (stamped on every quote)")
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

    work = worklist_io.read(WORKLIST)
    judged = worklist_io.read(args.judged)
    strength_judged = worklist_io.read(args.strength_judged, required=False)
    out, stats, rejected = apply(work, judged, PageGate(PAGE_DIR), args.llm, strength_judged)

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
        atomic_write_json(path, out[corpus], indent=1, sort_keys=True)
        print(f"wrote {os.path.relpath(path, REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
