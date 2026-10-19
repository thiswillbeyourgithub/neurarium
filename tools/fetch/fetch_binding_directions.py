#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "beautifulsoup4>=4.12",
# ]
# ///
"""Build the worklist that lets a drug's Wikipedia article state a binding's *direction*.

Why this exists
---------------
740 bindings in ``tools/data/drugs_data.jsonl`` are ``affinity_only``: PDSP (corpus #5)
or GtoPdb measured a Ki, so we know the drug engages the target, but nothing in the
corpora says what it *does* there. Such a binding never animates and its direction is a
NOSOURCE ``drug_binding_action`` node. Every one of the roster's drugs already has its
English Wikipedia article stored author-side (corpus #9 ``wikipedia_pharm``, see
``CLAUDE.local.md``), and an article routinely states in prose exactly what the assay
does not ("olanzapine is an antagonist at the 5-HT2C receptor"). This pass mines those
sentences.

It states **no verdict of its own**, exactly like ``fetch_cyp_worklist.py``: it offers
candidate sentences, already confirmed verbatim on a real stored page, and leaves every
judgement (is this sentence about THIS drug, at THAT target, and is it a claim rather
than a denial?) to the model that reads the worklist and to the applier's gates. A
regex cannot tell "is an antagonist at D2" from "unlike the antagonists at D2" or from
a sentence about the drug's metabolite, so it does not try.

Nothing here is duplicated: the stored-page lookup is ``lib.corpora.wikipedia.page_for``
(which owns the ``PAGE_ALIASES`` redirect map and the slug rule), the prose-sentence
extraction is ``fetch_metabolite_bindings.action_lines``, and the "does this sentence
name this target" test is ``tools/target_aliases.py``, shared with the applier so the
gate can never accept what the worklist could not have offered.

The contract for the LLM pass
-----------------------------
Read ``tools/generated_cache/binding_directions_worklist.json``: a list of records
``{drug, name, slug, targets: [{target, name, aliases}], candidates: [{line, qid}, ...]}``.
Write ``tools/generated_cache/binding_directions_judged.json``::

    {"<drug id>": [{"target": "<target id>", "action": "<action key>", "index": <int>,
                    "qid": "<the candidate's qid>", "note": "<optional>"}, ...], ...}

* ``index`` is the position of the sentence in that drug's ``candidates`` list, and
  ``qid`` echoes that candidate's fingerprint (``pipeline.judged``: a rebuilt worklist
  that shifted the list makes the applier refuse the pick). Answer with an index,
  **never** a rewritten or trimmed quote string: the applier resolves the quote itself,
  so a paraphrase is not expressible and cannot reach the dataset.
* ``target`` must be one of that record's ``targets`` (those are the drug's
  affinity-only bindings, the only ones this pass may fill in).
* ``action`` is one of the ``DRUG_ACTIONS`` keys: ``agonist``, ``antagonist``,
  ``blocker``, ``enzyme_inhibitor``, ``inverse_agonist``, ``modulator``, ``nam``,
  ``pam``, ``partial_agonist``, ``precursor``, ``releaser``, ``reuptake_inhibitor``,
  ``synthesis_inhibitor``, ``vesicular_inhibitor``, ``vesicular_releaser``. The applier
  gates against the live vocabulary in ``data_generators/drugs.py``, so a key this list
  has drifted from is rejected rather than written.
* Answer **only** when the sentence itself states that direction, for that target, for
  this drug. Not a class-wide sentence about other drugs ("most antipsychotics block
  D2"), not a negation or a denial, not a claim about a metabolite or a co-prescribed
  drug, not an inference from the drug's class. Anything doubtful is skipped: a skipped
  binding stays honestly unsourced, a wrong one is a false ``verified``.
* One row per target at most. A target the article never discusses simply gets no row.

Then ``tools/sourcing/apply_binding_directions.py`` re-gates each pick and merges it.

Usage (from the repo root; fully offline, every article is already stored)::

    uv run tools/fetch/fetch_binding_directions.py
    uv run tools/fetch/fetch_binding_directions.py --only clozapine,olanzapine

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)                              # sibling fetch_* modules
sys.path.insert(0, os.path.join(REPO, "tools"))       # drugs_io, target_aliases

from lib.page_file import page_path, read_page_file  # noqa: E402 (refuses a path-like page)
from lib import drugs_io  # noqa: E402
from lib import worklist_io  # noqa: E402
from lib import target_aliases as ta  # noqa: E402  (the shared "quote names the target" test)
from lib.corpora import wikipedia as wikistore  # noqa: E402  (stored-page lookup + PAGE_ALIASES)
# Imported for `action_lines` only. It pulls in BeautifulSoup at import time, which is
# why this script declares the beautifulsoup4 dependency above; no HTML is parsed here.
import fetch_metabolite_bindings as mb  # noqa: E402

WORKLIST = os.path.join(REPO, "tools", "generated_cache",
                        "binding_directions_worklist.json")

# Candidate sentences offered per drug. A cap exists so one verbose article cannot
# dominate the worklist; generous, because the lines are already filtered down to those
# naming one of this drug's affinity-only targets, and a dropped line is a claim that
# can never be sourced.
MAX_CANDIDATES = 40


def affinity_only_targets(drug: dict) -> list[str]:
    """The target ids of this drug's ``affinity_only`` bindings, sorted and deduplicated."""
    return sorted({b["target"] for b in drug.get("bindings", [])
                   if b.get("affinity_only") and b.get("target")})


def candidates_for(page_text: str, aliases: dict[str, list[str]]) -> list[str]:
    """Prose lines from a stored article that name at least one of the wanted targets.

    Parameters
    ----------
    page_text : str
        The stored ``pages/<slug>.md`` text (what the quote gate later checks against,
        so a line returned here is verbatim-citable as it stands).
    aliases : dict
        ``{target id: aliases}``, restricted to this drug's affinity-only targets.

    Returns
    -------
    list of str
        Verbatim lines, in page order, capped at :data:`MAX_CANDIDATES`.
    """
    # limit=None: the whole article is scanned, then filtered by target. Taking
    # `action_lines`' own default cap first would let the first fourteen action verbs
    # (often a lead paragraph about indications) decide which bindings are sourceable.
    # max_commas=None for the same reason: a drug article states its binding profile in
    # one long clause-heavy sentence ("antagonism at histaminergic H1, muscarinic M3 and
    # dopamine D2 receptors have been associated with..."), which the navbox-enumeration
    # cap reads as a list. Measured: the cap alone cost two thirds of the candidates.
    lines = mb.action_lines(page_text, limit=None, max_commas=None)
    patterns = [rx for rx in (ta.alias_regex(a) for a in aliases.values()) if rx]
    out = []
    for line in lines:
        folded = ta.fold(line)
        if any(rx.search(folded) for rx in patterns):
            out.append(line)
            if len(out) >= MAX_CANDIDATES:
                break
    return out


def build(drugs: list[dict], only: set[str] | None = None) -> tuple[list[dict], list[str]]:
    """Build the worklist records plus the warnings for drugs that could not be read.

    Parameters
    ----------
    drugs : list of dict
        The authored drug records (``drugs_io.load_drugs()``).
    only : set of str, optional
        Drug ids to limit to; None means every drug.

    Returns
    -------
    tuple
        ``(records, warnings)``, records sorted by drug id.
    """
    all_aliases = ta.aliases_by_target()
    names = ta.target_names()
    records, warnings = [], []
    for drug in sorted(drugs, key=lambda d: d["id"]):
        if only is not None and drug["id"] not in only:
            continue
        targets = affinity_only_targets(drug)
        if not targets:
            continue
        unknown = [t for t in targets if t not in all_aliases]
        if unknown:
            # A binding on a target the generator does not model would fail validation
            # long before here, so this is a corruption report, not a routine skip.
            warnings.append(f"{drug['id']}: unmodeled target(s) {unknown} - not offered")
            targets = [t for t in targets if t in all_aliases]
        path = wikistore.page_for(drug)
        if not path:
            warnings.append(f"{drug['id']}: no stored Wikipedia article "
                            f"(uv run tools/fetch/fetch_wikipedia_pharmacology.py "
                            f"--drug {drug['id']}) - skipped")
            continue
        page_text = read_page_file(path)
        aliases = {t: all_aliases[t] for t in targets}
        records.append({
            "drug": drug["id"],
            "name": drug.get("name") or drug["id"],
            "slug": os.path.splitext(os.path.basename(path))[0],
            "targets": [{"target": t, "name": names[t], "aliases": aliases[t]}
                        for t in targets],
            "candidates": [{"line": c} for c in candidates_for(page_text, aliases)],
        })
    return records, warnings


# ---------------------------------------------------------------------------
# --search: the UNKNOWN search (tools/data_generators/unknown.py). One record per
# binding with no direction, over every corpus UNKNOWN_REQUIRED_SOURCES lists: the two
# assay tables are looked up by code (PDSP records no direction at all; a GtoPdb or a
# Wikipedia-table direction would already have been applied, so one found here is
# reported, never offered), the three prose corpora offer candidate sentences with no
# verdict. Each record also carries its search log rows, which become the UNKNOWN
# entry when nothing is accepted.
# ---------------------------------------------------------------------------
SEARCH_WORKLIST = os.path.join(REPO, "tools", "generated_cache",
                               "binding_directions_search_worklist.json")
FR_PAGES = os.path.join(REPO, "data_sources", "wikipedia", "pages_fr")
EN_PAGES = os.path.join(REPO, "data_sources", "wikipedia", "pages")
# A direction word, narrower than `mb.ACTION_RE` (which also takes "affinity", "binds"):
# a sentence that only says the ligand binds cannot state a direction.
DIRECTION_RE = re.compile(
    r"(agonis|antagonis|inhibit|block|modulat|releas|activat|stimulat|reuptake|"
    r"uptake|potentiat|allosteric)", re.I)
FR_DIRECTION_RE = re.compile(
    r"(agonis|antagonis|inhib|bloqu|modulat|lib[ée]r|activ|stimul|recapture|"
    r"potentialis|allost[ée]rique)", re.I)
MAX_SEARCH_CANDIDATES = 12   # per binding, across all three prose corpora


def _lines(path: str) -> list[str]:
    """A stored page's non-empty, non-heading lines (headers end at the first blank)."""
    text = read_page_file(path)
    if text is None:
        return []
    return [ln.strip() for ln in text.split("\n\n", 1)[-1].splitlines()
            if ln.strip() and not ln.startswith(("#", "<!--"))]


_fold = functools.lru_cache(maxsize=None)(ta.fold)   # one page line is tested per target


def _offered(lines, aliases, direction_re, must_mention=None) -> list[str]:
    """The lines naming the target AND a direction word (and ``must_mention``, a
    metabolite's name, when the page is its parent's), deduplicated in page order."""
    rx = ta.alias_regex(aliases)
    out = []
    for line in lines:
        if not rx or " | " in line or not rx.search(_fold(line)):
            continue
        if not direction_re.search(line):
            continue
        if must_mention and mb._norm(must_mention) not in mb._norm(line):
            continue
        if line not in out:
            out.append(line)
    return out


def build_search(drugs: list[dict], metabolites: list[dict] = ()) -> list[dict]:
    """The search worklist: one record per direction-less binding (see above)."""
    sys.path.insert(0, os.path.join(REPO, "tools", "fetch"))
    import fetch_category_worklist as catwl          # FR slug resolver
    import fetch_europepmc as epmc                    # the search ledger + pages
    import fetch_gtopdb_ki as gk                      # the GtoPdb join
    import fetch_ki                                   # the PDSP join
    from data_generators import unknown

    aliases, names = ta.aliases_by_target(), ta.target_names()
    with open(os.path.join(REPO, "tools", "generated_cache", "brand_worklist.json"),
              encoding="utf-8") as f:
        brand = json.load(f)
    with open(WORKLIST, encoding="utf-8") as f:       # what the prose pass already showed
        shown = {r["drug"]: {c["line"] for c in r["candidates"]} for r in json.load(f)}
    with open(os.path.join(REPO, "tools", "generated_cache",
                           "binding_directions_tables.json"), encoding="utf-8") as f:
        tables = json.load(f)
    with open(mb.WORKLIST, encoding="utf-8") as f:
        metab_pages = {unknown.fold(r["metabolite"]): r.get("pages") or []
                       for r in json.load(f)}
    ledger = json.loads(epmc.SEARCH_LEDGER.read_text("utf-8"))
    by_ligand = gk.index_by_ligand(gk.read_rows())
    gene_owner = gk.owner_genes(set(aliases))
    by_drug = {d["id"]: d for d in drugs}

    records, pdsp_cache = [], {}
    for row in unknown.affinity_only_bindings(drugs, metabolites):
        drug, target, ligand, metab = by_drug[row["drug"]], row["target"], row["ligand"], \
            row["metabolite"]
        al = aliases.get(target, [])
        log, cands, elsewhere = [], [], []
        # PDSP (#5): a binding-assay table, no direction field.
        pdsp_key = (ligand, None if metab else drug["id"])
        if pdsp_key not in pdsp_cache:       # one CSV scan per ligand, not per binding
            pdsp_cache[pdsp_key] = fetch_ki.resolve_rows(*pdsp_key)[0]
        pdsp_rows = pdsp_cache[pdsp_key]
        summ = fetch_ki.summarize_target(pdsp_rows, target)
        log.append({"corpus": "pdsp_ki", "lookup": f"{ligand} x {target} (ligand rows "
                    f"joined to the target's gene)", "hits": (summ or {}).get("matched_rows", 0),
                    "note": "binding Ki rows only; PDSP records no direction"})
        # GtoPdb (#11): the curated Action/Type columns.
        g_rows = [r for r in gk.ligand_rows(by_ligand, ligand, drug["id"])
                  if target in gene_owner.get((r.get("Target Gene Symbol") or "").upper(), ())]
        acts = sorted({a for r in g_rows if (a := gk.action_for(r, target))})
        log.append({"corpus": "gtopdb_ki", "lookup": f"{ligand} x {target} in "
                    f"interactions.csv", "hits": len(g_rows),
                    "note": f"action column: {', '.join(acts) or 'none'}"})
        if acts:
            elsewhere.append(f"gtopdb_ki says {', '.join(acts)}")
        # Wikipedia EN (#9): the Ki table's Action column, then the prose.
        t_acts = sorted({r["action"] for r in (tables.get(drug["id"]) or {}).get("rows", [])
                         if r.get("target") == target and r.get("action")} if not metab else set())
        if t_acts:
            elsewhere.append(f"wikipedia_pharm table says {', '.join(t_acts)}")
        if metab:
            en_pages = [page_path(EN_PAGES, p) for p in metab_pages.get(
                unknown.fold(metab), [])]
        else:
            en = wikistore.page_for(drug)
            en_pages = [en] if en else []
        en_hits = 0
        for path in en_pages:
            slug = os.path.splitext(os.path.basename(path))[0]
            lines = _offered(_lines(path), al, DIRECTION_RE,
                             must_mention=metab if metab and fold_slug(slug) != unknown.fold(
                                 metab) else None)
            en_hits += len(lines)
            for line in lines:
                if line not in shown.get(drug["id"], ()) or metab:
                    cands.append({"corpus": "wikipedia_pharm", "page": slug, "line": line})
        log.append({"corpus": "wikipedia_pharm", "lookup": "article(s) "
                    f"{', '.join(os.path.splitext(os.path.basename(p))[0] for p in en_pages) or 'none stored'}"
                    ": Ki-table Action column + prose sentences naming the target with a "
                    "direction word", "hits": en_hits + len(t_acts)})
        # Wikipedia FR (#10): the prose.
        fr = catwl._fr_slug(drug, brand)
        fr_lines = _offered(_lines(page_path(FR_PAGES, fr)) if fr else [], al,
                            FR_DIRECTION_RE, must_mention=metab)
        cands += [{"corpus": "wikipedia_fr", "page": fr, "line": ln} for ln in fr_lines]
        log.append({"corpus": "wikipedia_fr", "lookup": f"article {fr or 'none found'}: "
                    "sentences naming the target with a direction word", "hits": len(fr_lines)})
        # Europe PMC (#17): the abstracts the query returned.
        hit = ledger.get(row["site"])
        if hit:
            for pmid in hit["read"]:
                # An abstract is about many compounds, so its sentence must name this
                # one (unlike a sentence of the drug's own article).
                for ln in _offered(_lines(page_path(epmc.PAGES_DIR, pmid)),
                                   al, DIRECTION_RE, must_mention=ligand):
                    cands.append({"corpus": "europepmc", "page": pmid, "line": ln})
            log.append({"corpus": "europepmc", "query": hit["query"], "hits": hit["hits"],
                        "read": hit["read"], "searched": hit["searched"]})
        records.append({
            "site": row["site"], "drug": drug["id"], "ligand": ligand, "metabolite": metab,
            "target": target, "target_name": names.get(target, target), "aliases": al,
            "elsewhere": elsewhere, "searched": log,
            "candidates": cands[:MAX_SEARCH_CANDIDATES]})
    return records


fold_slug = drugs_io.ascii_key  # a page slug folded like a metabolite name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="",
                    help="comma-separated drug ids to limit the worklist to")
    ap.add_argument("--search", action="store_true",
                    help="build the UNKNOWN search worklist over every corpus instead")
    args = ap.parse_args()
    if args.search:
        records = build_search(drugs_io.load_drugs(), drugs_io.load_metabolites())
        worklist_io.write(SEARCH_WORKLIST, records)
        n_c = sum(1 for r in records if r["candidates"])
        print(f"wrote {os.path.relpath(SEARCH_WORKLIST, REPO)}: {len(records)} binding(s), "
              f"{n_c} with candidates ({sum(len(r['candidates']) for r in records)} "
              f"sentence(s)), {sum(1 for r in records if r['elsewhere'])} with a direction "
              f"found elsewhere")
        return 0

    only = {d.strip() for d in args.only.split(",") if d.strip()} or None
    drugs = drugs_io.load_drugs()
    records, warnings = build(drugs, only)

    for line in warnings:
        print(f"  warn: {line}")

    # A binding is "reachable" when at least one offered sentence names its target; the
    # rest can never be sourced from this corpus, which is the honest expectation here
    # (an article states a handful of directions, not a whole assay panel). Counted over
    # every scoped drug, so a drug skipped for a missing article still shows in the total.
    scoped = [d for d in drugs if only is None or d["id"] in only]
    n_drugs = sum(1 for d in scoped if affinity_only_targets(d))
    n_bindings = sum(1 for d in scoped for b in d.get("bindings", [])
                     if b.get("affinity_only"))
    n_reachable = 0
    for rec in records:
        folded = [ta.fold(c["line"]) for c in rec["candidates"]]
        reachable = {t["target"] for t in rec["targets"]
                     if (rx := ta.alias_regex(t["aliases"]))
                     and any(rx.search(f) for f in folded)}
        n_reachable += sum(1 for b in next(d for d in scoped if d["id"] == rec["drug"])
                           .get("bindings", [])
                           if b.get("affinity_only") and b["target"] in reachable)

    worklist_io.write(WORKLIST, records, indent=2)
    n_cand = sum(len(r["candidates"]) for r in records)
    print(f"\nwrote {os.path.relpath(WORKLIST, REPO)}")
    print(f"  {n_drugs} drug(s) with an affinity-only binding, "
          f"{len(records)} of them with a stored article")
    print(f"  {n_bindings} affinity-only binding(s), {n_reachable} with >= 1 candidate "
          f"sentence naming their target")
    print(f"  {n_cand} candidate sentence(s) offered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
