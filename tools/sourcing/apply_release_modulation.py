#!/usr/bin/env python
"""Gate ``receptor_release_modulation`` picks and write ``generated_cache/release_modulation.json``.

Third step of the four-step pipeline (see ``tools/fetch/fetch_release_modulation.py`` first):
an LLM read ``release_modulation_worklist.json`` and answered by candidate index into
``release_modulation_judged.json``::

    {"owners": {"5ht2c": [{"kind": "heteroreceptor", "structure": "vta",
                           "cell": "gaba_interneuron", "modulates": "dopamine",
                           "effect": "decrease", "picks": [3]}]}}

This applier is the **sole writer** of the cache and rebuilds it from the judged file on
every run (dropping a pick there, e.g. on a judge reject, drops the node here). A node
lands only when every gate passes, all or nothing per node:

1. the owner is in the worklist AND still a current receptor;
2. kind / cell / modulates / effect sit in the closed vocabularies, ``structure`` (when
   given) is a modeled structure, and an autoreceptor sits on a terminal or cell body and
   modulates its receptor's own transmitter (``release_modulation.vocab_error``);
3. every picked candidate was offered for ``modulates`` (the sentence names it);
4. every picked sentence is still verbatim on its stored page (``pipeline.gate.PageGate``).

The loop and the command line are ``prose_gate.apply_picks`` / ``run_applier``, shared with
``apply_receptor_effects.py``. It writes no ``llm`` stamp, so ``recheck_quotes.py``
(``--kinds receptor_release_modulation``) must judge the new citations afterwards, or
``check_data.py`` family 5 fails them as extracted-but-unjudged.

Usage (from repo root)::

    python tools/sourcing/apply_release_modulation.py --dry-run
    python tools/sourcing/apply_release_modulation.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_generators.release_modulation import CACHE, node_key, vocab_error  # noqa: E402
from lib.structure_ids import bases_of  # noqa: E402
from prose_gate import apply_picks, not_offered, run_applier  # noqa: E402
from apply_classification_sources import PROSE_PAGES  # noqa: E402 (same two corpora)

WORKLIST = TOOLS / "generated_cache" / "release_modulation_worklist.json"
JUDGED = TOOLS / "generated_cache" / "release_modulation_judged.json"


def _jsonl(name: str) -> list[dict]:
    return [json.loads(ln) for ln in (REPO / "public/data" / name).read_text("utf-8").splitlines()
            if ln.strip()]


def current_receptors() -> dict[str, str]:
    """``{receptor id: neurotransmitter}`` for what the dataset models today."""
    return {r["id"]: r.get("neurotransmitter") for r in _jsonl("receptors.jsonl")}


def current_structures() -> set[str]:
    """Modeled structure base ids (a mirrored ``x_R`` counts as ``x``)."""
    return bases_of(_jsonl("structures.jsonl"))


def apply(worklist: dict, judged: dict, receptors: dict[str, str], structures: set[str],
          pages: dict = PROSE_PAGES) -> tuple[dict, list[str]]:
    """``(cache, misses)``: the rebuilt ``{receptor: {node_key: [source]}}`` cache."""
    def check(oid, node, cands):
        f = {k: node.get(k) for k in ("kind", "structure", "cell", "modulates", "effect")}
        try:
            key = node_key(**f)
        except TypeError:
            return None, "a field is missing"
        why = vocab_error(f, receptors[oid], structures)
        if why:
            return key, why
        off = not_offered(cands, node.get("picks"), "transmitters", f["modulates"])
        if off:
            return key, f"candidate(s) {off} never name {f['modulates']!r}"
        return key, None
    return apply_picks(worklist, judged, receptors, check, pages)


def main() -> int:
    return run_applier(__doc__, WORKLIST, JUDGED, CACHE,
                       lambda w, j: apply(w, j, current_receptors(), current_structures()),
                       "receptor_release_modulation")


if __name__ == "__main__":
    raise SystemExit(main())
