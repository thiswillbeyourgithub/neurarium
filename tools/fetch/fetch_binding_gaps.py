#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "beautifulsoup4>=4.12",
# ]
# ///
"""Build the worklist of MISSING drug -> target bindings a drug's Wikipedia article states.

Why this exists
---------------
Every other binding pass is confirm-only: the direction passes fill in an
``affinity_only`` binding, PDSP / GtoPdb annotate or add a measured one. None of them can
see a target no assay panel covers and no book monograph mentions, yet the drug's own
English Wikipedia article (corpus #9 ``wikipedia_pharm``, every roster article stored
author-side, see ``CLAUDE.local.md``) often says it ("tetrabenazine is a reversible VMAT2
inhibitor"). The drugbox's "Biomolecular targets" row would be the structured answer, but
almost no stored article carries one, so prose is what closes the class.

Three inputs per drug, both minus every target it already covers
(``binding_gaps.bound_targets``):

* **drugbox**: a ``Biomolecular targets`` / ``Inhibited transporters`` / ``Target`` cell
  of a flattened infobox row, offered as ``"<header> | <cell>"`` (a verbatim substring
  of the stored line);
* **prose**: the article's action-verb paragraphs (``fetch_metabolite_bindings.action_lines``,
  the same extractor the direction pass uses) cut into sentences
  (``lib.corpora.wikipedia.SENTENCE_SPLIT``), each carrying a direction word and naming a
  modeled target under the shared matcher ``tools/target_aliases.py``;
* **rcp**: the drug's French RCP section 5.1 (corpus #24 ``bdpm_rcp``, pages built by
  ``fetch_bdpm_rcp.py``), a lead line ending in ":" joined with its list items
  (:func:`rcp_units`), French class words read through ``binding_gaps.FR_ALIASES``. Each
  such candidate carries its own ``corpus`` + ``page`` (the CIS) for the applier to cite.

A candidate is one (sentence, target) pair. Pairs are **dropped** here when the clause
naming the target is negated or hedged (``binding_gaps.negated``) or the sentence is
about a stereo relative (``binding_gaps.stereo_mixed``): the applier re-runs both, so
dropping them only spares the judge. Nothing else is decided here: the worklist carries
**no verdict** (is it this drug, in humans, a claim rather than a comparison, which
direction?), exactly like ``fetch_binding_directions.py``.

LLM contract
------------
Write ``tools/generated_cache/binding_gaps_judged.json``::

    {"tetrabenazine": [{"index": 0, "pick": true, "action": "vesicular_inhibitor"},
                       {"index": 1, "pick": false, "reason": "class-wide"}]}

* One entry per candidate **index**, picked or rejected with a short reason, so the
  applier can tell an unjudged candidate from a rejected one.
* ``action`` is a ``DRUG_ACTIONS`` key the sentence itself states. A sentence stating
  only that the drug binds, with no direction, is rejected ("no direction"): a binding
  without an action needs a Ki to show anything (``check_data``), which prose lacks.
* Pick only a sentence asserting THIS drug acts on THAT target as a pharmacological
  fact; not a comparison ("unlike X"), a metabolite's action, a class-wide statement, a
  hypothesis, an animal-only finding, or a target merely listed as absent.

Usage (from the repo root; offline, every article already stored)::

    uv run tools/fetch/fetch_binding_gaps.py
    uv run tools/fetch/fetch_binding_gaps.py --only tetrabenazine,valbenazine

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))

from lib import binding_gaps as bg  # noqa: E402  (the predicates the applier re-runs)
from lib import drugs_io  # noqa: E402
from lib.page_file import read_page_file  # noqa: E402
import fetch_binding_directions as bd  # noqa: E402  (DIRECTION_RE: a stated direction)
from lib.corpora import wikipedia as wikistore  # noqa: E402  (stored-page lookup + sentence split)
import fetch_metabolite_bindings as mb  # noqa: E402  (prose action-line extractor)
from lib import target_aliases as ta  # noqa: E402
from lib import worklist_io  # noqa: E402
from lib.worklist_io import merge_scoped_list  # noqa: E402
from data_generators.provenance import corpus_page_path  # noqa: E402
import fetch_workup as wu  # noqa: E402 (the corpus #24 page reader)

WORKLIST = os.path.join(REPO, "tools", "generated_cache", "binding_gaps_worklist.json")

# drug id -> its corpus #24 RCP page entry (``fetch_bdpm_rcp.py``).
RCP_LABELS = (json.loads(open(wu.LABELS, encoding="utf-8").read())
              if os.path.exists(wu.LABELS) else {})

# The infobox headers whose next cell lists a drug's molecular targets.

DRUGBOX_HEADERS = ("Biomolecular targets", "Inhibited transporters", "Target")


def drugbox_cells(page_text: str) -> list[str]:
    """``"<header> | <cell>"`` for each drugbox target cell, verbatim, deduplicated."""
    out: list[str] = []
    for line in page_text.splitlines():
        cells = [c.strip() for c in line.split(" | ")]
        for i, cell in enumerate(cells[:-1]):
            if cell in DRUGBOX_HEADERS and cells[i + 1]:
                snippet = f"{cell} | {cells[i + 1]}"
                if snippet in line and snippet not in out:
                    out.append(snippet)
    return out


def prose_sentences(page_text: str) -> list[str]:
    """The article's direction-stating sentences, verbatim, deduplicated, in page order.

    ``action_lines`` yields whole paragraphs; each is cut with the CYP pass's sentence
    splitter so the quote is the one sentence making the claim, and a sentence must carry
    a direction word of its own (``fetch_binding_directions.DIRECTION_RE``): a picked row
    needs an action, so "binds with high affinity" alone is never worth offering.
    """
    out: list[str] = []
    for para in mb.action_lines(page_text, limit=None, max_commas=None):
        for sent in wikistore.SENTENCE_SPLIT.split(para):
            sent = sent.strip()
            if sent and bd.DIRECTION_RE.search(sent) and sent not in out:
                out.append(sent)
    return out


def candidates_for(drug: dict, page_text: str, aliases: dict[str, list[str]],
                   names: dict[str, str], siblings: list[str]) -> list[dict]:
    """The (line, target) pairs worth judging for one drug, in page order.

    Parameters
    ----------
    drug : dict
        The authored drug record.
    page_text : str
        Its stored ``pages/<slug>.md``.
    aliases, names : dict
        ``{target id: aliases}`` / ``{target id: display name}`` for every modeled target.
    siblings : list of str
        Its stereo relatives' names (``binding_gaps.stereo_siblings``).
    """
    out = []
    for origin, line in [("drugbox", ln) for ln in drugbox_cells(page_text)] + \
            [("prose", ln) for ln in prose_sentences(page_text)]:
        out += line_candidates(drug, origin, line, aliases, names, siblings, bg.WIKI_CORPUS)
    return out


def line_candidates(drug: dict, origin: str, line: str, aliases: dict[str, list[str]],
                    names: dict[str, str], siblings: list[str], corpus: str) -> list[dict]:
    """One candidate per target ``line`` claims that ``drug`` does not cover yet."""
    if bg.stereo_mixed(line, siblings):
        return []
    covered = bg.covered(drug, corpus)
    return [{"target": t, "target_name": names[t], "origin": origin, "line": line}
            for t in sorted(aliases) if t not in covered
            and bg.claims_target(line, t, aliases[t], corpus)]


def rcp_units(page_text: str) -> list[str]:
    """The RCP section 5.1 lines of a corpus #24 page, a lead line ending in ":" joined
    with the list items under it ("possède des propriétés : - antihistaminiques H1, -
    antidopaminergiques"), since an item alone does not say whose property it is.

    The joined unit still passes the quote gate: ``normalize_for_match`` drops the
    "- " markers and line breaks both texts differ by."""
    out: list[str] = []
    lead = None
    for ln in wu.page_lines(page_text):
        if ln["section"] != "5.1":
            continue
        line = ln["line"].strip()
        if lead is not None and ln["item"]:
            out[-1] += f" - {line}"
            continue
        lead = line if line.endswith(":") else None
        out.append(line)
    return out


def rcp_candidates(drug: dict, roster: list[dict], aliases, names) -> tuple[str | None, list[dict]]:
    """``(page, candidates)`` from the drug's French RCP section 5.1 (corpus #24),
    each candidate tagged with its corpus + page; ``(None, [])`` without a stored page."""
    entry = RCP_LABELS.get(drug["id"])
    text = entry and read_page_file(corpus_page_path(bg.RCP_CORPUS, entry["page"]))
    if not text:
        return None, []
    siblings = bg.stereo_siblings(drug, roster)
    cands = []
    for unit in rcp_units(text):
        for c in line_candidates(drug, "rcp_5.1", unit, aliases, names, siblings, bg.RCP_CORPUS):
            cands.append({**c, "corpus": bg.RCP_CORPUS, "page": entry["page"]})
    return entry["page"], cands


def build(drugs: list[dict], only: set[str] | None = None) -> tuple[list[dict], list[str]]:
    """``(records, warnings)``: one record per drug with at least one candidate."""
    aliases, names = ta.aliases_by_target(), ta.target_names()
    records, warnings = [], []
    for drug in sorted(drugs, key=lambda d: d["id"]):
        if (only is not None and drug["id"] not in only) or not bg.offerable(drug):
            continue
        path = wikistore.page_for(drug)
        cands = candidates_for(drug, read_page_file(path), aliases, names,
                               bg.stereo_siblings(drug, drugs)) if path else []
        # The RCP candidates go last, so a Wikipedia candidate keeps its judged index.
        _, rcp = rcp_candidates(drug, drugs, aliases, names)
        if not path and not rcp:
            warnings.append(f"{drug['id']}: no stored Wikipedia article nor RCP 5.1 - skipped")
        if cands or rcp:
            records.append({"drug": drug["id"], "name": drug.get("name") or drug["id"],
                            "slug": os.path.splitext(os.path.basename(path))[0] if path else None,
                            "stahl": bg.is_stahl(drug), "candidates": cands + rcp})
    return records, warnings


def scoped(existing: list[dict], records: list[dict], only: set[str] | None) -> list[dict]:
    """The worklist to write: ``records`` as is on a full build; on an ``--only`` build,
    ``records`` merged into ``existing`` (every other drug's entry kept, so its committed
    judged picks stay answerable), a scoped drug with no candidate left dropped."""
    if only is None:
        return records
    kept = [r for r in existing if r["drug"] not in only]
    return sorted(merge_scoped_list(kept, records, "drug"), key=lambda r: r["drug"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated drug ids to scope to")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} or None
    records, warnings = build(drugs_io.load_drugs(), only)
    for line in warnings:
        print(f"  warn: {line}")
    if only is not None and os.path.exists(WORKLIST):
        with open(WORKLIST, encoding="utf-8") as f:
            records = scoped(json.load(f), records, only)
    worklist_io.write(WORKLIST, records)
    n = sum(len(r["candidates"]) for r in records)
    print(f"wrote {os.path.relpath(WORKLIST, REPO)}: {n} candidate(s) over {len(records)} "
          f"drug(s), {sum(len(r['candidates']) for r in records if r['stahl'])} on Stahl drugs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
