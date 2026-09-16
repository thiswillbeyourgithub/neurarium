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

**The second input, ``--tables``** (``binding_directions_tables.json``, written by
``tools/fetch/fetch_binding_direction_tables.py``): the direction read off the ``Action``
column of the article's own Ki table, one verbatim table row as the quote. Gates 3, 4 and 6
are the same; gates 1 and 2 have no index to resolve; gate 5 becomes "the row's target cell
resolves to the target claimed" under the very resolver the fetcher offered it with
(``fetch_wikipedia_pharmacology.resolve_wiki_target``). A cell is copied, not chosen, so
that source is stamped ``extraction: "code"`` (pipeline ``page_code``) and needs no judge
and no recheck: the Ki value in the same row is sourced exactly this way.

Sole writer of a direction onto an affinity-only binding, and idempotent: a binding
already carrying that exact ``wikipedia_pharm`` quote is skipped, so re-running with the
same judged file changes nothing.

Usage (from the repo root), then regenerate + check::

    python tools/sourcing/apply_binding_directions.py --dry-run
    python tools/sourcing/apply_binding_directions.py
    uv run --with beautifulsoup4 python tools/sourcing/apply_binding_directions.py --tables --dry-run
    uv run --with beautifulsoup4 python tools/sourcing/apply_binding_directions.py --tables
    python tools/generate_data.py && python tools/check_data.py

Stdlib only (``--tables`` imports the resolver, and so bs4, lazily); author-side (the gate needs the gitignored corpus #9 page tree, so on a
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
TABLES = os.path.join(CACHE, "binding_directions_tables.json")
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
    gate = _Gate(read_page)
    stats, rejected, reject = gate.stats, gate.rejected, gate.reject

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

            gate.write(drug, target, action, quote, slug, label,
                       names_target=lambda: ta.mentions(quote, aliases.get(target, [])))
    return stats, rejected


class _Gate:
    """Gates 3 to 6 and the write, shared by both inputs (a judged sentence, a table row).

    Holds the tally, the rejection log and the page cache so each caller only supplies
    what differs: how gate 5 decides the quote names the target, and how the source is
    stamped (a chosen sentence carries no ``extraction``; a copied cell is ``code``).
    """

    def __init__(self, read_page, extraction: str | None = None) -> None:
        self.read_page = read_page
        self.extraction = extraction
        self.stats: collections.Counter = collections.Counter()
        self.rejected: list[str] = []
        self.pages: dict[str, str | None] = {}

    def reject(self, why: str, detail: str) -> None:
        self.stats[f"rejected: {why}"] += 1
        self.rejected.append(f"[{why}] {detail}")

    def write(self, drug: dict, target: str, action: str, quote: str, slug: str,
              label: str, names_target) -> bool:
        binding = next((b for b in drug.get("bindings", [])
                        if b.get("target") == target), None)
        if binding is None:
            self.reject("no binding on that target", label)
            return False
        if _already_applied(binding, quote):
            self.stats["skipped: already applied"] += 1
            return False
        if not binding.get("affinity_only"):
            # Confirm-only: this pass fills a direction in, it never revises one.
            self.reject("binding already states a direction", label)
            return False
        if action not in DRUG_ACTIONS:
            self.reject("unknown action", label)
            return False
        if not names_target():
            self.reject("quote does not name the target", f"{label}: {quote[:80]}")
            return False
        if slug not in self.pages:
            self.pages[slug] = self.read_page(slug)
        body = self.pages[slug]
        if body is None:
            self.reject("no stored page for the citation", f"{label} ({slug})")
            return False
        if normalize_for_match(quote) not in body:
            self.reject("quote not verbatim on the cited page", f"{label}: {quote[:80]}")
            return False

        binding.pop("affinity_only", None)
        binding["action"] = action
        source = {"corpus": CORPUS, "page": slug, "quote": quote, "provenance": "verified"}
        if self.extraction:
            source["extraction"] = self.extraction
        binding.setdefault("sources", []).append(source)
        self.stats[f"node: {action}"] += 1
        return True


def apply_tables(proposals: dict, drugs: list[dict], read_page,
                 resolve) -> tuple[collections.Counter, list[str]]:
    """Run the gates over the table proposals, writing the survivors onto ``drugs``.

    Parameters
    ----------
    proposals : dict
        ``{drug id: {slug, rows: [{target, wiki_name, cell, action, quote}, ...]}}``.
    drugs : list of dict
        The authored drug records, **mutated in place** for every row that passes.
    read_page : callable
        ``slug -> normalized page text or None``.
    resolve : callable
        ``wiki_name -> target id or None``, the fetcher's own resolver, injected so the
        gate is testable without bs4 and can never accept a name the fetcher could not
        have offered.
    """
    by_drug = {d["id"]: d for d in drugs}
    gate = _Gate(read_page, extraction="code")
    for drug_id in sorted(proposals):
        drug = by_drug.get(drug_id)
        rec = proposals[drug_id]
        if drug is None:
            gate.reject("drug not in the dataset", drug_id)
            continue
        for row in rec.get("rows", []):
            target, action, quote = row.get("target"), row.get("action"), row.get("quote")
            name = row.get("wiki_name") or ""
            label = f"{drug_id} {target}/{action} cell={row.get('cell')!r}"
            if not isinstance(quote, str) or not quote:
                gate.reject("no quote on the row", label)
                continue
            # Gate 5 for a table row: the row text opens with the target cell, and that
            # cell resolves to the target the row claims.
            gate.write(drug, target, action, quote, rec.get("slug", ""), label,
                       names_target=lambda: bool(name) and quote.startswith(name)
                       and resolve(name) == target)
    return gate.stats, gate.rejected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--verbose", action="store_true", help="list every rejected row")
    ap.add_argument("--judged", default=JUDGED, help="judged file to apply")
    ap.add_argument("--tables", nargs="?", const=TABLES, metavar="FILE",
                    help="apply the table-column proposals instead (default file: "
                         f"{os.path.relpath(TABLES, REPO)})")
    args = ap.parse_args()

    if not os.path.isdir(PAGES):
        print(f"missing the author-side corpus tree ({PAGES}); see CLAUDE.local.md",
              file=sys.stderr)
        return 1
    inputs = (args.tables,) if args.tables else (WORKLIST, args.judged)
    for path in inputs:
        if not os.path.exists(path):
            print(f"missing {os.path.relpath(path, REPO)}", file=sys.stderr)
            return 1

    drugs = drugs_io.load_drugs()
    if args.tables:
        # The fetcher's resolver, imported here only: it needs bs4, which the judged
        # path (and a plain clone running the tests) does not.
        sys.path.insert(0, os.path.join(REPO, "tools", "fetch"))
        try:
            import fetch_wikipedia_pharmacology as wiki  # noqa: E402
        except ModuleNotFoundError as exc:
            print(f"--tables needs the fetcher's resolver ({exc}); run it as\n"
                  "  uv run --with beautifulsoup4 python "
                  "tools/sourcing/apply_binding_directions.py --tables", file=sys.stderr)
            return 1
        valid_ids = wiki.load_valid_ids()
        with open(args.tables, encoding="utf-8") as f:
            proposals = json.load(f)
        stats, rejected = apply_tables(proposals, drugs, page_text,
                                       lambda name: wiki.resolve_wiki_target(name, valid_ids))
    else:
        with open(WORKLIST, encoding="utf-8") as f:
            worklist = json.load(f)
        with open(args.judged, encoding="utf-8") as f:
            judged = json.load(f)
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
