#!/usr/bin/env python
"""Apply the judged Stahl pharmacokinetics (T½ + active metabolites) to the drugs.

Second half of the pipeline started by ``tools/fetch/fetch_pharmacokinetics.py``: the
fetch pass wrote a worklist of candidate half-life / metabolite lines, an LLM read it
into ``tools/generated_cache/pk_judged.json`` (per drug: the parent elimination T½ and
the named active metabolites, each with a verbatim Stahl quote + page). This applier,
for each judged drug:

* **quote-gates** every returned quote: it must appear verbatim (under check_data's
  normalization) on the cited ``data_sources/books/stahl/pages/<page>.md`` page, so an
  LLM paraphrase or hallucination is dropped here, not written;
* writes the drug's ``half_life`` (``{hours, hours_max?}``) + a ``verified``
  ``half_life_sources`` quote node; and
* writes ``metabolites`` (one identity node each, ``{name, drug_id?, half_life?,
  half_life_sources?, sources}``), resolving ``drug_id`` when the metabolite's name
  matches a modeled drug (so the viewer can link + reuse its bindings), and attaching
  the metabolite's own T½ when Stahl states it.

Merge semantics (idempotent): a judged metabolite updates the same-named existing
record, keeping the fields other passes own (``bindings`` from
``apply_metabolite_bindings.py``, a prodrug's metabolite from ``apply_prodrug.py``), and a
metabolite the judged file does not name is left alone. A judged quote may cite
``"corpus": "wikipedia_pharm"`` (``page`` = article slug) where Stahl is silent, and an
explicit ``"drug_id"`` links a metabolite known under a synonym (ODV = desvenlafaxine).
``"half_life": null`` clears a T½ the source states for someone else (a prodrug's figure
that is its metabolite's, an IV-only figure), so the by-index half-life pass can re-pick.
Later passes re-picked some drugs' T½, so scope a run with ``--only <ids>``.

Usage (from the repo root): python tools/sourcing/apply_pharmacokinetics.py [--dry-run]
Stdlib only; author-side (needs the gitignored data_sources/books/stahl/pages tree; on
a clone that lacks it the quote gate cannot run, so the applier refuses rather than
writing ungated quotes).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
sys.path.insert(0, str(ROOT / "tools"))
from lib import drugs_io                                                 # noqa: E402
from lib import worklist_io  # noqa: E402 (the one judged / worklist reader)

# The corpora a judged quote may cite (``corpus`` defaults to ``stahl``): Stahl's
# monograph prose, then the drug's (or the metabolite's) own English Wikipedia article.
PAGES = {"stahl": ROOT / "data_sources" / "books" / "stahl" / "pages",
         "wikipedia_pharm": ROOT / "data_sources" / "wikipedia" / "pages"}
JUDGED_PATH = ROOT / "tools" / "generated_cache" / "pk_judged.json"

sys.path.insert(0, str(ROOT / "tools" / "sourcing"))
from pipeline.gate import PageGate  # noqa: E402 (the applier's page gate)


norm_name = drugs_io._fold          # one name fold (lowercase, alphanumerics only)


def clean_half_life(hl: dict | None) -> dict | None:
    """Return a validated ``{hours, hours_max?}`` (floats) or None if unusable."""
    if not isinstance(hl, dict):
        return None
    try:
        hours = float(hl.get("hours"))
    except (TypeError, ValueError):
        return None
    if hours <= 0:
        return None
    rec = {"hours": hours}
    hi = hl.get("hours_max")
    if hi is not None:
        try:
            hi = float(hi)
        except (TypeError, ValueError):
            hi = None
        if hi is not None and hi >= hours:
            rec["hours_max"] = hi
    return rec


def source(q: dict) -> dict:
    """A ``verified`` quote source node from a judged ``{corpus?, page, quote}``."""
    corpus = q.get("corpus") or "stahl"
    page = int(q["page"]) if corpus == "stahl" else q["page"]
    return {"corpus": corpus, "page": page, "quote": q["quote"],
            "provenance": "verified"}


def apply(judged: dict, drugs: list[dict], pages: PageGate,
          only: set[str] | None = None,
          metabolites: list[dict] | None = None) -> tuple[int, int, list[str]]:
    """Merge the judged T½ + metabolites onto ``drugs`` + the ``metabolites`` store;
    return (n_hl, n_met, warnings).

    Merge, not overwrite: a judged metabolite resolves to the store record that shares a
    name with it (:func:`drugs_io.find_metabolite`, so ``"Desmethyldiazepam (nordazepam)"``
    matches ``"Nordazepam"``), whose name, ``bindings`` and links other passes own; the
    molecule's T½ goes on that record, the "is a metabolite of <drug>" quote on the
    drug's reference. A metabolite the judged file does not name is left alone. Explicit
    ``"half_life": null`` clears a T½ (the parent's, or a metabolite's) the source
    states for someone else, e.g. a prodrug's figure that is its metabolite's.
    """
    metabolites = [] if metabolites is None else metabolites
    by_id = {d["id"]: d for d in drugs}
    drug_norm_to_id = {norm_name(d["name"]): d["id"] for d in drugs}
    warnings: list[str] = []

    def gated(q) -> bool:
        """Whether ``q``'s quote is verbatim on its (allowed) corpus page."""
        if not isinstance(q, dict) or not q.get("quote") or q.get("page") is None:
            return False
        corpus = q.get("corpus") or "stahl"
        return corpus in PAGES and pages.on_page(corpus, q["page"], q["quote"])

    def set_half_life(rec: dict, owner: dict, label: str) -> int:
        """Apply ``rec["half_life"]`` (gated dict, or explicit None) onto ``owner``."""
        if "half_life" not in rec:
            return 0
        hl = rec["half_life"]
        if hl is None:
            owner.pop("half_life", None)
            owner.pop("half_life_sources", None)
            return 0
        value = clean_half_life(hl)
        if value and gated(hl):
            owner["half_life"] = value
            owner["half_life_sources"] = [source(hl)]
            return 1
        warnings.append(f"{label}: half-life quote failed the gate, dropped")
        return 0

    n_hl = n_met = 0
    for did, rec in judged.items():
        if only is not None and did not in only:
            continue
        drug = by_id.get(did)
        if not drug:
            warnings.append(f"judged drug {did!r} not in dataset; skipped")
            continue
        n_hl += set_half_life(rec, drug, did)
        mets = drug.setdefault("metabolites", [])
        for m in rec.get("metabolites", []) or []:
            name = (m.get("name") or "").strip()
            # A quote-less entry only re-dates an existing metabolite (its T½), keeping
            # the identity source another pass wrote (a prodrug's metabolite).
            has_quote = bool(m.get("quote"))
            if not name or (has_quote and not gated(m)):
                warnings.append(f"{did}: metabolite {name!r} quote failed the gate")
                continue
            known = drugs_io.find_metabolite(metabolites, name)
            listed = known is not None and any(r["id"] == known["id"] for r in mets)
            if not listed and not has_quote:
                warnings.append(f"{did}: new metabolite {name!r} has no quote")
                continue
            ref, mrec = drugs_io.attach_metabolite(drug, metabolites, name)
            # Link a metabolite that is itself a modeled drug (never the parent itself),
            # so the viewer reuses its bindings + T½ and jumps to it. An explicit
            # ``drug_id`` covers a synonym the name match cannot see (ODV = desvenlafaxine).
            linked = m.get("drug_id") or drug_norm_to_id.get(norm_name(name))
            if m.get("drug_id") and linked not in by_id:
                warnings.append(f"{did}: metabolite {name!r} drug_id {linked!r} unknown")
                linked = None
            if linked and linked != did:
                mrec["drug_id"] = linked
            set_half_life(m, mrec, f"{did}/{name}")
            if has_quote:
                ref["sources"] = [source(m)]
            n_met += 1
        if not mets:
            del drug["metabolites"]
    return n_hl, n_met, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--judged", type=Path, default=JUDGED_PATH,
                    help="the LLM-judged pharmacokinetics file")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing drugs_data.jsonl")
    ap.add_argument("--only", help="comma-separated drug ids to apply (the judged file "
                    "predates later passes that re-picked some drugs' T½, so a full "
                    "re-run is not a no-op)")
    args = ap.parse_args()
    only = {d.strip() for d in args.only.split(",") if d.strip()} if args.only else None

    missing = [str(p) for p in PAGES.values() if not p.exists()]
    if missing:
        print(f"[error] {', '.join(missing)} absent (author-side corpus tree missing); the "
              f"quote gate cannot run, refusing to write ungated quotes.",
              file=sys.stderr)
        return 1
    if not args.judged.exists():
        print(f"[error] judged file {args.judged} not found; run the LLM pass first.",
              file=sys.stderr)
        return 1

    judged = worklist_io.read(args.judged)
    drugs = drugs_io.load_drugs()
    metabolites = drugs_io.load_metabolites()
    n_hl, n_met, warnings = apply(judged, drugs, PageGate(PAGES), only, metabolites)
    if args.dry_run:
        print(f"[dry-run] would set half_life on {n_hl} drugs, {n_met} metabolites; "
              f"{len(warnings)} quotes dropped.")
    else:
        drugs_io.save_drugs(drugs)
        drugs_io.save_metabolites(metabolites)
        print(f"[ok] set half_life on {n_hl} drugs, {n_met} metabolites; "
              f"{len(warnings)} quotes dropped. Wrote {drugs_io.DRUGS_PATH.relative_to(ROOT)}.")
    for w in warnings[:40]:
        print(f"  [warn] {w}")
    if len(warnings) > 40:
        print(f"  ... and {len(warnings) - 40} more warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
