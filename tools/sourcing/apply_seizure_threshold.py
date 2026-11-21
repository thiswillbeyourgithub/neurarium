#!/usr/bin/env python
"""Gate the judged seizure-threshold picks and write ``drug_seizure_threshold`` nodes.

Third of the four steps (worklist: ``tools/fetch/fetch_seizure_threshold.py``): reads the
LLM's ``tools/generated_cache/seizure_threshold_judged.json`` (``{drug: [{index, qid,
effect}]}``, ``[]`` = nothing to take) and writes
``tools/generated_cache/seizure_threshold.json``. Every pick is re-gated:

1. the drug is a dataset drug and the fetcher, rebuilt now, offers it candidates;
2. ``index`` + ``qid`` resolve to the candidate it was judged on (``pipeline.judged``);
3. ``effect`` is in ``seizure_threshold.EFFECTS`` and the line itself says it
   (``seizure_threshold.says``: a seizure word, plus a stopping word for ``withdrawal``,
   an anticonvulsant word for ``raises``);
4. the line is verbatim on the page it cites (``PageGate`` over every corpus's pages).

One node per (drug, effect): a second accepted line adds a source.

Example pick: ``{"index": 1, "qid": "5b0c11e2", "effect": "lowers"}``.

The applier writes no ``llm`` stamp, so ``tools/sourcing/recheck_quotes.py build --kinds
drug_seizure_threshold --unjudged`` + judge + apply must follow, or ``check_data.py``
family 5 fails on extracted-but-unjudged citations.

Usage (repo root)::

    python tools/sourcing/apply_seizure_threshold.py --dry-run
    python tools/sourcing/apply_seizure_threshold.py

Built with the help of Claude Code.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))

import fetch_seizure_threshold                                  # noqa: E402
import drug_effect_gate                                         # noqa: E402
from data_generators import seizure_threshold as S              # noqa: E402

JUDGED_PATH = ROOT / "tools" / "generated_cache" / "seizure_threshold_judged.json"


def gate(judged, offered, drug_ids, pages):
    """Gate every pick (``drug_effect_gate.gate`` over the seizure vocabulary)."""
    return drug_effect_gate.gate(S.KIND, judged, offered, drug_ids, pages)


def main() -> int:
    return drug_effect_gate.main(S.KIND, JUDGED_PATH, fetch_seizure_threshold.build, __doc__)


if __name__ == "__main__":
    raise SystemExit(main())
