#!/usr/bin/env python
"""Quote-gate the judged binding directions and write them onto ``drugs_data.jsonl``.

The apply half of the binding-direction pass (see docs/DRUGS.md "Drugs" -> "Binding
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
   under ``lib.quote_match.normalize_for_match`` rather than trusted from the worklist.

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
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))

import drugs_io  # noqa: E402
import worklist_io  # noqa: E402 (the one judged / worklist reader)
from io_atomic import atomic_write_json  # noqa: E402
import target_aliases as ta  # noqa: E402  (the same matcher the fetcher offered with)
from pipeline.gate import PageGate, Tally, registry_pages  # noqa: E402 (the applier's page gate)
from pipeline.judged import resolve  # noqa: E402
from data_generators.drugs import DRUG_ACTIONS  # noqa: E402  (the live action vocabulary)

CORPUS = "wikipedia_pharm"
CACHE = os.path.join(REPO, "tools", "generated_cache")
WORKLIST = os.path.join(CACHE, "binding_directions_worklist.json")
JUDGED = os.path.join(CACHE, "binding_directions_judged.json")
TABLES = os.path.join(CACHE, "binding_directions_tables.json")
PAGES = os.path.join(REPO, "data_sources", "wikipedia", "pages")


# The real page store behind the injectable readers below (tests pass their own).
_STORE = PageGate(registry_pages())


def page_text(slug: str) -> str | None:
    """The stored corpus #9 article a quote cites, normalized, or None when absent."""
    return _STORE.text(CORPUS, slug)


def _already_applied(binding: dict, quote: str, corpus: str = CORPUS) -> bool:
    """Whether this binding already cites that exact quote of that corpus.

    Checked before the affinity-only gate so a second run reads as a no-op rather than
    as a pile of rejections: after the first run the binding is, correctly, no longer
    affinity-only.
    """
    return any(src.get("corpus") == corpus and src.get("quote") == quote
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
    gate = BindingGate(read_page)
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

            cand, why = resolve(cands, row)
            if why:
                reject(why, label)
                continue
            quote = cand["line"]

            gate.write(drug, target, action, quote, slug, label,
                       names_target=lambda: ta.mentions(quote, aliases.get(target, [])))
    return stats, rejected


class BindingGate(Tally):
    """Gates 3 to 6 and the write, shared by both inputs (a judged sentence, a table row)
    and by ``apply_binding_gaps``.

    Holds the tally, the rejection log and the page cache (a :class:`PageGate`) so each
    caller only supplies what differs: how gate 5 decides the quote names the target, and
    how the source is stamped (a chosen sentence carries no ``extraction``; a copied cell
    is ``code``). ``read_page(slug)`` reads corpus #9; ``read_other(corpus, page)`` any
    other corpus (the --search input cites French Wikipedia and Europe PMC abstracts too).
    """

    def __init__(self, read_page, extraction: str | None = None, read_other=None) -> None:
        super().__init__()
        self.pages = PageGate(read=lambda corpus, page: (
            read_page(page) if corpus == CORPUS
            else read_other(corpus, page) if read_other else None))
        self.extraction = extraction

    def quote_on_page(self, corpus: str, slug: str, quote: str, label: str) -> bool:
        """Gate 6: ``quote`` is verbatim on the cited stored page (rejects otherwise)."""
        if self.pages.text(corpus, slug) is None:
            self.reject("no stored page for the citation", f"{label} ({slug})")
            return False
        if not self.pages.on_page(corpus, slug, quote):
            self.reject("quote not verbatim on the cited page", f"{label}: {quote[:80]}")
            return False
        return True

    def write(self, drug: dict, target: str, action: str, quote: str, slug: str,
              label: str, names_target, corpus: str = CORPUS) -> bool:
        """``drug`` is any record holding ``bindings`` (a drug, or a metabolite)."""
        binding = next((b for b in drug.get("bindings", [])
                        if b.get("target") == target), None)
        if binding is None:
            self.reject("no binding on that target", label)
            return False
        if _already_applied(binding, quote, corpus):
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
        if not self.quote_on_page(corpus, slug, quote, label):
            return False

        binding.pop("affinity_only", None)
        binding["action"] = action
        source = {"corpus": corpus, "page": slug, "quote": quote, "provenance": "verified"}
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
    gate = BindingGate(read_page, extraction="code")
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


# ---------------------------------------------------------------------------
# --search: the UNKNOWN search's picks (fetch_binding_directions.py --search), then
# --unknown-log: the search log of every binding the search left without a direction.
# ---------------------------------------------------------------------------
SEARCH_WORKLIST = os.path.join(CACHE, "binding_directions_search_worklist.json")
SEARCH_JUDGED = os.path.join(CACHE, "binding_directions_search_judged.json")


def read_other(corpus: str, page) -> str | None:
    """Any other corpus's stored page (French Wikipedia, a Europe PMC abstract),
    normalized, or None when absent (the tree is author-side)."""
    return _STORE.text(corpus, page)


def _owners(drugs: list[dict], rec: dict, metabolites: list[dict] = ()) -> list[dict]:
    """The record holding a search record's binding: the drug, or the metabolite's one
    store record (one molecule, one record, whatever its parents)."""
    from data_generators import unknown
    if not rec.get("metabolite"):
        return [d for d in drugs if d["id"] == rec["drug"]]
    want = unknown.fold(rec["metabolite"])
    return [m for m in metabolites if unknown.fold(m.get("name")) == want]


def apply_search(worklist: list[dict], judged: dict, drugs: list[dict], read_page,
                 read_other_page, metabolites: list[dict] = ()
                 ) -> tuple[collections.Counter, list[str]]:
    """Gate the picks over the search worklist (``{site: {index, action}}``), same gates
    as :func:`apply`, the citation carrying the candidate's own corpus and page."""
    by_site = {rec["site"]: rec for rec in worklist}
    aliases = ta.aliases_by_target()
    gate = BindingGate(read_page, read_other=read_other_page)
    for site in sorted(judged):
        rec, row = by_site.get(site), judged[site]
        index, action = row.get("index"), row.get("action")
        label = f"{site} {action} index={index}"
        if rec is None:
            gate.reject("site not in the search worklist", site)
            continue
        cand, why = resolve(rec["candidates"], row)
        if why:
            gate.reject(why, label)
            continue
        target = rec["target"]
        owners = _owners(drugs, rec, metabolites)
        if not owners:
            gate.reject("no record holds that binding", label)
            continue
        for owner in owners:
            gate.write(owner, target, action, cand["line"], cand["page"], label,
                       names_target=lambda: ta.mentions(cand["line"], aliases.get(target, [])),
                       corpus=cand["corpus"])
    return gate.stats, gate.rejected


def unknown_log(worklist: list[dict], drugs: list[dict], by: dict,
                prior: dict | None = None, metabolites: list[dict] = ()) -> dict:
    """The UNKNOWN search log: every worklist binding still without a direction, whose
    search found no direction anywhere (``elsewhere`` empty), keyed by its site.

    Entries the search did not revisit are kept from ``prior`` (a scoped rerun must not
    erase them); ``apply_unknown`` drops any whose binding gained a source since.
    """
    from data_generators import unknown
    still = {r["site"] for r in unknown.affinity_only_bindings(drugs, metabolites)}
    log = dict(prior or {})
    for rec in worklist:
        site = rec["site"]
        if site not in still or rec["elsewhere"]:
            log.pop(site, None)
            continue
        dates = [s["searched"] for s in rec["searched"] if s.get("searched")]
        log[site] = {"kind": "drug_binding_action",
                     # The oldest leg dates the search: it expires from there.
                     "searched": min(dates) if dates else by["date"],
                     "by": {"harness": by["harness"], "model": by["model"]},
                     "candidates_offered": len(rec["candidates"]),
                     "sources": [{k: v for k, v in s.items() if k != "searched"}
                                 for s in rec["searched"]]}
    return log


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--verbose", action="store_true", help="list every rejected row")
    ap.add_argument("--judged", default=JUDGED, help="judged file to apply")
    ap.add_argument("--tables", nargs="?", const=TABLES, metavar="FILE",
                    help="apply the table-column proposals instead (default file: "
                         f"{os.path.relpath(TABLES, REPO)})")
    ap.add_argument("--search", action="store_true",
                    help="apply the UNKNOWN search's picks (binding_directions_search_*)")
    ap.add_argument("--unknown-log", action="store_true",
                    help="write the UNKNOWN log for every searched binding still "
                         "without a direction (run after the recheck)")
    ap.add_argument("--model", default="opus", help="the model that picked (for the log)")
    args = ap.parse_args()
    if args.search or args.unknown_log:
        return _main_search(args)

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
        proposals = worklist_io.read(args.tables)
        stats, rejected = apply_tables(proposals, drugs, page_text,
                                       lambda name: wiki.resolve_wiki_target(name, valid_ids))
    else:
        worklist = worklist_io.read(WORKLIST)
        judged = worklist_io.read(args.judged)
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



def _main_search(args) -> int:
    import datetime
    from data_generators import unknown
    worklist = worklist_io.read(SEARCH_WORKLIST)
    drugs = drugs_io.load_drugs()
    metabolites = drugs_io.load_metabolites()
    if args.search:
        judged = worklist_io.read(SEARCH_JUDGED)
        stats, rejected = apply_search(worklist, judged, drugs, page_text, read_other,
                                       metabolites)
        for key, n in sorted(stats.items()):
            print(f"  {key:<48} {n}")
        for line in rejected if args.verbose else []:
            print(f"    {line}")
    else:
        log = unknown_log(worklist, drugs, {"harness": "Claude Code", "model": args.model,
                                            "date": datetime.date.today().isoformat()},
                          unknown.load_log(), metabolites)
        print(f"  UNKNOWN log: {len(log)} binding(s)")
        if not args.dry_run:
            atomic_write_json(unknown.UNKNOWN_LOG_PATH, log, indent=1, sort_keys=True)
        return 0
    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    drugs_io.save_drugs(drugs)
    drugs_io.save_metabolites(metabolites)
    print(f"wrote {drugs_io.DRUGS_PATH.relative_to(REPO)} + "
          f"{drugs_io.METABOLITES_PATH.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
