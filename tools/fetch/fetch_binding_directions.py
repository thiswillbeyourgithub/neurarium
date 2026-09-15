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

Nothing here is duplicated: the stored-page lookup is ``fetch_cyp_wikipedia.page_for``
(which owns the ``PAGE_ALIASES`` redirect map and the slug rule), the prose-sentence
extraction is ``fetch_metabolite_bindings.action_lines``, and the "does this sentence
name this target" test is ``tools/target_aliases.py``, shared with the applier so the
gate can never accept what the worklist could not have offered.

The contract for the LLM pass
-----------------------------
Read ``tools/generated_cache/binding_directions_worklist.json``: a list of records
``{drug, name, slug, targets: [{target, name, aliases}], candidates: [sentence, ...]}``.
Write ``tools/generated_cache/binding_directions_judged.json``::

    {"<drug id>": [{"target": "<target id>", "action": "<action key>",
                    "index": <int>, "note": "<optional, free text>"}, ...], ...}

* ``index`` is the position of the sentence in that drug's ``candidates`` list. Answer
  with an index, **never** a rewritten or trimmed quote string: the applier resolves the
  quote itself, so a paraphrase is not expressible and cannot reach the dataset.
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
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)                              # sibling fetch_* modules
sys.path.insert(0, os.path.join(REPO, "tools"))       # drugs_io, target_aliases

import drugs_io  # noqa: E402
import target_aliases as ta  # noqa: E402  (the shared "quote names the target" test)
import fetch_cyp_wikipedia as cypwiki  # noqa: E402  (stored-page lookup + PAGE_ALIASES)
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
        path = cypwiki.page_for(drug)
        if not path:
            warnings.append(f"{drug['id']}: no stored Wikipedia article "
                            f"(uv run tools/fetch/fetch_wikipedia_pharmacology.py "
                            f"--drug {drug['id']}) - skipped")
            continue
        with open(path, encoding="utf-8") as f:
            page_text = f.read()
        aliases = {t: all_aliases[t] for t in targets}
        records.append({
            "drug": drug["id"],
            "name": drug.get("name") or drug["id"],
            "slug": os.path.splitext(os.path.basename(path))[0],
            "targets": [{"target": t, "name": names[t], "aliases": aliases[t]}
                        for t in targets],
            "candidates": candidates_for(page_text, aliases),
        })
    return records, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="",
                    help="comma-separated drug ids to limit the worklist to")
    args = ap.parse_args()

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
        folded = [ta.fold(c) for c in rec["candidates"]]
        reachable = {t["target"] for t in rec["targets"]
                     if (rx := ta.alias_regex(t["aliases"]))
                     and any(rx.search(f) for f in folded)}
        n_reachable += sum(1 for b in next(d for d in scoped if d["id"] == rec["drug"])
                           .get("bindings", [])
                           if b.get("affinity_only") and b["target"] in reachable)

    os.makedirs(os.path.dirname(WORKLIST), exist_ok=True)
    with open(WORKLIST, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
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
