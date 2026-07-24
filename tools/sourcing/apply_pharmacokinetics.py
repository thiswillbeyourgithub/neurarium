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

Overwrite semantics (idempotent): this is the sole writer of these two fields, so a
re-run replaces a drug's ``half_life`` / ``metabolites`` from the current judged file
rather than accumulating; a judged drug with no surviving metabolite has any prior
``metabolites`` cleared. A drug absent from the judged file is left untouched.

Usage (from the repo root): python tools/sourcing/apply_pharmacokinetics.py [--dry-run]
Stdlib only; author-side (needs the gitignored data_sources/books/stahl/pages tree; on
a clone that lacks it the quote gate cannot run, so the applier refuses rather than
writing ungated quotes).
"""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent           # repo root
sys.path.insert(0, str(ROOT / "tools"))
import drugs_io                                                 # noqa: E402

STAHL_PAGES = ROOT / "data_sources" / "books" / "stahl" / "pages"
JUDGED_PATH = ROOT / "tools" / "generated_cache" / "pk_judged.json"

# Reuse check_data's canonical quote-gate normalization (single source of truth), so
# a quote that passes here also passes check_data's later re-gate.
_spec = importlib.util.spec_from_file_location("cd", ROOT / "tools" / "check_data.py")
_cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cd)
normalize_for_match = _cd.normalize_for_match


def norm_name(s: str) -> str:
    """Fold a name for drug-id matching (lowercase, alphanumerics only)."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


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


def stahl_source(page: int, quote: str) -> dict:
    """Build a ``verified`` Stahl quote source node for a page + verbatim quote."""
    return {"corpus": "stahl", "page": int(page), "quote": quote,
            "provenance": "verified"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--judged", type=Path, default=JUDGED_PATH,
                    help="the LLM-judged pharmacokinetics file")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing drugs_data.jsonl")
    args = ap.parse_args()

    if not STAHL_PAGES.exists():
        print(f"[error] {STAHL_PAGES} absent (author-side Stahl tree missing); the "
              f"quote gate cannot run, refusing to write ungated quotes.",
              file=sys.stderr)
        return 1
    if not args.judged.exists():
        print(f"[error] judged file {args.judged} not found; run the LLM pass first.",
              file=sys.stderr)
        return 1

    judged = json.loads(args.judged.read_text(encoding="utf-8"))
    drugs = drugs_io.load_drugs()
    by_id = {d["id"]: d for d in drugs}
    drug_norm_to_id = {norm_name(d["name"]): d["id"] for d in drugs}

    page_cache: dict[int, str] = {}

    def page_text(page) -> str:
        """Normalized text of a Stahl page (cached); "" if the page file is absent."""
        try:
            page = int(page)
        except (TypeError, ValueError):
            return ""
        if page not in page_cache:
            p = STAHL_PAGES / f"{page}.md"
            page_cache[page] = (normalize_for_match(p.read_text(encoding="utf-8"))
                                if p.exists() else "")
        return page_cache[page]

    def gated(page, quote) -> bool:
        """Whether ``quote`` appears verbatim (normalized) on Stahl ``page``."""
        if not quote or page is None:
            return False
        return normalize_for_match(quote) in page_text(page)

    n_hl = n_met = dropped = 0
    warnings: list[str] = []
    for did, rec in judged.items():
        drug = by_id.get(did)
        if not drug:
            warnings.append(f"judged drug {did!r} not in dataset; skipped")
            continue

        # --- Parent elimination half-life ---------------------------------------
        hl = rec.get("half_life")
        if hl:
            value = clean_half_life(hl)
            if value and gated(hl.get("page"), hl.get("quote")):
                drug["half_life"] = value
                drug["half_life_sources"] = [stahl_source(hl["page"], hl["quote"])]
                n_hl += 1
            else:
                dropped += 1
                warnings.append(f"{did}: half-life quote failed the gate, dropped")

        # --- Active metabolites --------------------------------------------------
        mets: list[dict] = []
        seen: set[str] = set()
        for m in rec.get("metabolites", []) or []:
            name = (m.get("name") or "").strip()
            key = norm_name(name)
            if not name or key in seen:
                continue
            if not gated(m.get("page"), m.get("quote")):
                dropped += 1
                warnings.append(f"{did}: metabolite {name!r} quote failed the gate")
                continue
            seen.add(key)
            mrec: dict = {"name": name}
            # Link a metabolite that is itself a modeled drug (never the parent
            # itself), so the viewer reuses its bindings + T½ and jumps to it.
            linked = drug_norm_to_id.get(key)
            if linked and linked != did:
                mrec["drug_id"] = linked
            mhl = m.get("half_life")
            if mhl:
                mvalue = clean_half_life(mhl)
                if mvalue and gated(mhl.get("page"), mhl.get("quote")):
                    mrec["half_life"] = mvalue
                    mrec["half_life_sources"] = [
                        stahl_source(mhl["page"], mhl["quote"])]
            mrec["sources"] = [stahl_source(m["page"], m["quote"])]
            mets.append(mrec)
            n_met += 1
        if mets:
            drug["metabolites"] = mets
        elif "metabolites" in drug:
            # Idempotent: judged says none survived -> clear a prior run's list.
            del drug["metabolites"]

    if args.dry_run:
        print(f"[dry-run] would set half_life on {n_hl} drugs, "
              f"{n_met} metabolites; {dropped} quotes dropped.")
    else:
        drugs_io.save_drugs(drugs)
        print(f"[ok] set half_life on {n_hl} drugs, {n_met} metabolites; "
              f"{dropped} quotes dropped. Wrote {drugs_io.DRUGS_PATH.relative_to(ROOT)}.")
    for w in warnings[:40]:
        print(f"  [warn] {w}")
    if len(warnings) > 40:
        print(f"  ... and {len(warnings) - 40} more warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
