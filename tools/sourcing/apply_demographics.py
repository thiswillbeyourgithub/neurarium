#!/usr/bin/env python
"""Gate the ``receptor_demographic`` picks and write ``generated_cache/receptor_demographics.json``.

Third step of the four-step pipeline (see ``tools/fetch/fetch_demographics.py`` first): an
LLM read ``demographics_worklist.json`` and answered by candidate index into
``demographics_judged.json``::

    {"owners": {"d2": [{"factor": "age", "direction": "decrease", "structure": "caudate",
                        "magnitude": "6.6% per decade in caudate", "picks": [12]}]}}

This applier is the **sole writer** of the cache and rebuilds it from the judged file on
every run (dropping a pick there, e.g. on a judge reject, drops its node here). A node
lands only when every gate passes, all or nothing per node:

1. the owner is in the worklist AND is still a current receptor / target;
2. ``factor`` / ``direction`` sit in the closed vocabulary and ``structure`` (when given) is
   a modeled structure (``demographics.vocab_error``);
3. every picked candidate was offered for that factor (its age / sex cue hit);
4. every picked paper is a human one: its MeSH species ledger
   (``generated_cache/europepmc_species.json``) names ``human`` (animal studies are out);
5. ``magnitude`` (when given) is verbatim in one of the picked sentences, and rides that
   source only;
6. every picked sentence is still verbatim on its stored page (``pipeline.gate.PageGate``).

The loop and command line are ``prose_gate.apply_picks`` / ``run_applier``, shared with
``apply_receptor_effects.py`` and ``apply_release_modulation.py``. It writes no ``llm``
stamp, so ``recheck_quotes.py`` (``--kinds receptor_demographic``) must judge the new
citations afterwards, or ``check_data.py`` family 5 fails them as extracted-but-unjudged.

Usage (from the repo root)::

    python tools/sourcing/apply_demographics.py --dry-run
    python tools/sourcing/apply_demographics.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "fetch"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_generators.demographics import CACHE, node_key, vocab_error  # noqa: E402
from prose_gate import apply_picks, not_offered, run_applier  # noqa: E402
from pipeline.judged import resolve  # noqa: E402
from apply_receptor_effects import current_kinds  # noqa: E402 (receptors + targets)
from apply_release_modulation import current_structures  # noqa: E402
from lib.quote_match import normalize_for_match  # noqa: E402
from fetch_europepmc import PAGES_DIR, SPECIES_LEDGER  # noqa: E402

WORKLIST = TOOLS / "generated_cache" / "demographics_worklist.json"
JUDGED = TOOLS / "generated_cache" / "demographics_judged.json"
PAGES = {"europepmc": PAGES_DIR}


def apply(worklist: dict, judged: dict, kinds: dict[str, str], structures: set[str],
          species: dict[str, list[str]], pages: dict = PAGES) -> tuple[dict, list[str]]:
    """``(cache, misses)``: the rebuilt ``{owner: {node key: [source]}}`` cache."""
    magnitudes: dict[tuple[str, str], str] = {}

    def check(oid, node, cands):
        f = {k: node.get(k) for k in ("factor", "direction", "structure")}
        key = node_key(**f)
        why = vocab_error(f, structures)
        if why:
            return key, why
        picks = node.get("picks") or []
        off = not_offered(cands, picks, "factors", f["factor"])
        if off:
            return key, f"candidate(s) {off} were not offered for {f['factor']!r}"
        picked = [c for c in (resolve(cands, p)[0] for p in picks) if c is not None]
        animal = sorted({c["page"] for c in picked
                         if "human" not in species.get(str(c["page"]), [])})
        if animal:
            return key, f"paper(s) {animal} are not human studies (species ledger)"
        mag = node.get("magnitude")
        if mag:
            if not any(normalize_for_match(mag) in normalize_for_match(c["line"])
                       for c in picked):
                return key, f"magnitude {mag!r} is in none of the picked sentences"
            magnitudes[(oid, key)] = mag
        return key, None

    cache, misses = apply_picks(worklist, judged, kinds, check, pages)
    for (oid, key), mag in magnitudes.items():
        for src in (cache.get(oid) or {}).get(key, []):
            if normalize_for_match(mag) in normalize_for_match(src["quote"]):
                src["magnitude"] = mag
                break
    return cache, misses


def main() -> int:
    species = json.loads(SPECIES_LEDGER.read_text("utf-8")) if SPECIES_LEDGER.exists() else {}
    return run_applier(__doc__, WORKLIST, JUDGED, CACHE,
                       lambda w, j: apply(w, j, current_kinds(), current_structures(),
                                          species),
                       "receptor_demographic")


if __name__ == "__main__":
    raise SystemExit(main())
