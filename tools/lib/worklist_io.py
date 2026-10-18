"""Shared helper for the ``--only`` scoped rebuild of an LLM worklist.

Every worklist under ``tools/generated_cache/`` is answered **by index** into a committed
``*_judged.json``. A scoped (``--only``) rebuild that overwrote the whole file would orphan
every other entry's already-applied picks (it once dropped 5600 lines of candidates), so a
scoped build is **merged** into the existing worklist instead.

:func:`write` is the one way a fetcher saves a worklist: it stamps every candidate's
``qid`` fingerprint first (``pipeline.judged``), so the judge can echo it and the applier
can refuse a pick whose index has since shifted onto another sentence.

:func:`read` is the matching way an applier loads its worklist or ``*_judged.json``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.io_atomic import atomic_write_json
from pipeline.judged import stamp


def merge_scoped(existing: dict, scoped: dict, key: str) -> dict:
    """Merge a scoped build into ``existing``: entries under ``key`` are merged (scoped
    wins per entry), every other top-level field is taken from the fresh ``scoped`` build.

    >>> merge_scoped({"v": 1, "d": {"x": 1, "y": 2}}, {"v": 2, "d": {"y": 3}}, "d")
    {'v': 2, 'd': {'x': 1, 'y': 3}}
    """
    out = {**existing, **{k: v for k, v in scoped.items() if k != key}}
    out[key] = {**existing.get(key, {}), **scoped.get(key, {})}
    return out


def merge_scoped_list(existing: list, scoped: list, key: str) -> list:
    """The list-shaped twin of :func:`merge_scoped`: entries matched on ``entry[key]``,
    a scoped entry replacing its old self in place, a new one appended.

    >>> merge_scoped_list([{"k": "a", "v": 1}, {"k": "b", "v": 2}],
    ...                   [{"k": "b", "v": 3}, {"k": "c", "v": 4}], "k")
    [{'k': 'a', 'v': 1}, {'k': 'b', 'v': 3}, {'k': 'c', 'v': 4}]
    """
    fresh = {e[key]: e for e in scoped}
    out = [fresh.pop(e[key], e) for e in existing]
    return out + list(fresh.values())


def write(path, worklist, indent: int = 1, sort_keys: bool = False) -> None:
    """Stamp ``qid`` on every candidate of ``worklist`` and write it as UTF-8 JSON."""
    atomic_write_json(path, stamp(worklist), indent=indent, sort_keys=sort_keys)


def read(path, required: bool = True, default: Any = None) -> Any:
    """The parsed JSON of a worklist or judged file.

    Parameters
    ----------
    path
        The file (``str`` or ``Path``), read as UTF-8.
    required
        When true (the default) a missing file raises ``FileNotFoundError``: an applier
        run before its fetcher should stop, not apply nothing. When false a missing
        file returns ``default`` (a judge pass that has not run yet is "no picks").
    default
        What an absent, not-required file reads as.

    Returns
    -------
    Any
        The parsed document, or ``default``.

    A file that exists but does not parse always raises (``json.JSONDecodeError``),
    whatever ``required`` says: a truncated judged file must never read as "no picks".
    """
    path = Path(path)
    if not required and not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))
