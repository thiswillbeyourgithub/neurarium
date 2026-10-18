#!/usr/bin/env python
"""Offer the RCP lines that may state a pre-prescription test: the workup worklist.

First step of the ``drug_workup`` pass (``data_generators/workup.py``): for every drug
with a corpus #24 page (``fetch_bdpm_rcp.py`` -> ``bdpm_rcp_labels.json`` +
``data_sources/bdpm/pages_rcp4/<page>.md``), every line of RCP sections 4.2 / 4.3 / 4.4
that names a test in ``workup.TESTS`` AND reads like an ask (a check / measure /
monitor verb, or a timing word, in the line or the sub-heading above it). Each
candidate carries the section and that sub-heading for context, plus the test ids its
text names (a hint, never a verdict: "insuffisance hepatique" names the liver and
asks for nothing).

Then one LLM pass answers by **index** with ``[{index, test, timing}]`` per drug into
``tools/generated_cache/workup_judged.json``, and ``tools/sourcing/apply_workup.py``
gates and writes. :func:`build` is what the applier re-derives, so a judged index
always resolves against a freshly built list.

Usage (repo root)::

    python tools/fetch/fetch_workup.py    # -> tools/generated_cache/workup_worklist.json

Stdlib only, offline, author-side (reads ``data_sources/``). Built with the help of
Claude Code.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT / "tools"))
from data_generators import workup as W  # noqa: E402
from lib import worklist_io  # noqa: E402
from data_generators.provenance import corpus_page_path  # noqa: E402

CORPUS = "bdpm_rcp"
LABELS = ROOT / "tools" / "generated_cache" / "bdpm_rcp_labels.json"
WORKLIST = ROOT / "tools" / "generated_cache" / "workup_worklist.json"

# An ask: the label tells the prescriber to check, measure or monitor something.
ASK_RE = re.compile(
    r"surveill|contr[ôo]l|dosage|doser|mesur|bilan|examen|v[ée]rifi|recherch|"
    r"\btest|r[ée]alis|effectu|pratiqu|[ée]valu|d[ée]termin|suivi|recommand|"
    r"n[ée]cessaire|doit|doivent|devra|devront|il convient|s.assurer", re.IGNORECASE)

# An excipient notice ("contient moins de 1 mmol de sodium", "contient du lactose")
# names no test.
EXCIPIENT_RE = re.compile(r"excipient|mmol \(?\d|contient moins de|lactose|galactose|"
                          r"saccharose|fructose", re.IGNORECASE)


def page_lines(text: str) -> list[dict]:
    """A stored page's body as ``[{line, section, under}]``: each text line with the
    ``## `` section and the nearest ``### `` sub-heading (within that section) above
    it. Header and heading lines themselves are not lines. A list item keeps its text
    without the ``- `` marker (the quote is the item's words, not the Markdown).

    >>> page_lines("# T\\ncis: 1\\n\\n## 4.4. Mises\\n### Avant :\\n- ECG.\\nTexte.")
    ... # doctest: +NORMALIZE_WHITESPACE
    [{'line': 'ECG.', 'section': '4.4', 'under': 'Avant :'},
     {'line': 'Texte.', 'section': '4.4', 'under': 'Avant :'}]
    """
    out, section, under = [], None, ""
    for raw in text.splitlines():
        if raw.startswith("## "):
            section, under = raw[3:].split(" ", 1)[0].rstrip("."), ""
            continue
        if raw.startswith("### "):
            under = raw[4:].strip()
            continue
        if section is None or not raw.strip():
            continue
        out.append({"line": raw[2:] if raw.startswith("- ") else raw,
                    "section": section, "under": under})
    return out


def offered(ln: dict) -> bool:
    """Whether a page line is offered: it names a test, and it or its sub-heading
    reads as an ask or carries a timing word."""
    if not W.tests_named(ln["line"]) or EXCIPIENT_RE.search(ln["line"]):
        return False
    ctx = f"{ln['line']} {ln['under']}"
    return bool(ASK_RE.search(ctx) or any(W.attests(W.TIMINGS, t, ctx) for t in W.TIMINGS))


def build(labels: dict | None = None) -> dict[str, dict]:
    """``{drug_id: {page, candidates: [{index, section, under, quote, tests}]}}``; ``page``
    is the CIS, or the EMA product number of an EPAR found by name."""
    if labels is None:
        labels = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    out = {}
    for did, entry in sorted(labels.items()):
        path = corpus_page_path(CORPUS, entry["page"])
        if not path or not path.exists():
            continue
        cands = []
        for ln in page_lines(path.read_text(encoding="utf-8")):
            if offered(ln):
                cands.append({"index": len(cands), "section": ln["section"],
                              "under": ln["under"], "quote": ln["line"],
                              "tests": W.tests_named(ln["line"])})
        if cands:
            out[did] = {"page": entry["page"], "denomination": entry.get("denomination"),
                        "candidates": cands}
    return out


def main() -> int:
    wl = build()
    worklist_io.write(WORKLIST, wl)
    n = sum(len(v["candidates"]) for v in wl.values())
    print(f"[ok] {n} candidate line(s) over {len(wl)} drug(s) -> "
          f"{WORKLIST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
