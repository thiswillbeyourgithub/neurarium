#!/usr/bin/env python
"""Quote-gate the judged binding directions and write them onto ``drugs_data.jsonl``.

The apply half of the binding-direction pass (see CLAUDE.md "Drugs" -> "Binding
directions"): ``tools/fetch/fetch_binding_directions.py`` offers candidate sentences
from each drug's stored English Wikipedia article (corpus #9 ``wikipedia_pharm``), one
LLM pass answers with the ones that state a direction, and this script decides whether
that answer is allowed into the dataset.

Input ``tools/generated_cache/binding_directions_judged.json``::

    {"olanzapine": [{"target": "5ht2c", "action": "inverse_agonist", "index": 3}, ...]}

``index`` points into that drug's ``candidates`` list in the worklist, so the judge
never supplies a quote and this script resolves it itself: a paraphrase is not
expressible. Six gates stand between that answer and the data, each counted and
reported rather than silently dropped:

1. the drug is one the worklist offered (a hallucinated id is a rejection);
2. the index resolves to one of that drug's candidates;
3. the target is a binding this drug **currently** carries as ``affinity_only``. This is
   what makes the pass **confirm-only**: it never adds a binding, and a direction that
   came from anywhere else (Stahl, GtoPdb, an author) is never overwritten;
4. the action is a live ``DRUG_ACTIONS`` key;
5. **the quote names the target the row claims.** The judge picks a sentence and a
   target separately, so this is what stops the two being paired wrongly. It runs the
   very matcher the fetcher used to offer the sentence (``tools/target_aliases.py``), so
   the gate can never accept what the worklist could not have shown;
6. the quote is verbatim on ``data_sources/wikipedia/pages/<slug>.md``, re-derived here
   under ``check_data.normalize_for_match`` rather than trusted from the worklist.

On a pass the binding loses ``affinity_only``, gains ``action``, keeps its ``ki``
untouched, and gains a ``{corpus, page, quote, provenance: "verified"}`` source. **No
``llm`` stamp is written here**: a model picked this sentence out of prose, so it is not
backed until a second model has agreed it supports the claim, and that stamp is
``tools/sourcing/recheck_quotes.py``'s to write (see CLAUDE.md "no LLM-picked quote
ships unjudged"). Until it runs, ``check_data.py`` family 5 will flag these citations,
which is the intended loud reminder.

Sole writer of a direction onto an affinity-only binding, and idempotent: a binding
already carrying that exact ``wikipedia_pharm`` quote is skipped, so re-running with the
same judged file changes nothing.

Usage (from the repo root), then regenerate + check::

    python tools/sourcing/apply_binding_directions.py --dry-run
    python tools/sourcing/apply_binding_directions.py
    python tools/generate_data.py && python tools/check_data.py

Stdlib only; author-side (the gate needs the gitignored corpus #9 page tree, so on a
clone without it the script refuses rather than writing ungated quotes).

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))

import drugs_io  # noqa: E402
import target_aliases as ta  # noqa: E402  (the same matcher the fetcher offered with)
from check_data import normalize_for_match  # noqa: E402  (one canonical quote gate)
from data_generators.drugs import DRUG_ACTIONS  # noqa: E402  (the live action vocabulary)

CORPUS = "wikipedia_pharm"
CACHE = os.path.join(REPO, "tools", "generated_cache")
WORKLIST = os.path.join(CACHE, "binding_directions_worklist.json")
JUDGED = os.path.join(CACHE, "binding_directions_judged.json")
PAGES = os.path.join(REPO, "data_sources", "wikipedia", "pages")


def page_text(slug: str) -> str | None:
    """The stored corpus #9 article a quote cites, normalized, or None when absent."""
    path = os.path.join(PAGES, f"{slug}.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return normalize_for_match(f.read())


def _already_applied(binding: dict, quote: str) -> bool:
    """Whether this binding already cites that exact corpus #9 quote.

    Checked before the affinity-only gate so a second run reads as a no-op rather than
    as a pile of rejections: after the first run the binding is, correctly, no longer
    affinity-only.
    """
    return any(src.get("corpus") == CORPUS and src.get("quote") == quote
               for src in binding.get("sources", []))


def apply(worklist: list[dict], judged: dict, drugs: list[dict],
          read_page) -> tuple[collections.Counter, list[str]]:
    """Run the gates over a judged file, writing the survivors onto ``drugs`` in place.

    Pure apart from ``read_page``, which is the only IO: that is what lets the gates be
    tested without the author-side corpus, which is gitignored and so absent from a
    clone.

    Parameters
    ----------
    worklist : list of dict
        The fetcher's records (``binding_directions_worklist.json``).
    judged : dict
        ``{drug id: [{target, action, index, note?}, ...]}``.
    drugs : list of dict
        The authored drug records, **mutated in place** for every row that passes.
    read_page : callable
        ``slug -> normalized page text or None``.

    Returns
    -------
    tuple
        ``(stats, rejected)``: a tally and one line per rejected row.
    """
    by_work = {rec["drug"]: rec for rec in worklist}
    by_drug = {d["id"]: d for d in drugs}
    aliases = ta.aliases_by_target()
    stats: collections.Counter = collections.Counter()
    rejected: list[str] = []
    pages: dict[str, str | None] = {}

    def reject(why: str, detail: str) -> None:
        stats[f"rejected: {why}"] += 1
        rejected.append(f"[{why}] {detail}")

    for drug_id in sorted(judged):
        rec = by_work.get(drug_id)
        drug = by_drug.get(drug_id)
        if rec is None or drug is None:
            reject("drug not in the worklist", drug_id)
            continue
        cands, slug = rec["candidates"], rec["slug"]
        for row in judged[drug_id]:
            target = row.get("target")
            action = row.get("action")
            index = row.get("index")
            label = f"{drug_id} {target}/{action} index={index}"

            # `isinstance(True, int)` is True, so a boolean index is excluded explicitly
            # rather than silently resolving to candidate 0 or 1.
            if isinstance(index, bool) or not isinstance(index, int) \
                    or not 0 <= index < len(cands):
                reject("candidate index out of range", label)
                continue
            quote = cands[index]

            binding = next((b for b in drug.get("bindings", [])
                            if b.get("target") == target), None)
            if binding is None:
                reject("no binding on that target", label)
                continue
            if _already_applied(binding, quote):
                stats["skipped: already applied"] += 1
                continue
            if not binding.get("affinity_only"):
                # Confirm-only: this pass fills a direction in, it never revises one.
                reject("binding already states a direction", label)
                continue
            if action not in DRUG_ACTIONS:
                reject("unknown action", label)
                continue
            if not ta.mentions(quote, aliases.get(target, [])):
                reject("quote does not name the target", f"{label}: {quote[:80]}")
                continue
            if slug not in pages:
                pages[slug] = read_page(slug)
            body = pages[slug]
            if body is None:
                reject("no stored page for the citation", f"{label} ({slug})")
                continue
            if normalize_for_match(quote) not in body:
                reject("quote not verbatim on the cited page", f"{label}: {quote[:80]}")
                continue

            binding.pop("affinity_only", None)
            binding["action"] = action
            binding.setdefault("sources", []).append(
                {"corpus": CORPUS, "page": slug, "quote": quote,
                 "provenance": "verified"})
            stats[f"node: {action}"] += 1
    return stats, rejected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--verbose", action="store_true", help="list every rejected row")
    ap.add_argument("--judged", default=JUDGED, help="judged file to apply")
    args = ap.parse_args()

    if not os.path.isdir(PAGES):
        print(f"missing the author-side corpus tree ({PAGES}); see CLAUDE.local.md",
              file=sys.stderr)
        return 1
    for path in (WORKLIST, args.judged):
        if not os.path.exists(path):
            print(f"missing {os.path.relpath(path, REPO)}", file=sys.stderr)
            return 1

    with open(WORKLIST, encoding="utf-8") as f:
        worklist = json.load(f)
    with open(args.judged, encoding="utf-8") as f:
        judged = json.load(f)
    drugs = drugs_io.load_drugs()
    stats, rejected = apply(worklist, judged, drugs, page_text)

    written = sum(n for key, n in stats.items() if key.startswith("node: "))
    print(f"{written} affinity-only binding(s) given a sourced direction")
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
    drugs_io.save_drugs(drugs)
    print(f"\nwrote {drugs_io.DRUGS_PATH.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
