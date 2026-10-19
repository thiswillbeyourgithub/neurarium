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
   states (computed by ``lib.parse.durations.durations_in``, not by the model);
5. the value is a plausible ORAL time-to-peak (``MAX_TMAX_HOURS``), which is what the
   simulation models. A depot injection or an implant peaks in days (aripiprazole LAI
   at 6.5-7.1 days is a real number about a different formulation), and writing it
   would make the tablet's curve nonsense;
6. the quote is verbatim, under ``lib.quote_match.normalize_for_match``, on the page it
   cites: ``data_sources/books/stahl/pages/<n>.md`` for corpus #1,
   ``data_sources/wikipedia/pages/<slug>.md`` for corpus #9,
   ``data_sources/dailymed/pages/<setid>.md`` for corpus #14, or
   ``data_sources/bdpm/pages/<CIS>.md`` for corpus #16 (any corpus's ``pages_dir``).

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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "fetch"))

from lib import drugs_io                                                 # noqa: E402
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)
from data_generators import formulations as F  # noqa: E402 (placed: a claim already on a formulation)
from pipeline.judged import resolve  # noqa: E402
from pipeline.gate import PageGate, registry_pages              # noqa: E402
import fetch_tmax                                               # noqa: E402

JUDGED_PATH = ROOT / "tools" / "generated_cache" / "tmax_judged.json"
WIKI_PAGES = ROOT / "data_sources" / "wikipedia" / "pages"

# Above this, the line is about a depot / implant / modified-release formulation, not
# the oral single dose the simulation draws (gate 5). 24 h is generous: the slowest
# oral peaks in the roster sit around 8 h.
MAX_TMAX_HOURS = 24.0


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


def apply_judged(judged: dict, offered: dict, drugs: list[dict], field: str,
                 max_hours: float, too_long: str,
                 owned=None) -> tuple[int, list[str], list[str]]:
    """Gate every judged ``{index, hours, hours_max?}`` and write the survivors.

    Shared by every duration pass over a ``fetch_tmax.build`` worklist (this one and
    ``apply_half_life.py``): only the target ``field`` (its quotes go to
    ``<field>_sources``), the plausibility ceiling and its rejection wording differ.

    Returns
    -------
    tuple
        ``(written, rejected, owned)``: how many drugs were set, one line per
        rejection, and the ids skipped because ``owned(drug)`` says another pass now
        holds the fact (the fetcher's own skip predicate: a pick judged before that
        pass landed is stale, not wrong, so it is counted apart from the rejections).
    """
    by_id = {d["id"]: d for d in drugs}
    # The stored page a candidate's ``(corpus, page)`` cites, via the corpus registry's
    # ``pages_dir``, so a corpus a worklist offers needs no branch here.
    pages = PageGate(registry_pages())

    written = 0
    rejected: list[str] = []
    skipped: list[str] = []

    def reject(did: str, why: str) -> None:
        rejected.append(f"{did}: {why}")

    for did, rec in judged.items():
        drug = by_id.get(did)
        if not drug:
            reject(did, "not a dataset drug")
            continue
        if (owned and owned(drug)) or F.placed(drug, field):
            skipped.append(did)
            continue
        entry = offered.get(did)
        if not entry:
            reject(did, "the fetcher offers no candidate for this drug")
            continue
        cand, why = resolve(entry["candidates"], rec)
        if why:
            reject(did, f"index {rec.get('index')!r}: {why}")
            continue
        value = clean_value(rec)
        if not value:
            reject(did, "no usable hours in the judged record")
            continue
        if not any(same_duration(value, d) for d in cand["durations"]):
            reject(did, f"{value} is not a duration the quote states "
                        f"({cand['durations']})")
            continue
        if value["hours"] > max_hours:
            reject(did, f"{value['hours']} h {too_long} (> {max_hours} h)")
            continue
        if pages.text(cand["corpus"], cand["page"]) is None:
            reject(did, f"no stored page for {cand['corpus']} {cand['page']!r}")
            continue
        if not pages.on_page(cand["corpus"], cand["page"], cand["line"]):
            reject(did, "the quote is not verbatim on its page")
            continue
        drug[field] = value
        drug[f"{field}_sources"] = [{"corpus": cand["corpus"], "page": cand["page"],
                                     "quote": cand["line"], "provenance": "verified"}]
        written += 1
    return written, rejected, skipped


def run(doc: str, judged_default: Path, build, field: str, max_hours: float,
        too_long: str, owned=None) -> int:
    """The CLI shared by every duration applier (see ``apply_judged``)."""
    ap = argparse.ArgumentParser(description=doc,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judged", type=Path, default=judged_default,
                    help="the LLM-judged file")
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

    judged = worklist_io.read(args.judged)
    offered = build()                                  # gate 2: freshly re-derived
    drugs = drugs_io.load_drugs()
    written, rejected, skipped = apply_judged(judged, offered, drugs, field, max_hours,
                                              too_long, owned)
    tally = (f"{len(rejected)} rejected, {len(skipped)} skipped (another pass owns "
             f"the fact)")
    if args.dry_run:
        print(f"[dry-run] would set {field} on {written} drug(s); {tally}.")
    else:
        drugs_io.save_drugs(drugs)
        print(f"[ok] set {field} on {written} drug(s); {tally}. "
              f"Wrote {drugs_io.DRUGS_PATH.relative_to(ROOT)}.")
    for r in rejected[:40]:
        print(f"  [reject] {r}")
    if len(rejected) > 40:
        print(f"  ... and {len(rejected) - 40} more")
    return 0


def main() -> int:
    return run(__doc__, JUDGED_PATH, fetch_tmax.build, "tmax", MAX_TMAX_HOURS,
               "is not an oral time-to-peak, likely a depot or implant")


if __name__ == "__main__":
    raise SystemExit(main())
