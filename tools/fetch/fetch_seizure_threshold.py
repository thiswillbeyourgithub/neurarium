#!/usr/bin/env python
"""Offer the lines that may say a drug lowers / raises the seizure threshold (no verdict).

First of the four steps behind ``drug_seizure_threshold`` nodes
(``data_generators/seizure_threshold.py``): this fetcher writes
``tools/generated_cache/seizure_threshold_worklist.json``, one LLM pass answers per drug
``[{index, qid, effect}]`` into ``seizure_threshold_judged.json``,
``tools/sourcing/apply_seizure_threshold.py`` gates and writes, ``recheck_quotes.py``
judges.

Two inputs, each line offered only when it speaks of seizures
(``seizure_threshold.about_seizures``, the pattern the applier gates on):

* the drug's French RCP, sections 4.1-4.4 and 5.1 (corpus #24 ``bdpm_rcp``, the page
  ``fetch_workup`` reads: ``bdpm_rcp_labels.json`` -> ``pages_rcp4/<page>.md``), e.g.
  "Le méthylphénidate peut abaisser le seuil épileptogène chez les patients ...";
* the abstracts of :data:`SEIZURE_PAPERS` (corpus #17 ``europepmc``), each sentence
  offered to every roster drug it names by its INN, e.g. Pisani 2002's "maprotiline and
  clomipramine among antidepressants and chlorpromazine and clozapine among
  antipsychotics that have a relatively high seizurogenic potential" goes to all four.
  A name shared by several roster ids (a racemate and its enantiomer) is never matched:
  a paper naming "methylphenidate" does not say which form.

Usage (repo root), offline::

    python tools/fetch/fetch_seizure_threshold.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))
import fetch_workup  # noqa: E402 (the RCP page reader + labels)
import fetch_europepmc as epmc  # noqa: E402
from data_generators import seizure_threshold as S  # noqa: E402
from data_generators.provenance import corpus_page_path  # noqa: E402
from lib import drugs_io, worklist_io  # noqa: E402
from lib.quote_match import normalize_for_match  # noqa: E402 (the page gate's normalizer)

WORKLIST = ROOT / "tools" / "generated_cache" / "seizure_threshold_worklist.json"

# Europe PMC papers ranking drugs by seizure risk (each also in fetch_europepmc.PAPERS).
SEIZURE_PAPERS = ("17223086", "11888352")
assert all(p in epmc.PAPERS for p in SEIZURE_PAPERS), "add the paper to fetch_europepmc.PAPERS"

# An excipient notice (terpene suppositories "peuvent abaisser le seuil épileptogène")
# speaks of the product's excipient, not of the molecule.
# 4.1 indications ("traitement de l'épilepsie": the anticonvulsants' ``raises``), 4.2-4.4
# warnings, 5.1 pharmacodynamics ("activité anticonvulsivante").
RCP_SECTIONS = ("4.1", "4.2", "4.3", "4.4", "5.1")

# How far above a seizure line its withdrawal context may sit (see _with_stopping_context).
STOP_LOOKBACK = 2
# The line above that makes a seizure line a withdrawal one (narrower than S.STOPPING:
# a bare "arrêter le traitement" ends many unrelated paragraphs).
WITHDRAWAL_RE = re.compile(r"sevrage|withdraw|rebond|rebound", re.IGNORECASE)

EXCIPIENT_RE = re.compile(r"excipient|terp[ée]n", re.IGNORECASE)


def _with_stopping_context(lines: list[dict], i: int, page: str) -> str:
    """Line ``i``, or, when it names seizures but not stopping and one of the
    :data:`STOP_LOOKBACK` lines just above it in the same section speaks of withdrawal
    (:data:`WITHDRAWAL_RE`), the run from that line through line ``i`` joined by spaces,
    kept only when verbatim on ``page`` (the normalized page text: a heading between the
    lines breaks it).
    A benzodiazepine label says "Cet état peut entraîner à l'arrêt du traitement un
    phénomène de sevrage." then, two lines on, "... phénomènes hallucinatoires,
    convulsions.": only the run says the convulsions are withdrawal ones."""
    line = lines[i]["line"]
    if re.search(S.STOPPING, line, re.IGNORECASE):
        return line
    for j in range(i - 1, max(-1, i - 1 - STOP_LOOKBACK), -1):
        # A list item's page text keeps its "- " marker, so a run through one is not verbatim.
        if lines[j]["section"] != lines[i]["section"] or lines[j]["item"] or lines[i]["item"]:
            break
        if WITHDRAWAL_RE.search(lines[j]["line"]):
            run = " ".join(ln["line"] for ln in lines[j:i + 1])
            return run if normalize_for_match(run) in page else line
    return line


def _rcp_candidates(labels: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for did, entry in sorted(labels.items()):
        path = corpus_page_path(fetch_workup.CORPUS, entry["page"])
        if not path or not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        lines, page = fetch_workup.page_lines(text), normalize_for_match(text)
        for i, ln in enumerate(lines):
            if ln["section"] in RCP_SECTIONS and S.about_seizures(ln["line"]) \
                    and not EXCIPIENT_RE.search(ln["line"]):
                out[did].append({"corpus": fetch_workup.CORPUS, "page": entry["page"],
                                 "section": ln["section"],
                                 "quote": _with_stopping_context(lines, i, page)})
    return out


def _name_patterns(drugs: list[dict]) -> dict[str, re.Pattern]:
    """drug id -> a whole-word pattern of its INN (parenthetical qualifier dropped),
    for names only one roster id carries."""
    by_name: dict[str, list[str]] = defaultdict(list)
    for d in drugs:
        base = re.sub(r"\s*\(.*\)\s*$", "", d["name"]).strip().lower()
        if base:
            by_name[base].append(d["id"])
    return {ids[0]: re.compile(rf"\b{re.escape(n)}\b", re.IGNORECASE)
            for n, ids in by_name.items() if len(ids) == 1}


def _paper_lines(pmid: str) -> list[str]:
    """The abstract / body sentences of a stored Europe PMC page (header lines dropped)."""
    path = corpus_page_path("europepmc", pmid)
    if not path or not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    body = lines[next((i for i, l in enumerate(lines) if l.startswith("fetched:")), 0) + 1:]
    return [l.strip() for l in body if l.strip() and not l.startswith("#")]


def _paper_candidates(drugs: list[dict]) -> dict[str, list[dict]]:
    pats = _name_patterns(drugs)
    out: dict[str, list[dict]] = defaultdict(list)
    for pmid in SEIZURE_PAPERS:
        for line in _paper_lines(pmid):
            if not S.about_seizures(line):
                continue
            for did, pat in pats.items():
                if pat.search(line):
                    out[did].append({"corpus": "europepmc", "page": pmid, "quote": line})
    return out


def build(labels: dict | None = None, drugs: list[dict] | None = None) -> dict[str, dict]:
    """``{drug_id: {candidates: [{index, corpus, page, section?, quote}]}}``."""
    if labels is None:
        labels = (json.loads(fetch_workup.LABELS.read_text(encoding="utf-8"))
                  if fetch_workup.LABELS.exists() else {})
    if drugs is None:
        drugs = drugs_io.load_drugs()
    merged: dict[str, list[dict]] = defaultdict(list)
    for part in (_rcp_candidates(labels), _paper_candidates(drugs)):
        for did, cands in part.items():
            merged[did].extend(cands)
    out = {}
    for did in sorted(merged):
        seen, cands = set(), []
        for c in merged[did]:
            key = (c["corpus"], str(c["page"]), c["quote"])
            if key not in seen:
                seen.add(key)
                cands.append({"index": len(cands), **c})
        out[did] = {"candidates": cands}
    return out


def main() -> int:
    wl = build()
    worklist_io.write(WORKLIST, wl)
    n = sum(len(v["candidates"]) for v in wl.values())
    print(f"[ok] {n} candidate line(s) over {len(wl)} drug(s) -> {WORKLIST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
