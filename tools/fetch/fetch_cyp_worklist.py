#!/usr/bin/env python
"""Build the cytochrome-P450 worklist: candidate sentences for an LLM to judge.

The fetch / candidate-extraction half of the LLM-extract + quote-gate + judge pipeline
for the ``drug_enzymes`` node kind, mirroring ``fetch_pharmacokinetics.py`` and
``fetch_brand_names.py``.

Why this exists
---------------
The two older passes (``fetch_cyp.py`` over Stahl, ``fetch_cyp_wikipedia.py`` over
Wikipedia) decide the role themselves, from regular expressions. For Stahl that is
defensible: its ``Pharmacokinetics`` block is a telegraphic bullet list whose shape is
nearly a grammar ("Substrate for CYP2D6", "Inhibits CYP2C19"). For **Wikipedia prose it
is not**, and the machinery that accumulated there (a negation veto, two victim-frame
vetoes, a head-only subject test, a coordination rule, a positional two-role split) is
that mismatch made visible. A regex cannot see that "inhibitors" is a plural noun here
and a verb's object there, nor that the "it" opening a follow-up sentence is the drug
the paragraph is about.

So this script decides **nothing**. It asks one deterministic question of every line,
"does it name an isoform the dataset models", and hands what survives to a judge.

The candidate is the quote
--------------------------
Every candidate is confirmed **verbatim on its own page here**, under
``check_data.normalize_for_match`` (the same normalizer the gate uses), and is offered
to the judge under a stable index ``n``. The judge answers with that index, never with a
string, so it cannot paraphrase a quote into existence: the worst it can do is pick the
wrong true sentence. ``apply_cyp_sources.py`` re-gates anyway (a judge that edits a
string must fail loudly, not silently).

Each candidate carries the nearest preceding heading, because the same sentence means
different things in different sections and the judge is given no other context (see
CLAUDE.md, "Where a quote sits").

Both corpora, one worklist, because they ask the judge the same question:

* **Stahl** (corpus #1): the drug's ``Pharmacokinetics`` answer from the structured
  dump, split into bullets, each resolved to the page file that holds it verbatim.
* **Wikipedia** (corpus #9): the stored English article, its drugbox ``Metabolism |``
  row plus every sentence of prose naming a modeled isoform. Reference-list lines are
  skipped: a cited paper's title states a role the article is not asserting here.

Output: ``tools/generated_cache/cyp_worklist.json``, committed beside the judged file it
feeds (like ``pk_worklist.json`` and ``brand_worklist.json``) so a reviewer can see what
the judge was shown, not only what it answered. Rebuilding it needs the author-side
corpora; applying the judged file does not.

Usage (from the repo root):
    python tools/fetch/fetch_cyp_worklist.py
    python tools/fetch/fetch_cyp_worklist.py --only fluoxetine,modafinil
    python tools/fetch/fetch_cyp_worklist.py --out PATH

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, HERE)

import check_data  # noqa: E402  (reuse the quote gate's normalizer, one definition)
import drugs_io  # noqa: E402
from fetch_cyp import (  # noqa: E402  (one definition of each shared rule)
    ENZYME_RE,
    gate,
    load_index,
    load_pk_blocks,
    strip_html,
)
from fetch_cyp_wikipedia import (  # noqa: E402
    INFOBOX_RE,
    KNOWN_ENZYMES,
    REFERENCE_RE,
    SENTENCE_SPLIT,
    page_for,
)

OUT = os.path.join(REPO, "tools", "generated_cache", "cyp_worklist.json")

# The vocabularies the judge must answer in, copied into the worklist so the prompt and
# the applier cannot drift apart. Mirrors ENZYME_ROLES / ENZYME_STRENGTHS in
# data_generators/drugs.py (not imported: this script is stdlib-only and runs
# author-side, like every other fetcher).
ROLES = {
    "substrate": "this enzyme metabolises the drug (the drug is cleared by it)",
    "inhibitor": "the drug reduces this enzyme's activity",
    "inducer": "the drug increases this enzyme's activity",
}
STRENGTHS = {
    "substrate": ["major", "minor"],
    "inhibitor": ["strong", "moderate", "weak"],
    "inducer": ["strong", "moderate", "weak"],
}

# A stored Wikipedia page keeps its headings as Markdown ATX lines; a Stahl page does
# not, so its trail is the dump question the bullet came from.
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$")


def _gated(quote: str, page_text_normalized: str) -> bool:
    """Is this candidate verbatim on its page, by the gate's own normalization?"""
    return check_data.normalize_for_match(quote) in page_text_normalized


def stahl_candidates(name: str, span: tuple[int, int], answer: str) -> list[dict]:
    """The drug's Pharmacokinetics bullets that name an isoform, each with its page.

    Resolved through ``fetch_cyp.gate``, which finds the page file inside the
    monograph's span holding the bullet verbatim and, failing that, retries it cut just
    past the last isoform. That retry is not cosmetic: the dump sometimes carries a
    running header into a bullet and a hyphen rejoins differently across a page break,
    so four real claims (fluoxetine's CYP3A4 inhibition among them) are only offerable
    in the shortened form. A bullet no page holds either way is dropped rather than
    offered, because a quote the gate will reject is not a candidate.
    """
    out, seen = [], set()
    for raw in re.split(r"<br\s*/?>|\u2022", answer):
        bullet = strip_html(raw)
        if not bullet or not ENZYME_RE.search(bullet) or bullet in seen:
            continue
        seen.add(bullet)
        gated = gate(bullet, *span)
        if gated is None:
            continue
        page, quote = gated
        out.append({"corpus": "stahl", "page": page, "quote": quote,
                    "heading": f"{name.title()} / Pharmacokinetics"})
    return out


def wikipedia_candidates(path: str, slug: str) -> list[dict]:
    """Every drugbox metabolism row and prose sentence naming an isoform.

    No veto of any kind. A negation ("without involvement of CYP2D6"), a victim frame
    ("medications that are metabolized by CYP3A4") and a sentence about another molecule
    are all offered, because telling them apart is what the judge is for and what the
    regexes got wrong.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    normalized = check_data.normalize_for_match(text)
    out, seen, heading = [], set(), ""
    for raw in text.splitlines():
        head = HEADING_RE.match(raw)
        if head:
            heading = head.group(2)
            continue
        line = raw.strip()
        if not line or not ENZYME_RE.search(line) or REFERENCE_RE.search(line):
            continue
        pieces = [line] if INFOBOX_RE.match(line) else SENTENCE_SPLIT.split(line)
        for piece in pieces:
            piece = piece.strip()
            if not piece or not ENZYME_RE.search(piece) or piece in seen:
                continue
            seen.add(piece)
            if not _gated(piece, normalized):
                continue           # a sentence split mid-quote: not offerable verbatim
            out.append({"corpus": "wikipedia_pharm", "page": slug, "quote": piece,
                        "heading": heading or "(lead)"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT, help="worklist output path")
    ap.add_argument("--only", help="comma-separated drug ids, for a cheap slice")
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",")} if args.only else None
    try:
        index, blocks = load_index(), load_pk_blocks()
    except OSError:
        print("missing the author-side Stahl tree; see CLAUDE.local.md", file=sys.stderr)
        return 1

    worklist: dict[str, dict] = {}
    stats: collections.Counter = collections.Counter()
    for drug in drugs_io.load_drugs():
        if only and drug["id"] not in only:
            continue
        name = (drug.get("name") or "").strip().lower()
        cands: list[dict] = []
        answer, span = blocks.get(name), index.get(name)
        if answer and span:
            cands += stahl_candidates(name, span, answer)
        else:
            stats["drug: not on Stahl's roster"] += 1
        path = page_for(drug)
        if path:
            cands += wikipedia_candidates(path, os.path.splitext(os.path.basename(path))[0])
        else:
            stats["drug: no stored Wikipedia article"] += 1
        if not cands:
            stats["drug: no candidate names a modeled isoform"] += 1
            continue
        for n, c in enumerate(cands):
            c["n"] = n
        worklist[drug["id"]] = {"name": drug.get("name"), "candidates": cands}
        stats["drug: queued"] += 1
        stats["candidates"] += len(cands)

    payload = {
        "vocabulary": {"roles": ROLES, "strengths": STRENGTHS,
                       "enzymes": sorted(KNOWN_ENZYMES)},
        "drugs": worklist,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"{stats['drug: queued']} drugs, {stats['candidates']} candidate sentences")
    for key, n in sorted(stats.items()):
        if key != "candidates":
            print(f"  {key:<44} {n}")
    print(f"\nwrote {os.path.relpath(args.out, REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
