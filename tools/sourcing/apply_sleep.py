#!/usr/bin/env python
"""Gate judged sleep picks and write ``drug_sleep`` nodes.

Third of the four steps (worklist: ``tools/fetch/fetch_sleep.py``): reads the LLM's
``tools/generated_cache/sleep_judged.json`` (``{drug: [{index, qid, effect, species?}]}``,
``[]`` = nothing to take) and writes ``tools/generated_cache/sleep.json``, every pick
re-gated by ``drug_effect_gate.gate`` (offered drug, index + qid, effect in
``sleep.EFFECTS`` and said by the line, line verbatim on its paper page). ``species``
records the animal a sentence is about ("rat"), raising the animal_evidence flag.

Example pick: ``{"index": 0, "qid": "5b0c11e2", "effect": "rem_suppression"}``.

Writes no ``llm`` stamp, so ``tools/sourcing/recheck_quotes.py build --kinds drug_sleep
--unjudged`` + judge + apply must follow.

Usage (repo root)::

    python tools/sourcing/apply_sleep.py --dry-run
    python tools/sourcing/apply_sleep.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))

import fetch_sleep                                              # noqa: E402
import drug_effect_gate                                         # noqa: E402
from data_generators import sleep as S                          # noqa: E402

JUDGED_PATH = ROOT / "tools" / "generated_cache" / "sleep_judged.json"


def main() -> int:
    return drug_effect_gate.main(S.KIND, JUDGED_PATH, fetch_sleep.build, __doc__)


if __name__ == "__main__":
    raise SystemExit(main())
