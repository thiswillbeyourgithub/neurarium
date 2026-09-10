#!/usr/bin/env python
"""Remove, by quote id, a source that a judge found does not back its claim.

The recheck pipeline (``recheck_quotes.py``) ends by flagging quotes that are verbatim
on their cited page but do not substantiate the claim they were attached to. A flag is
not an outcome: while the source is still stored, the node keeps its green ``verified``
pill and the reader is told a sentence backs a claim it does not. Either a better
sentence replaces it (a re-extraction pass, see ``--replace``) or the source has to go,
and the node falls back to the grade it deserves without it (usually ``llm``, sometimes
``NOSOURCE``). This applies that second half.

**It removes the source, never the claim.** A drug that loses its class quote is still
classified; it just no longer says a book said so. Deciding whether the claim itself is
wrong is a separate, human judgement, and this tool deliberately does not make it.

Sources live in two machine-writable places, and this walks both:

* ``tools/data/drugs_data.jsonl`` (bindings, NbN, class, brands, half-life, metabolites
  and their bindings / formed_by rows);
* ``tools/generated_cache/*.json`` (the applier-written caches: expression locations,
  classifications, the two enzyme caches, expression density).

Anything else is hand-authored Python (``tools/data_generators/quotes/*.py`` and the
registries in ``provenance.py``), which no script should be rewriting. Those ids are
**reported, not touched**, with their corpus/page/quote so the authoring site can be
found by grep. Nothing is silently skipped.

Matching is by the same content hash the emitted data uses (``quote_table.quote_id``
over corpus + page + quote + species), so an id from ``quote_recheck_flagged.json``,
from a verdicts file, or read off ``quotes.jsonl`` all resolve to the same sources. One
excerpt cited by several claims is removed from every one of them **unless the verdict
says which claim it failed**: a sentence can honestly back the binding and not the
class, so a target may carry ``"sites"``, the citation sites (see ``citation_site.py``)
the demotion applies at. The quote's other citations keep their source, and the quote
keeps its judging stamp. A site that matches nothing is reported rather than passing for
a run that changed nothing.

Usage:
    python tools/sourcing/demote_quotes.py --flagged            # every flagged quote
    python tools/sourcing/demote_quotes.py --ids q_a,q_b [--dry-run]
    python tools/sourcing/demote_quotes.py --replace PROPOSALS.json
    python tools/sourcing/demote_quotes.py --ids q_a --sites drug:clozapine/categories

``--replace`` takes a re-extraction pass's proposals
(``{"proposals": {qid: {"found": true, "quote": "..."}}}``): a proposal with a
replacement rewrites the source's ``quote`` in place (re-gated against the cited page,
exactly like every other applier, so a paraphrase is rejected), and a proposal with
``found: false`` falls through to removal. Idempotent: a second run finds nothing.

Stdlib only; authoring helper, not served. Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "tools", "generated_cache")
DRUGS = os.path.join(ROOT, "tools", "data", "drugs_data.jsonl")
DATA = os.path.join(ROOT, "public", "data")

sys.path.insert(0, os.path.join(ROOT, "tools"))
from data_generators.quote_table import quote_id  # noqa: E402
from check_data import normalize_for_match  # noqa: E402
import citation_site as CS  # noqa: E402

# The applier-written caches that can hold a quote-bearing source. The hand-authored
# registries are deliberately absent: see the module docstring.
CACHE_FILES = ("location_sources.json", "classification_sources.json",
               "drug_enzymes.json", "drug_enzymes_wikipedia.json",
               "expression_density.json", "enzyme_variability.json")


def _is_source(obj) -> bool:
    """A dict carrying a verbatim ``quote`` string, i.e. a quote-bearing source."""
    return isinstance(obj, dict) and isinstance(obj.get("quote"), str) and "corpus" in obj


def _dedupe_sources(members: list) -> list:
    """``members`` with any repeated source collapsed onto its first occurrence.

    A re-extraction can propose the sentence a sibling citation already carries (two
    quotes cited from one node often failed for the same reason and are repaired the same
    way), and two identical citations on one node are one citation: the viewer would draw
    the same pill twice and the excerpt table, keyed by content hash, would fold them
    back together anyway.
    """
    seen, out = set(), []
    for m in members:
        if _is_source(m):
            key = quote_id(m)
            if key in seen:
                continue
            seen.add(key)
        out.append(m)
    return out


def _page_dirs() -> dict[str, str]:
    """``corpus -> author-side page directory``, read from the emitted registry."""
    with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as fh:
        corpora = json.load(fh).get("source_corpora", {})
    return {name: entry["pages_dir"] for name, entry in corpora.items()
            if entry.get("pages_dir")}


class Editor:
    """Walks a loaded JSON tree, rewriting or dropping the sources named by id."""

    def __init__(self, targets: dict[str, dict], pages: dict[str, str]):
        # qid -> {} to remove, {"quote": "..."} to rewrite in place, either of them
        # optionally narrowed by "sites" to some of the quote's citations (see
        # citation_site.py): one sentence can back the binding and not the class.
        self.targets = targets
        self.pages = pages
        self.removed: list[str] = []
        self.replaced: list[str] = []
        self.rejected: list[str] = []
        self.seen: set[str] = set()
        # Every site a narrowed target actually reached, so one that reached nothing can
        # be reported instead of passing for a silent no-op.
        self.hit_sites: set[str] = set()
        # Quotes a site filter spared at least one citation of: they keep their node, so
        # they must also keep their judging stamp.
        self.partial: set[str] = set()

    def _page_text(self, corpus, page):
        """The cited page, normalized, or ``None`` when the corpus is not on disk."""
        d = self.pages.get(corpus)
        if not d:
            return None
        md = os.path.join(ROOT, d, f"{page}.md")
        if not os.path.exists(md):
            return None
        with open(md, encoding="utf-8") as fh:
            return normalize_for_match(fh.read())

    def _apply_one(self, src, root=None, path=()):
        """``True`` when this source should be dropped from the list holding it."""
        qid = quote_id(src)
        if qid not in self.targets:
            return False
        self.seen.add(qid)
        target = self.targets[qid] or {}
        wanted = target.get("sites")
        if wanted:
            here = CS.resolve(root, list(path))
            if here not in wanted:
                # A citation the verdict did not name keeps its source: that is the whole
                # point of judging per claim rather than per sentence.
                self.partial.add(qid)
                return False
            self.hit_sites.add(here)
        new = target.get("quote")
        # A re-extraction that answers with the sentence it was asked to replace has
        # found nothing: writing it back would leave the rejected quote in place while
        # reporting a repair, so it falls through to removal like any other miss.
        if new is not None and new.strip() == (src.get("quote") or "").strip():
            new = None
        if not new:
            self.removed.append(qid)
            return True
        # A replacement is only worth as much as the gate behind it, so it goes through
        # the same verbatim check check_data.py will run on it later. A proposal that
        # does not match the page is not written at all, and the source is removed
        # instead: that is the honest fallback, not a silently-kept bad quote.
        text = self._page_text(src["corpus"], src.get("page"))
        if text is not None and normalize_for_match(new) not in text:
            self.rejected.append(qid)
            self.removed.append(qid)
            return True
        src["quote"] = new
        self.replaced.append(qid)
        return False

    def walk(self, node, root=None, path=()):
        """Rewrite ``node`` in place, returning it (a list may lose members).

        ``root`` + ``path`` are carried purely so a source can be addressed by its
        citation site; a caller that does not need per-claim targeting can ignore both.
        """
        if isinstance(node, list):
            out = []
            for i, v in enumerate(node):
                if _is_source(v) and self._apply_one(v, root, path):
                    continue
                out.append(self.walk(v, root, tuple(path) + (CS.member_label(v, i),)))
            return _dedupe_sources(out)
        if isinstance(node, dict):
            for k, v in list(node.items()):
                node[k] = self.walk(v, root, tuple(path) + (k,))
                # An emptied `sources` list is not the same as no sources: the key is
                # dropped so the node reads as unsourced rather than as sourced-by-none.
                if isinstance(node[k], list) and not node[k] and k.endswith("sources"):
                    del node[k]
            return node
        return node


def _targets(args) -> dict[str, dict]:
    """``qid -> {}`` (remove) or ``{"quote": ...}`` (replace), from the CLI."""
    out: dict[str, dict] = {}
    if args.flagged:
        path = os.path.join(CACHE, "quote_recheck_flagged.json")
        with open(path, encoding="utf-8") as fh:
            for row in json.load(fh):
                out[row["qid"]] = {}
    sites = [x.strip() for x in (args.sites or "").split(",") if x.strip()]
    for qid in (args.ids or "").split(","):
        if qid.strip():
            out[qid.strip()] = {"sites": sites} if sites else {}
    if args.replace:
        # A re-extraction pass answers one file per batch, so a directory is accepted
        # and merged rather than made someone's `jq` problem.
        paths = ([os.path.join(args.replace, n)
                  for n in sorted(os.listdir(args.replace)) if n.endswith(".json")]
                 if os.path.isdir(args.replace) else [args.replace])
        if not paths:
            sys.exit(f"{args.replace}: no proposal files in there")
        raw = {}
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                one = json.load(fh)
            for qid, p in (one.get("proposals", one) or {}).items():
                if qid in raw and raw[qid] != p:
                    sys.exit(f"{qid}: two batches proposed different things for it")
                raw[qid] = p
        for qid, p in raw.items():
            entry = {"quote": p["quote"]} if p.get("found") and p.get("quote") else {}
            if p.get("sites"):
                entry["sites"] = list(p["sites"])
            out[qid] = entry
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flagged", action="store_true",
                    help="target every quote in quote_recheck_flagged.json")
    ap.add_argument("--ids", default="", help="comma-separated quote ids")
    ap.add_argument("--replace", help="a re-extraction pass's proposals JSON")
    ap.add_argument("--sites", default="",
                    help="with --ids, narrow to these comma-separated citation "
                         "sites (see citation_site.py); the quote's other "
                         "citations are left alone")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    targets = _targets(args)
    if not targets:
        sys.exit("nothing to do: pass --flagged, --ids or --replace")

    ed = Editor(targets, _page_dirs())

    with open(DRUGS, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    rows = [ed.walk(r, "drugs_data.jsonl", (r.get("id"),)) for r in rows]
    if not args.dry_run:
        with open(DRUGS, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    for name in CACHE_FILES:
        path = os.path.join(CACHE, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data = ed.walk(data, name, ())
        if not args.dry_run:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)

    # A stamp on a quote nobody cites any more is dead weight, and a flag on one that
    # has been dealt with would be re-proposed by the next pass, so both are cleared.
    for name in ("quote_llm.json", "quote_recheck_flagged.json"):
        path = os.path.join(CACHE, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        # A quote a site filter only partly demoted still exists and still has judged
        # citations, so it keeps its stamp; the flag goes either way, since the verdict
        # it recorded has now been acted on.
        gone = set(ed.removed) - ed.partial
        done = ({q for q in ed.seen if not (targets[q] or {}).get("quote")} | gone
                if name == "quote_recheck_flagged.json" else gone)
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in done}
        else:
            data = [r for r in data if r.get("qid") not in ed.seen]
        if not args.dry_run:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False,
                          indent=0 if isinstance(data, dict) else 1, sort_keys=True)

    # A site that reached no citation is the one failure mode this abstraction adds:
    # the two ends name a claim differently and the demotion quietly does nothing. Say
    # so, loudly, rather than reporting a successful run that changed nothing.
    asked = {x for t in targets.values() for x in (t or {}).get("sites", [])}
    missed = sorted(asked - ed.hit_sites)
    unreachable = sorted(set(targets) - ed.seen)
    print(f"removed {len(ed.removed)} source(s), replaced {len(ed.replaced)}"
          + (f", rejected {len(ed.rejected)} replacement(s) as not verbatim on the page"
             if ed.rejected else "")
          + (" (dry run, nothing written)" if args.dry_run else ""))
    if missed:
        print(f"{len(missed)} citation site(s) matched nothing (check the spelling "
              f"against citation_site.py):")
        for site in missed:
            print(f"  {site}")
    if unreachable:
        # Hand-authored, so reported with enough to grep for rather than rewritten.
        quotes = {}
        with open(os.path.join(DATA, "quotes.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                q = json.loads(line)
                quotes[q["id"]] = q
        print(f"{len(unreachable)} quote(s) live in hand-authored Python; edit them "
              f"by hand (grep tools/data_generators/):")
        for qid in unreachable:
            q = quotes.get(qid, {})
            print(f"  {qid}  {q.get('corpus')} p.{q.get('page')}  "
                  f"{(q.get('quote') or '')[:70]!r}")


if __name__ == "__main__":
    main()
