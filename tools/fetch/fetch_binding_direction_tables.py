#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "beautifulsoup4>=4.12",
# ]
# ///
"""Read the direction an ``affinity_only`` binding has out of a Wikipedia Ki table.

The prose pass (``tools/fetch/fetch_binding_directions.py``) can only reach a binding the
article *discusses*, and an article discusses a handful of a drug's targets, not its whole
assay panel. The binding table it carries, however, often has an ``Action`` column beside
the Ki one (``5-HT 2C | 6.4 | Inverse agonist``), and that cell is the direction stated as
plainly as a cell can state it. Reading a cell is not choosing a sentence: there is no
wrong-true-sentence failure mode, so this is a **code extraction** (``extraction: "code"``,
the pipeline ``page_code``) that needs no LLM and no judge, exactly like the Ki value the
same row already sources (``fetch_wikipedia_pharmacology.py``).

Nothing here is duplicated: the table grid, the header detection, the target-name resolver
and the row text (the one string both the stored page and every quote from it are made of)
are ``fetch_wikipedia_pharmacology``'s, imported; the stored-page lookup is
``fetch_cyp_wikipedia.page_for``; the write and its gates are
``tools/sourcing/apply_binding_directions.py --tables``, the sole writer of a direction.

What it offers, per drug, into ``tools/generated_cache/binding_directions_tables.json``::

    {"olanzapine": {"slug": "olanzapine",
                    "rows": [{"target": "5ht2b", "wiki_name": "5-HT 2B", "cell": "Inverse agonist",
                              "action": "inverse_agonist",
                              "quote": "5-HT 2B | 12 | Inverse agonist"}]}}

Only a row whose Action cell maps **exactly** onto the dataset's action vocabulary
(``ACTION_CELLS``, after footnote stripping) is offered. Everything else is reported and
left alone on purpose: ``ND`` / ``?`` (the table says it does not know), an arrow or a glyph
(defined by a legend this parser never reads), a percentage or a number (an efficacy, not a
direction), and a slash reading (``partial agonist / functional antagonist``, two claims the
vocabulary cannot hold). ``Inhibitor`` / ``Blocker`` are read by the target's type (a
transporter is reuptake-inhibited, an enzyme enzyme-inhibited, a channel blocked) and skipped
on a receptor, where the cell is ambiguous. Two rows on one target that disagree are skipped
too (a D4.2 / D4.4 / D4.7 triple that agrees is one proposal).

Confirm-only, like every other applier feeding this store: a target is proposed only when the
drug currently binds it ``affinity_only``, so a direction Stahl, GtoPdb or the author states
is never touched. Run from the repo root::

    uv run tools/fetch/fetch_binding_direction_tables.py            # -> the proposals file
    uv run --with beautifulsoup4 python tools/sourcing/apply_binding_directions.py --tables --dry-run
    uv run --with beautifulsoup4 python tools/sourcing/apply_binding_directions.py --tables

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, HERE)

import drugs_io  # noqa: E402
import fetch_cyp_wikipedia as cypwiki  # noqa: E402 (owns PAGE_ALIASES + the slug rule)
import fetch_wikipedia_pharmacology as wiki  # noqa: E402 (grid, headers, resolver, row text)

OUT = os.path.join(REPO, "tools", "generated_cache", "binding_directions_tables.json")

# The Action column: a header that says so, and is not one of the numeric neighbours a
# pharmacodynamics table also carries (an efficacy / intrinsic-activity column is a
# percentage, not a direction; the same word "action" never labels those, but "IA" and
# "E max" columns do sit next to one, so the exclusion is explicit).
ACTION_HEAD_RE = re.compile(r"\baction\b")
NOT_ACTION_RE = re.compile(r"efficacy|intrinsic|\bia\b|e\s*max|potency")

# A cell -> a live DRUG_ACTIONS key. Exact match after footnotes + case folding; a cell
# absent here is reported, never guessed. "inhibitor" / "blocker" resolve by target type
# (see :func:`typed_action`) since the same word means three different nodes.
ACTION_CELLS = {
    "antagonist": "antagonist",
    "antagonism": "antagonist",
    "silent antagonist": "antagonist",
    "neutral antagonist": "antagonist",
    "irreversible silent antagonist": "antagonist",
    "agonist": "agonist",
    "full agonist": "agonist",
    "near-full agonist": "agonist",
    "full/super agonist": "agonist",
    "partial agonist": "partial_agonist",
    "agonist (partial)": "partial_agonist",
    "(partial) agonist": "partial_agonist",
    "inverse agonist": "inverse_agonist",
    "reuptake inhibitor": "reuptake_inhibitor",
    "positive allosteric modulator": "pam",
    "negative allosteric modulator": "nam",
    "modulator": "modulator",
}
TYPED_CELLS = {"inhibitor", "blocker"}
TYPED_ACTION = {"transporter": "reuptake_inhibitor", "enzyme": "enzyme_inhibitor",
                "ion_channel": "blocker"}


def fold_cell(cell: str) -> str:
    """A table cell as the vocabulary sees it: footnotes gone, one space, lower case."""
    return wiki.clean_cell(cell).lower().strip()


def typed_action(cell: str, target_type: str | None) -> str | None:
    """The action key a cell states, or None when it states none the vocabulary holds."""
    key = fold_cell(cell)
    if key in ACTION_CELLS:
        return ACTION_CELLS[key]
    if key in TYPED_CELLS:
        return TYPED_ACTION.get(target_type or "")
    return None


def table_rows(table, valid_ids: set[str]) -> list[dict]:
    """Every (target, cell, quote) of one table that has both a Ki and an Action column."""
    grid = wiki.grid_expand(table)
    if len(grid) < 2:
        return []
    n_head, labels = wiki._header_split(grid)
    ki_col = next((i for i, lab in enumerate(labels)
                   if wiki.KI_HEAD_RE.search(lab) and not wiki.NOT_KI_RE.search(lab)), None)
    if ki_col is None:
        return []
    act_col = next((i for i, lab in enumerate(labels)
                    if i != ki_col and ACTION_HEAD_RE.search(lab)
                    and not NOT_ACTION_RE.search(lab)), None)
    if act_col is None:
        return []
    tgt_col = next((i for i, lab in enumerate(labels) if wiki.TARGET_HEAD_RE.search(lab)), 0)
    trs = table.find_all("tr")
    rows = []
    for r in range(n_head, len(grid)):
        row = grid[r]
        if len(row) <= max(ki_col, tgt_col, act_col) or r >= len(trs):
            continue
        name = row[tgt_col]["text"]
        # The same footer / range guards as the Ki extractor: a spanned note fills every
        # column with one sentence, and a "D 1 - D 5" row names no single target.
        if not name or name == row[ki_col]["text"] or len(name) > 45:
            continue
        if wiki.RANGE_RE.match(wiki.greek_to_latin(name)):
            continue
        tid = wiki.resolve_wiki_target(name, valid_ids)
        if tid is None:
            continue
        rows.append({"target": tid, "wiki_name": name, "cell": row[act_col]["text"],
                     "quote": wiki.row_text(trs[r])})
    return rows


def proposals_for(html: str, drug: dict, valid_ids: set[str], target_types: dict[str, str],
                  stats: collections.Counter) -> list[dict]:
    """The table-stated directions for one drug's affinity-only bindings, deduplicated."""
    affinity_only = {b["target"] for b in drug.get("bindings", []) if b.get("affinity_only")}
    if not affinity_only:
        return []
    soup = BeautifulSoup(html, "html.parser")
    by_target: dict[str, list[dict]] = collections.defaultdict(list)
    for table in soup.find_all("table"):
        for row in table_rows(table, valid_ids):
            if row["target"] not in affinity_only:
                stats["row: not affinity-only, left alone"] += 1
                continue
            action = typed_action(row["cell"], target_types.get(row["target"]))
            if action is None:
                stats[f"cell unmapped: {fold_cell(row['cell']) or '(empty)'}"] += 1
                continue
            by_target[row["target"]].append({**row, "action": action})
    out = []
    for target, rows in by_target.items():
        actions = {r["action"] for r in rows}
        if len(actions) > 1:
            stats["target: rows disagree, skipped"] += 1
            continue
        out.append(rows[0])
    return out


def build(only: set[str] | None = None) -> tuple[dict[str, dict], collections.Counter]:
    valid_ids = wiki.load_valid_ids()
    with open(wiki.META_PATH, encoding="utf-8") as f:
        target_types = {k: v.get("type") for k, v in json.load(f)["drug_targets"].items()}
    stats: collections.Counter = collections.Counter()
    proposals: dict[str, dict] = {}
    for drug in drugs_io.load_drugs():
        if only and drug["id"] not in only:
            continue
        path = cypwiki.page_for(drug)
        if not path:
            continue
        slug = os.path.splitext(os.path.basename(path))[0]
        raw = os.path.join(wiki.RAW_DIR, f"{slug}.html")
        if not os.path.exists(raw):
            stats["drug: page stored without its raw html"] += 1
            continue
        with open(raw, encoding="utf-8") as f:
            rows = proposals_for(f.read(), drug, valid_ids, target_types, stats)
        if rows:
            proposals[drug["id"]] = {"slug": slug, "rows": rows}
            stats["proposal"] += len(rows)
    return proposals, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated drug ids to scope the scan to")
    ap.add_argument("--out", default=OUT, help="proposals file to write")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None
    proposals, stats = build(only)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(proposals, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"{stats['proposal']} table-stated direction(s) over {len(proposals)} drug(s) "
          f"-> {os.path.relpath(args.out, REPO)}")
    for key, n in sorted(stats.items()):
        if key != "proposal":
            print(f"  {key:<48} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
