#!/usr/bin/env python
"""Apply the judged time-to-peak (Tmax) to the drugs, quote-gated.

Second half of the pipeline started by ``tools/fetch/fetch_tmax.py``: the fetch pass
wrote a worklist of candidate peak lines, an LLM read it into
``tools/generated_cache/tmax_judged.json`` answering per drug with a candidate
**index** plus the hours that candidate states, and this applier writes the drug's
``tmax`` (``{hours, hours_max?}``) + a ``verified`` ``tmax_sources`` quote node.

An index, never a quote string, for the same reason the CYP pass uses one: a paraphrase
is then not expressible, and the worst failure is picking the wrong true sentence,
which the gates below catch. The **number is not the LLM's either**: it must be one the
quote actually contains, re-parsed here by code, so the model only ever answers *which
line is this drug's own oral time-to-peak*.

Six gates, all re-derived here rather than trusted from the judged file:

1. the drug is in the dataset;
2. the drug was **offered** by a fresh ``fetch_tmax.build()`` (a judged file naming a
   drug the fetcher never proposed cannot smuggle one in);
3. the index resolves into that drug's candidate list;
4. the judged ``{hours, hours_max?}`` equals one of the durations the candidate line
   states (computed by ``fetch_tmax.durations_in``, not by the model);
5. the value is a plausible ORAL time-to-peak (``MAX_TMAX_HOURS``), which is what the
   simulation models. A depot injection or an implant peaks in days (aripiprazole LAI
   at 6.5-7.1 days is a real number about a different formulation), and writing it
   would make the tablet's curve nonsense;
6. the quote is verbatim, under ``check_data.normalize_for_match``, on the page it
   cites: ``data_sources/books/stahl/pages/<n>.md`` for corpus #1, or
   ``data_sources/wikipedia/pages/<slug>.md`` for corpus #9.

Sole writer of ``tmax`` / ``tmax_sources`` and idempotent: a re-run replaces a judged
drug's value from the current judged file, and a drug absent from it is left untouched.
It writes no ``llm`` stamp, so ``tools/sourcing/recheck_quotes.py`` must run afterwards
or ``check_data.py`` family 5 flags the new citations as extracted-but-unjudged.

Usage (from the repo root)::

    python tools/sourcing/apply_tmax.py --dry-run
    python tools/sourcing/apply_tmax.py

Stdlib only; author-side (needs the gitignored ``data_sources/`` trees, since without
them the quote gate cannot run and the applier refuses rather than writing ungated
quotes).

Built with the help of Claude Code.
"""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))

import drugs_io                                                 # noqa: E402
import fetch_tmax                                               # noqa: E402

JUDGED_PATH = ROOT / "tools" / "generated_cache" / "tmax_judged.json"
STAHL_PAGES = ROOT / "data_sources" / "books" / "stahl" / "pages"
WIKI_PAGES = ROOT / "data_sources" / "wikipedia" / "pages"

# Above this, the line is about a depot / implant / modified-release formulation, not
# the oral single dose the simulation draws (gate 5). 24 h is generous: the slowest
# oral peaks in the roster sit around 8 h.
MAX_TMAX_HOURS = 24.0

# Reuse check_data's canonical quote-gate normalization (single source of truth), so a
# quote that passes here also passes check_data's later re-gate.
_spec = importlib.util.spec_from_file_location("cd", ROOT / "tools" / "check_data.py")
_cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cd)
normalize_for_match = _cd.normalize_for_match


def page_path(corpus: str, page) -> Path | None:
    """The stored page a candidate's ``(corpus, page)`` pair cites, or None."""
    if corpus == "stahl":
        try:
            return STAHL_PAGES / f"{int(page)}.md"
        except (TypeError, ValueError):
            return None
    if corpus == "wikipedia_pharm":
        slug = str(page or "")
        return (WIKI_PAGES / f"{slug}.md") if slug else None
    return None


def same_duration(judged: dict, stated: dict) -> bool:
    """Whether a judged ``{hours, hours_max?}`` is one the quote actually states.

    Compared with a small tolerance because the judged value round-trips through JSON
    and the parsed one through a unit conversion (45 minutes is 0.75 h either way, but
    not bit-for-bit once a model writes 0.75 and the parser computes 45/60).
    """
    def close(a, b) -> bool:
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        return abs(float(a) - float(b)) <= 1e-3
    return (close(judged.get("hours"), stated.get("hours"))
            and close(judged.get("hours_max"), stated.get("hours_max")))


def clean_value(rec: dict) -> dict | None:
    """A validated ``{hours, hours_max?}`` out of the judged record, or None."""
    try:
        hours = float(rec.get("hours"))
    except (TypeError, ValueError):
        return None
    if hours <= 0:
        return None
    out = {"hours": round(hours, 3)}
    hi = rec.get("hours_max")
    if hi is not None:
        try:
            hi = float(hi)
        except (TypeError, ValueError):
            hi = None
        if hi is not None and hi >= hours:
            out["hours_max"] = round(hi, 3)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judged", type=Path, default=JUDGED_PATH,
                    help="the LLM-judged Tmax file")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing drugs_data.jsonl")
    args = ap.parse_args()

    if not WIKI_PAGES.is_dir():
        print(f"[error] {WIKI_PAGES} absent (author-side corpus tree missing); the "
              f"quote gate cannot run, refusing to write ungated quotes. See "
              f"CLAUDE.local.md.", file=sys.stderr)
        return 1
    if not args.judged.exists():
        print(f"[error] judged file {args.judged} not found; run the LLM pass first.",
              file=sys.stderr)
        return 1

    judged = json.loads(args.judged.read_text(encoding="utf-8"))
    offered = fetch_tmax.build()                       # gate 2: freshly re-derived
    drugs = drugs_io.load_drugs()
    by_id = {d["id"]: d for d in drugs}

    text_cache: dict[str, str] = {}

    def page_text(path: Path) -> str:
        key = str(path)
        if key not in text_cache:
            text_cache[key] = (normalize_for_match(
                path.read_text(encoding="utf-8", errors="replace"))
                if path.exists() else "")
        return text_cache[key]

    written = 0
    rejected: list[str] = []

    def reject(did: str, why: str) -> None:
        rejected.append(f"{did}: {why}")

    for did, rec in judged.items():
        drug = by_id.get(did)
        if not drug:
            reject(did, "not a dataset drug")
            continue
        entry = offered.get(did)
        if not entry:
            reject(did, "the fetcher offers no candidate for this drug")
            continue
        try:
            idx = int(rec.get("index"))
        except (TypeError, ValueError):
            reject(did, f"index {rec.get('index')!r} is not a number")
            continue
        if not (0 <= idx < len(entry["candidates"])):
            reject(did, f"index {idx} is outside the {len(entry['candidates'])} offered")
            continue
        cand = entry["candidates"][idx]
        value = clean_value(rec)
        if not value:
            reject(did, "no usable hours in the judged record")
            continue
        if not any(same_duration(value, d) for d in cand["durations"]):
            reject(did, f"{value} is not a duration the quote states "
                        f"({cand['durations']})")
            continue
        if value["hours"] > MAX_TMAX_HOURS:
            reject(did, f"{value['hours']} h is not an oral time-to-peak "
                        f"(> {MAX_TMAX_HOURS} h, likely a depot or implant)")
            continue
        path = page_path(cand["corpus"], cand["page"])
        if not path or not path.exists():
            reject(did, f"no stored page for {cand['corpus']} {cand['page']!r}")
            continue
        if normalize_for_match(cand["line"]) not in page_text(path):
            reject(did, "the quote is not verbatim on its page")
            continue
        drug["tmax"] = value
        drug["tmax_sources"] = [{"corpus": cand["corpus"], "page": cand["page"],
                                 "quote": cand["line"], "provenance": "verified"}]
        written += 1

    if args.dry_run:
        print(f"[dry-run] would set tmax on {written} drug(s); "
              f"{len(rejected)} rejected.")
    else:
        drugs_io.save_drugs(drugs)
        print(f"[ok] set tmax on {written} drug(s); {len(rejected)} rejected. "
              f"Wrote {drugs_io.DRUGS_PATH.relative_to(ROOT)}.")
    for r in rejected[:40]:
        print(f"  [reject] {r}")
    if len(rejected) > 40:
        print(f"  ... and {len(rejected) - 40} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
