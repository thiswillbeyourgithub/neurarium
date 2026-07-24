#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "beautifulsoup4>=4.12",
# ]
# ///
"""Merge LLM-extracted metabolite receptor bindings into ``drugs_data.jsonl``.

Run under ``uv run`` (a ``beautifulsoup4`` dep) because it reuses
``fetch_wikipedia_pharmacology`` for the Ki-object + page-store helpers, and that module
imports BeautifulSoup at load time; no HTML is parsed here.


This is the applier half of the metabolite-bindings pass (see CLAUDE.md "Drugs" ->
"Half-life + active metabolites", and its fetcher ``tools/fetch/fetch_metabolite_bindings.py``).
It is the SOLE writer of a non-modeled metabolite's ``bindings`` list, and idempotent:
each run rebuilds that list entirely from the worklist + the judge's picks, so re-running
just refreshes.

Pipeline (mirrors the brand / PK / Wikipedia-Ki passes)::

    fetch_metabolite_bindings.py  -> metabolite_bindings_worklist.json  (Ki rows + action lines)
    <one LLM pass>                -> metabolite_bindings_judged.json     (per-metabolite actions)
    apply_metabolite_bindings.py  -> drugs_data.jsonl                    (this script)

What a metabolite binding is made of (decision recorded in CLAUDE.md):

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
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
import drugs_io                                                 # noqa: E402
import fetch_ki                                                 # noqa: E402  (PDSP Ki lookup)
import fetch_wikipedia_pharmacology as wp                       # noqa: E402  (Ki obj + page store)
from data_generators.drugs import DRUG_ACTIONS                  # noqa: E402  (valid action keys)

WORKLIST = ROOT / "tools" / "generated_cache" / "metabolite_bindings_worklist.json"
JUDGED = ROOT / "tools" / "generated_cache" / "metabolite_bindings_judged.json"

# Reuse check_data's canonical quote-gate normalization (single source of truth), so a
# quote that passes here also passes check_data's later re-gate.
_spec = importlib.util.spec_from_file_location("cd", ROOT / "tools" / "check_data.py")
_cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cd)
normalize_for_match = _cd.normalize_for_match


def norm_name(s: str) -> str:
    """Fold a name for id/key matching (lowercase, alphanumerics only)."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _page_text(slug: str) -> str | None:
    """The stored corpus #9 page text for a slug (the quote-gate target), or None."""
    p = wp.PAGES_DIR + f"/{slug}.md"
    try:
        return open(p, encoding="utf-8").read()
    except OSError:
        return None


def _permalink(slug: str) -> str:
    """The revision permalink stamped into raw/<slug>.html (cited by a Wikipedia Ki)."""
    try:
        html = open(wp.RAW_DIR + f"/{slug}.html", encoding="utf-8").read()
    except OSError:
        return ""
    return wp._stored_meta(html)[1]


def _pdsp_ki(name: str, target: str) -> dict | None:
    """A measured PDSP Ki for (metabolite name, target), or None. Preferred over the
    Wikipedia table value when it exists (a raw assay beats a literature figure)."""
    try:
        rows = fetch_ki.resolve_rows(name, None)
        s = fetch_ki.summarize_target(rows, target)
    except Exception:
        return None
    if s and s.get("ki_nm"):
        return fetch_ki._ki_from_summary(s)
    return None


def build_bindings(metab_name: str, entry: dict, judged: dict,
                   valid_ids: set[str], warn) -> list[dict]:
    """Build one metabolite's ``bindings`` list from its worklist entry + judge picks.

    ``entry`` is the fetcher worklist record (slug, ki_bindings, ...); ``judged`` is the
    LLM's ``{"bindings": [{target, action, quote}, ...]}`` for this metabolite. Returns
    the emitted binding dicts (action bindings first, then affinity-only Ki rows)."""
    slug = entry["slug"]
    page = _page_text(slug)
    permalink = _permalink(slug)
    wiki_ki = {b["target"]: b for b in entry.get("ki_bindings", [])}

    def ki_for(target: str) -> dict | None:
        pdsp = _pdsp_ki(metab_name, target)
        if pdsp:
            return pdsp
        w = wiki_ki.get(target)
        return wp._wiki_ki_obj(w, slug, permalink) if w else None

    out, actioned = [], set()
    for jb in (judged or {}).get("bindings", []):
        target, action, quote = jb.get("target"), jb.get("action"), jb.get("quote")
        if target not in valid_ids:
            warn(f"{metab_name}: unknown target {target!r} - dropped")
            continue
        if action not in DRUG_ACTIONS:
            warn(f"{metab_name}: unknown action {action!r} for {target} - dropped")
            continue
        if not quote or page is None or normalize_for_match(quote) not in \
                normalize_for_match(page):
            warn(f"{metab_name}: quote for {target} not verbatim on {slug} - dropped")
            continue
        if target in actioned:
            continue
        actioned.add(target)
        b = {"target": target, "action": action,
             "sources": [{"corpus": "wikipedia_pharm", "page": slug,
                          "quote": quote, "provenance": "verified"}]}
        ki = ki_for(target)
        if ki:
            b["ki"] = ki
        out.append(b)

    # Every Ki-table target the judge left without an action -> affinity_only (a measured
    # value, no direction), exactly like the drug-level Wikipedia pass keeps the whole
    # curated table rather than only the strongest rows.
    for target in sorted(wiki_ki):
        if target in actioned:
            continue
        ki = ki_for(target)
        if ki:
            out.append({"target": target, "affinity_only": True, "ki": ki})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change, write nothing")
    args = ap.parse_args()

    worklist = {e["key"]: e for e in json.loads(WORKLIST.read_text(encoding="utf-8"))}
    judged = json.loads(JUDGED.read_text(encoding="utf-8")) if JUDGED.exists() else {}
    valid_ids = wp.load_valid_ids()
    drugs = drugs_io.load_drugs()
    drug_ids = {d["id"] for d in drugs}
    by_norm = {norm_name(d.get("name", "")): d["id"] for d in drugs}

    warnings: list[str] = []
    warn = warnings.append
    n_metab = n_bind = n_action = n_affinity = 0
    for d in drugs:
        for m in d.get("metabolites", []):
            # Only non-modeled metabolites are sourced here; a metabolite that IS a
            # modeled drug reuses that drug's bindings (js/data.js), nothing to write.
            linked = m.get("drug_id") or by_norm.get(norm_name(m["name"]))
            if linked and linked in drug_ids:
                continue
            key = wp.slugify(m["name"]).lower()
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

    for w in warnings:
        print(f"  warn: {w}")
    print(f"\n{n_metab} metabolite(s) given bindings: {n_bind} total "
          f"({n_action} with an action, {n_affinity} affinity-only)")
    if args.dry_run:
        print("(dry run: nothing written)")
        return 0
    drugs_io.save_drugs(drugs)
    print(f"wrote {drugs_io.DRUGS_PATH if hasattr(drugs_io, 'DRUGS_PATH') else 'drugs_data.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
