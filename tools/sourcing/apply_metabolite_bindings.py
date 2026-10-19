#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "beautifulsoup4>=4.12",
# ]
# ///
"""Merge LLM-extracted metabolite receptor bindings into ``metabolites_data.jsonl``.

Run under ``uv run`` (a ``beautifulsoup4`` dep) because it reuses
``fetch_wikipedia_pharmacology`` for the Ki-object + page-store helpers, and that module
imports BeautifulSoup at load time; no HTML is parsed here.


This is the applier half of the metabolite-bindings pass (see docs/DRUGS.md "Drugs" ->
"Half-life + active metabolites", and its fetcher ``tools/fetch/fetch_metabolite_bindings.py``).
It is the SOLE writer of a non-modeled metabolite's ``bindings`` list, and idempotent:
each run rebuilds that list entirely from the worklist + the judge's picks, so re-running
just refreshes.

Pipeline (mirrors the brand / PK / Wikipedia-Ki passes)::

    fetch_metabolite_bindings.py  -> metabolite_bindings_worklist.json  (Ki rows + action lines)
    <one LLM pass>                -> metabolite_bindings_judged.json     (per-metabolite actions)
    apply_metabolite_bindings.py  -> metabolites_data.jsonl              (this script)

What a metabolite binding is made of (decision recorded in docs/DRUGS.md):

* **Target + action** come from the metabolite's OWN Wikipedia prose (corpus #9
  ``wikipedia_pharm``): the judge assigns an action (a ``DRUG_ACTIONS`` key) to a target
  and cites a verbatim sentence, which this script re-gates against the stored page
  (``pages/<slug>.md``) exactly like ``check_data.py`` will. A quote that fails the gate,
  or an unknown target/action, is DROPPED (never guessed).
* **Affinity (Ki)** is "Wikipedia primary, backfilled with PDSP": for every Ki-table
  target the fetcher found, a PDSP measured Ki (corpus #5) is preferred when one exists
  for the metabolite's own name, else the Wikipedia table value is kept. Every Ki-table
  target the judge did NOT give an action to is added as an ``affinity_only`` binding (a
  measured value, no functional direction), mirroring the drug-level Wikipedia pass.

So an action binding may carry a Ki or not (a prose-only claim like norquetiapine's NET
reuptake inhibition has no affinity table), and an affinity-only binding always carries a
Ki (it would be meaningless otherwise).

Usage (from the repo root; no network)::

    python tools/sourcing/apply_metabolite_bindings.py
    python tools/sourcing/apply_metabolite_bindings.py --dry-run   # report, write nothing

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
from lib.page_file import page_path  # noqa: E402 (refuses a path-like id)
from lib import drugs_io                                                 # noqa: E402
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
import fetch_ki                                                 # noqa: E402  (PDSP Ki lookup)
import fetch_wikipedia_pharmacology as wp                       # noqa: E402  (Ki obj + page store)
from lib.corpora import wikipedia as wikistore  # noqa: E402  (the corpus #9 store)
from data_generators.drugs import DRUG_ACTIONS                  # noqa: E402  (valid action keys)

WORKLIST = ROOT / "tools" / "generated_cache" / "metabolite_bindings_worklist.json"
JUDGED = ROOT / "tools" / "generated_cache" / "metabolite_bindings_judged.json"

# The applier's one quote gate (check_data's canonical normalization, single source of
# truth), so a quote that passes here also passes check_data's later re-gate. Over every
# corpus's page tree: the metabolite's own and parent Wikipedia articles (corpus #9) and
# any corpus a judged pick cites outright. Pages are read once per run and cached.
from pipeline.gate import PageGate, registry_pages  # noqa: E402

GATE = PageGate(registry_pages())


def _permalink(slug: str) -> str:
    """The revision permalink stamped into raw/<slug>.html (cited by a Wikipedia Ki)."""
    try:
        html = open(page_path(wikistore.RAW_DIR, slug, ".html"), encoding="utf-8").read()
    except OSError:
        return ""
    return wikistore.stored_meta(html)[1]


def _pdsp_ki(name: str, target: str) -> dict | None:
    """A measured PDSP Ki for (metabolite name, target), or None. Preferred over the
    Wikipedia table value when it exists (a raw assay beats a literature figure)."""
    rows = fetch_ki.rows_by_name(name)
    if rows is None:   # no PDSP CSV on this checkout: keep the Wikipedia value
        return None
    s = fetch_ki.summarize_target(rows, target)
    if s and s.get("ki_nm"):
        return fetch_ki._ki_from_summary(s)
    return None


def build_bindings(metab_name: str, entry: dict, judged: dict,
                   valid_ids: set[str], warn) -> list[dict]:
    """Build one metabolite's ``bindings`` list from its worklist entry + judge picks.

    ``entry`` is the fetcher worklist record (slug, ki_bindings, ...); ``judged`` is the
    LLM's ``{"bindings": [{target, action, quote}, ...]}`` for this metabolite; a pick
    carrying ``corpus`` + ``page`` is gated on that cited page instead of the articles. Returns
    the emitted binding dicts (action bindings first, then affinity-only Ki rows)."""
    slug = entry["slug"]
    # A judged action quote may come from the metabolite's OWN article OR its parent's
    # (the #3 relaxation the fetcher now collects both), so gate against EACH candidate
    # page and record the matching one as the source page. Ki-table objects still cite the
    # own article (`slug`), where the affinity table lives.
    pages = entry.get("pages") or [slug]
    wiki_ki = {b["target"]: b for b in entry.get("ki_bindings", [])}

    def ki_for(target: str) -> dict | None:
        pdsp = _pdsp_ki(metab_name, target)
        if pdsp:
            return pdsp
        w = wiki_ki.get(target)
        if not w:
            return None
        page = w.get("page", slug)          # a compound-table row may sit on the parent's page
        return wp._wiki_ki_obj(w, page, _permalink(page))

    def gate(quote: str | None) -> str | None:
        """The slug whose stored page contains ``quote`` verbatim, or None. Tried in page
        order (own article first), so the recorded source page is the closest attribution."""
        if not quote:
            return None
        return next((s for s in pages if GATE.on_page("wikipedia_pharm", s, quote)), None)

    def gate_cited(corpus: str, page) -> bool:
        """Whether ``quote`` sits verbatim on the page an explicitly cited corpus names
        (a paper stating what no Wikipedia article does, e.g. a Europe PMC abstract)."""
        return GATE.on_page(corpus, page, quote)

    out, emitted = [], set()
    for jb in (judged or {}).get("bindings", []):
        target, action, quote = jb.get("target"), jb.get("action"), jb.get("quote")
        if target not in valid_ids:
            warn(f"{metab_name}: unknown target {target!r} - dropped")
            continue
        if action not in DRUG_ACTIONS:
            warn(f"{metab_name}: unknown action {action!r} for {target} - dropped")
            continue
        if jb.get("corpus"):
            # A judged pick may cite another corpus outright ({corpus, page, quote}).
            if not quote or not gate_cited(jb["corpus"], jb.get("page")):
                warn(f"{metab_name}: quote for {target} not verbatim on "
                     f"{jb['corpus']} page {jb.get('page')} - dropped")
                continue
            src = {"corpus": jb["corpus"], "page": jb["page"]}
        else:
            src_slug = gate(quote)
            if not src_slug:
                warn(f"{metab_name}: quote for {target} not verbatim on any of {pages} - dropped")
                continue
            src = {"corpus": "wikipedia_pharm", "page": src_slug}
        if target in emitted:
            continue
        emitted.add(target)
        b = {"target": target, "action": action,
             "sources": [{**src, "quote": quote, "provenance": "verified"}]}
        ki = ki_for(target)
        if ki:
            b["ki"] = ki
        out.append(b)

    # Every Ki-table target the judge left without an action -> affinity_only (a measured
    # value, no direction), exactly like the drug-level Wikipedia pass keeps the whole
    # curated table rather than only the strongest rows.
    for target in sorted(wiki_ki):
        if target in emitted:
            continue
        ki = ki_for(target)
        if ki:
            out.append({"target": target, "affinity_only": True, "ki": ki})
            emitted.add(target)

    # PDSP-discovered targets (corpus #5) with no Wikipedia table row and no judged action
    # -> affinity_only. This is the "use PDSP directly" path: a measured Ki on the
    # metabolite's own name with no known functional direction (norfluoxetine's 15 sites),
    # mirroring the drug-level PDSP affinity_only rows. A verified CSV-row source.
    for pt in entry.get("pdsp_targets", []):
        target = pt["target"]
        if target in emitted:
            continue
        ki = _pdsp_ki(metab_name, target)
        if ki:
            out.append({"target": target, "affinity_only": True, "ki": ki})
            emitted.add(target)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change, write nothing")
    ap.add_argument("--only", help="comma-separated PARENT drug ids whose metabolites to "
                    "rebuild (later passes, e.g. binding directions, write onto these "
                    "lists, so a full re-run is not a no-op)")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None

    worklist = {e["key"]: e for e in worklist_io.read(WORKLIST)}
    judged = worklist_io.read(JUDGED, required=False, default={})
    valid_ids = wikistore.load_valid_ids()
    drugs = drugs_io.load_drugs()
    store = drugs_io.load_metabolites()
    by_id = {m["id"]: m for m in store}

    warnings: list[str] = []
    warn = warnings.append
    n_metab = n_bind = n_action = n_affinity = 0
    # One pass per MOLECULE (the store), so a metabolite two drugs make is sourced
    # once; a modeled-drug metabolite reuses that drug's bindings, so any inline copy
    # is cleared.
    modeled = {m["id"] for m in store} - {
        m["id"] for m in drugs_io.non_modeled_metabolites(drugs, store)}
    for mm in drugs_io.non_modeled_metabolites(drugs, store):
        if only is not None and not only & set(mm["parents"]):
            continue
        m = by_id[mm["id"]]
        key = wikistore.title_slug(m["name"]).lower()
        entry = worklist.get(key)
        if not entry:
            warn(f"{m['name']}: no worklist entry (run the fetcher) - skipped")
            m.pop("bindings", None)
            continue
        bindings = build_bindings(m["name"], entry, judged.get(key), valid_ids, warn)
        if bindings:
            m["bindings"] = bindings
            n_metab += 1
            n_bind += len(bindings)
            n_action += sum(1 for b in bindings if not b.get("affinity_only"))
            n_affinity += sum(1 for b in bindings if b.get("affinity_only"))
        else:
            m.pop("bindings", None)
    for mid in modeled:
        by_id[mid].pop("bindings", None)

    for w in warnings:
        print(f"  warn: {w}")
    print(f"\n{n_metab} metabolite(s) given bindings: {n_bind} total "
          f"({n_action} with an action, {n_affinity} affinity-only)")
    if args.dry_run:
        print("(dry run: nothing written)")
        return 0
    drugs_io.save_metabolites(store)
    print(f"wrote {drugs_io.METABOLITES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
