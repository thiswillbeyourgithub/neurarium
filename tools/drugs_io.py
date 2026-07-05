"""Shared I/O for the authored drug dataset (``tools/data/drugs_data.jsonl``).

The dataset is stored as JSONL (one compact JSON object per line) rather than a
single pretty-printed JSON array: line-oriented diffs stay small and every
consumer reads/writes it the same way. Centralized here so the five consumers
(``generate_data.py``, ``fetch_ki.py``, ``apply_nbn_sources.py``,
``apply_category_sources.py``, ``apply_source_quotes.py``) don't hand-roll it.
"""

import json
from pathlib import Path

DRUGS_PATH = Path(__file__).resolve().parent / "data" / "drugs_data.jsonl"


def load_drugs(path=None) -> list[dict]:
    """Read the JSONL dataset, one ``json.loads`` per non-empty line, in order."""
    p = Path(path) if path is not None else DRUGS_PATH
    records = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def save_drugs(records, path=None) -> None:
    """Write the records as JSONL (compact, key order preserved), one per line."""
    p = Path(path) if path is not None else DRUGS_PATH
    lines = [json.dumps(rec, ensure_ascii=False) for rec in records]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
