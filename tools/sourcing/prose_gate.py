"""The owner-keyed loop shared by the by-index prose appliers.

A worklist lists indexed candidate sentences ``{corpus, page, line}``; an LLM answers by
index; the applier turns each picked index back into a source. The page check itself is
``pipeline.gate.PageGate`` (written once, for every applier); this module holds what the
prose appliers add on top: idempotent :func:`add_source`, the :func:`apply_picks` loop
and the :func:`run_applier` driver.

Used by ``apply_classification_sources.py --prose``, ``apply_projection_sources.py`` and
``apply_cyp_sources.py``.

Built with the help of Claude Code.
"""
from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from pipeline.gate import PageGate  # noqa: E402 (the page gate, written once)
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
from pipeline.judged import resolve  # noqa: E402
from lib.io_atomic import atomic_write_json  # noqa: E402


def add_source(bucket: list, src: dict, key=None) -> bool:
    """Append ``src`` unless a source with the same quote is already there (idempotence).

    ``key`` maps a quote before comparing (e.g. ``normalize_for_match``, so two spellings
    of one sentence count as one source); the default compares quotes verbatim.
    """
    key = key or (lambda q: q)
    if any(key(s.get("quote") or "") == key(src["quote"]) for s in bucket):
        return False
    bucket.append(src)
    return True


def apply_picks(worklist: dict, judged: dict, owners_ok, check, pages: dict,
                stamp=None) -> tuple[dict[str, dict[str, list]], list[str]]:
    """The shared loop of an owner-keyed by-index applier: ``(cache, misses)``.

    ``judged["owners"][oid]`` is a list of node dicts, each with ``picks``. A node lands
    under ``cache[oid][key]`` only when the owner is in the worklist AND ``owners_ok``,
    ``check(oid, node, cands)`` returns ``(key, None)`` (else ``(None, reason)``: a
    vocabulary or "cue not offered" refusal), it has picks, and every pick passes the
    page gate. All or nothing per node; the cache is rebuilt from scratch on every run.
    ``stamp(node, pick, source)``, when given, annotates each source of a node that
    landed, before it is merged (so a refused node is never read).
    """
    owners = worklist.get("owners", {})
    gate = PageGate(pages)
    out: dict[str, dict[str, list]] = {}
    misses: list[str] = []
    for oid, nodes in sorted((judged.get("owners") or {}).items()):
        own = owners.get(oid)
        if own is None or oid not in owners_ok:
            misses.append(f"{oid}: not in the worklist / not a current owner")
            continue
        cands = own.get("candidates", [])
        for node in nodes or []:
            key, why = check(oid, node, cands)
            what = f"{oid}/{key or node}"
            if why:
                misses.append(f"{what}: {why}")
                continue
            if not node.get("picks"):
                misses.append(f"{what}: no picks")
                continue
            srcs = gate.sources(cands, node["picks"], what, misses)
            if not srcs:
                continue
            if stamp:
                for pick, src in zip(node["picks"], srcs):
                    stamp(node, pick, src)
            bucket = out.setdefault(oid, {}).setdefault(key, [])
            for s in srcs:
                add_source(bucket, s)
    return out, misses


def not_offered(cands: list[dict], picks, field: str, value: str) -> list[int]:
    """The indices of the resolvable picks whose candidate was never offered ``value``
    under ``field``."""
    out = []
    for p in picks or []:
        cand, _ = resolve(cands, p)
        if cand is not None and value not in cand.get(field, []):
            out.append(p["index"])
    return out


def run_applier(doc: str, worklist_path: Path, judged_path: Path, cache_path: Path,
                apply, label: str) -> int:
    """The shared ``--dry-run`` command line of an owner-keyed applier: run ``apply(worklist,
    judged)``, print the misses, write the cache sorted (unless dry run)."""
    import argparse
    ap = argparse.ArgumentParser(description=doc,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()
    cache, misses = apply(worklist_io.read(worklist_path),
                          worklist_io.read(judged_path))
    for m in misses:
        print(f"  [miss] {m}", file=sys.stderr)
    n = sum(len(v) for v in cache.values())
    print(f"{n} {label} node(s) over {len(cache)} owner(s), {len(misses)} miss(es)")
    if args.dry_run:
        print("(dry run: not written)")
        return 0
    atomic_write_json(cache_path, cache, indent=1, sort_keys=True)
    print(f"wrote {cache_path}")
    return 0
