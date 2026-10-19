#!/usr/bin/env python
"""Fetch GtoPdb's curated *function* prose for every receptor / target (corpus #23).

GtoPdb's fourth slice, after the tissue distribution (#7, ``fetch_gtopdb.py``), the
ligand interactions (#11, ``fetch_gtopdb_ki.py``) and the classification facts (#12,
``fetch_gtopdb_class.py``). Per target it reads three curated sections of the target page
plus their free-text comments:

- ``/function``: "Physiological Functions", one ``property`` + ``tissue`` + **species**
  per row;
- ``/pathophysiology``: "Clinically-Relevant Mutations and Pathophysiology", one human
  disease per row with optional ``role`` / ``sideEffects`` / ``use`` / ``comments`` prose
  and mutation descriptions (no species field: the section is clinical by definition,
  so its lines carry no species tag rather than an assumed one);
- ``/alteredExpression``: "Physiological Consequences of Altering Gene Expression", one
  ``property`` + **species** per row (nearly all knockout mice);
- ``/comments``: the section comments (``functionComments``, ``alteredExpressionComments``,
  ``pathophysiologyComments``), split on ``<br>``.

Nothing here decides anything: the receptor-effect fetcher
(``fetch_receptor_effects.py``) offers these lines as candidates, offering a row with a
stated species only when that species is human (:func:`offerable`), an LLM picks by index,
the applier gates. Every line keeps its section and species in its own text, so a stored
quote reads on its own in the source pill.

Outputs (author-side, under the gitignored ``data_sources/gtopdb/``):

- ``raw_function/<owner>.json``: the four raw responses + the flattened ``lines``
  (``[{line, section, species}]``) the effect fetcher reads;
- ``pages_function/<targetId>.md``: the quote-gate page, a provenance header (source URL,
  ``fetched: YYYY-MM-DD``) then one cleaned statement per line, which
  ``check_data.py``'s verbatim-quote gate checks stored quotes against.

A group target that shares its representative gene with a modeled receptor (``muscarinic``
-> CHRM1 = ``m1``) is skipped: an M1 row is about M1, not every muscarinic receptor.
Contents CC BY-SA 4.0, database ODbL (as corpora #7 / #11 / #12).

Usage (from the repo root, network, API key as for corpus #7)::

    python tools/fetch/fetch_gtopdb_function.py
    python tools/fetch/fetch_gtopdb_function.py --only beta3,glycine
    python tools/fetch/fetch_gtopdb_function.py --refresh
    python tools/fetch/fetch_gtopdb_function.py --no-fetch   # re-flatten raw/ offline

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from fetch_gtopdb import BASE, clean, file_date, http_json  # noqa: E402
from fetch_gtopdb_class import subject, target_record  # noqa: E402
from data_generators import genes  # noqa: E402
from lib.page_file import page_path  # noqa: E402 (refuses a path-like page)
from lib.species import species_key  # noqa: E402

REPO = HERE.parent.parent
OUT = REPO / "data_sources" / "gtopdb"
RAW = OUT / "raw_function"
PAGES = OUT / "pages_function"
CLASS_RAW = OUT / "raw_class"
PAGE_URL = "https://www.guidetopharmacology.org/GRAC/ObjectDisplayForward?objectId={}"

# The endpoints read per target (key in the raw cache -> service path).
ENDPOINTS = {"function": "function", "pathophysiology": "pathophysiology",
             "altered": "alteredExpression", "comments": "comments"}
COMMENT_FIELDS = {"functionComments": "function comment",
                  "alteredExpressionComments": "altered gene expression comment",
                  "pathophysiologyComments": "pathophysiology comment"}
_BR = re.compile(r"<br\s*/?>", re.I)
_SPACE_PUNCT = re.compile(r"\s+([.,;:)])")


def tidy(text: str) -> str:
    """``fetch_gtopdb.clean`` plus closing the gap a stripped ``<Reference id=../>`` tag
    leaves before punctuation ("isoforms ." -> "isoforms.")."""
    return _SPACE_PUNCT.sub(r"\1", clean(text))


def owners() -> dict[str, tuple[str, str]]:
    """``{owner id: (gene, kind)}``: every receptor, then every target whose gene no
    receptor already claims (see the module docstring)."""
    out = {rid: (g, "receptor") for rid, g in genes.RECEPTOR_GENES.items()}
    taken = set(genes.RECEPTOR_GENES.values())
    out.update({tid: (g, "target") for tid, g in genes.TARGET_GENES.items()
                if g not in taken})
    return out


def flatten(payload: dict) -> list[dict]:
    """The page's statement lines ``[{line, section, species}]`` from one raw payload.

    ``species`` is GtoPdb's own label, or ``None`` when the section states none.
    """
    subj = subject(payload, payload["gene"])
    out: list[dict] = []

    def add(section: str, text: str, species: str | None = None, extra: str = "") -> None:
        text = tidy(text)
        if not text:
            return
        tag = f"{section} ({tidy(species)})" if species else section
        line = f"{subj} | {tag}: {text}" + (f" | {extra}" if extra else "")
        if not any(o["line"] == line for o in out):
            out.append({"line": line, "section": section,
                        "species": tidy(species) if species else None})

    for e in payload.get("function") or []:
        tissue = tidy(e.get("tissue", ""))
        add("physiological function", e.get("property", ""), e.get("species"),
            f"tissue: {tissue}" if tissue else "")
    for e in payload.get("pathophysiology") or []:
        disease = tidy((e.get("disease") or {}).get("name", ""))
        for field, label in (("role", "role"), ("sideEffects", "side effects"),
                             ("use", "use"), ("drugs", "drugs"), ("comments", "comments")):
            if tidy(e.get(field, "")):
                add("pathophysiology", f"{disease} | {label}: {e[field]}")
        for m in e.get("mutations") or []:
            if isinstance(m, dict) and tidy(m.get("description", "")):
                add("pathophysiology", f"{disease} | mutation: {m['description']}")
    for e in payload.get("altered") or []:
        add("altered gene expression", e.get("property", ""), e.get("species"))
    for field, label in COMMENT_FIELDS.items():
        for part in _BR.split((payload.get("comments") or {}).get(field) or ""):
            add(label, part)
    return out


def offerable(item: dict) -> bool:
    """Whether a line may be offered as a candidate: a row whose species GtoPdb states is
    offered only when that species is human (a monkey row is animal evidence like a rat
    one, and an unnamed label stays out); a species-less row is offered."""
    return item.get("species") is None or species_key(item["species"]) == "human"


def page_text(payload: dict, lines: list[dict]) -> str:
    """The quote-gate page: provenance header, then one statement per line."""
    head = [f"source: {PAGE_URL.format(payload['target_id'])}",
            f"fetched: {payload['fetched']}"]
    return "\n".join(head + [x["line"] for x in lines]) + "\n"


def rows(data, comments: bool = False):
    """One endpoint's payload, with GtoPdb's "no data" answer folded to empty.

    A target with nothing in a section answers 200 with a one-key message dict
    (``{"GtoPdb Web Services": "No function data for target ID:4 "}``), not ``[]``.
    """
    if comments:
        return data if isinstance(data, dict) and "GtoPdb Web Services" not in data else {}
    return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []


def target_id(owner: str, gene: str) -> dict | None:
    """The GtoPdb target record, reused from the corpus #12 cache when it holds one."""
    cached = page_path(CLASS_RAW, owner, ".json")
    if cached.exists():
        c = json.loads(cached.read_text("utf-8"))
        if c.get("gene") == gene:
            return {k: c[k] for k in ("target_id", "target_name")}
    try:
        rec = target_record(gene)
    except SystemExit as exc:  # http_json exits after its retries (a 404: gene unknown)
        print(f"  [miss] {owner} ({gene}): {exc}", file=sys.stderr)
        return None
    return rec and {k: rec[k] for k in ("target_id", "target_name")}


def fetch_one(owner: str, gene: str, kind: str, refresh: bool, offline: bool) -> dict | None:
    """Fetch (or reuse) one owner's function payload and write its page; returns it.

    A cached payload is reused only when it was fetched for ``gene``: after a gene remap
    the old target's rows would otherwise be republished under the owner (refetched
    online; offline the owner is skipped with a warning)."""
    raw_path = page_path(RAW, owner, ".json")
    cached = json.loads(raw_path.read_text("utf-8")) if raw_path.exists() else None
    stale = cached is not None and cached.get("gene") != gene
    if stale:
        print(f"  [stale] {owner}: cached for {cached.get('gene')}, now {gene}",
              file=sys.stderr)
    if cached is not None and not stale and (offline or not refresh):
        payload = cached
    elif offline:
        return None
    else:
        rec = target_id(owner, gene)
        if rec is None:
            print(f"  [miss] {owner} ({gene}): no GtoPdb target", file=sys.stderr)
            return None
        payload = {"owner": owner, "kind": kind, "gene": gene, **rec,
                   "fetched": time.strftime("%Y-%m-%d")}
        for key, path in ENDPOINTS.items():
            payload[key] = rows(http_json(f"{BASE}/targets/{rec['target_id']}/{path}"),
                                key == "comments")
    if not payload.get("fetched"):
        payload["fetched"] = file_date(raw_path)
    payload["lines"] = flatten(payload)
    raw_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    page_path(PAGES, payload['target_id']).write_text(
        page_text(payload, payload["lines"]), encoding="utf-8")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated receptor/target ids (default all)")
    ap.add_argument("--refresh", action="store_true", help="refetch even a cached owner")
    ap.add_argument("--no-fetch", action="store_true",
                    help="re-flatten the stored raw/ responses, no network")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    PAGES.mkdir(parents=True, exist_ok=True)
    wanted = owners()
    if args.only:
        keep = [o.strip() for o in args.only.split(",") if o.strip()]
        unknown = [o for o in keep if o not in wanted]
        if unknown:
            raise SystemExit(f"error: unmapped ids: {unknown}")
        wanted = {o: wanted[o] for o in keep}
    n_lines = n_offer = n_owners = 0
    for owner, (gene, kind) in wanted.items():
        p = fetch_one(owner, gene, kind, args.refresh, args.no_fetch)
        if p is None:
            continue
        n_owners += 1
        n_lines += len(p["lines"])
        n_offer += sum(offerable(x) for x in p["lines"])
    print(f"{n_owners} owner(s), {n_lines} line(s), {n_offer} offerable "
          f"-> {PAGES.relative_to(REPO)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
