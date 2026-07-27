#!/usr/bin/env python
"""Merge hand-curated quote sources onto the drug bindings no automatic pass could reach.

Why this exists (and why it is hand-curated, unlike every other applier here):
every *mechanical* route to a binding source has already been exhausted. PDSP
(corpus #5) and GtoPdb (corpus #11) have no assay for these compounds at the
granularity the dataset models (PDSP lists "alpha1" and "Muscarinic Acetylcholine
Receptor"; we model alpha1a/b/d and m1-m5), and the Stahl / Wikipedia greppers
(`apply_source_quotes.py`, `fetch_wikipedia_pharmacology.py`) key off regular
constructs these particular pages do not use. What is left is a handful of
one-off prose sentences, each read once by a human, so a curated table plus the
ordinary verbatim gate beats another judge.

Two conventions this table follows, both pre-existing house practice:

- **A coarse sentence backs every modeled subtype it names.** Stahl's
  "Anticholinergic activity may explain ... dry mouth, constipation, and blurred
  vision" sources m1 through m5, exactly as it already does on imipramine; a
  "blockade of alpha adrenergic 1 receptors" line sources alpha1a/b/d, as on
  chlorpromazine. The subtypes are the modeled members of the family the source
  names, not an extrapolation past it.
- **Report a conflict, never resolve it.** Stahl p788 explains sulpiride's dry
  mouth / sedation by muscarinic and histamine blockade; the English Wikipedia
  article says sulpiride has a "lack of alpha1 adrenergic, histamine and
  muscarinic acetylcholine receptor affinity". The Stahl quote is recorded (its
  m1-m5 and alpha1 siblings already carry it) and the disagreement is printed at
  the end of a run rather than silently arbitrated.

Idempotent and never destructive: a binding that already carries `sources` is
left untouched, so a re-run after a `fetch_ki.py --apply` refresh is a no-op.
Every quote is re-gated against the author-side corpus page before it is written,
so a typo cannot land a false `verified` (and on a clone without the page trees
the gate is skipped with a warning, like every other applier here).

Run from the repo root:

    python tools/sourcing/apply_binding_sources.py [--dry-run]
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import drugs_io  # noqa: E402

# check_data.py is a script, not a package module: load it by path (same trick as
# apply_nbn_sources.py) to reuse the *exact* normalizer the quote gate applies, so
# a quote accepted here cannot be rejected by the checker afterwards.
_spec = importlib.util.spec_from_file_location("cd", ROOT / "tools" / "check_data.py")
_cd = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_cd)
normalize_for_match = _cd.normalize_for_match

sys.path.insert(0, str(ROOT / "tools" / "data_generators"))
from provenance import SOURCE_CORPORA  # noqa: E402


def _rows(drug: str, targets: list[str], corpus: str, page: Any, quote: str) -> dict:
    """One curated source fanned out over every modeled subtype it covers."""
    return {(drug, t): {"corpus": corpus, "page": page, "quote": quote,
                        "provenance": "verified"} for t in targets}


# (drug_id, target) -> the source to write. Every quote below was read on the
# cited page; the gate re-confirms it on each run.
BINDING_SOURCES: dict[tuple[str, str], dict] = {
    # Stahl states the release inhibition directly; the modeled target is the
    # glutamate receptor group, and "modulator" is the action already recorded.
    **_rows("carbamazepine", ["glutamate"], "stahl", 147,
            "Inhibits release of glutamate"),

    # The coarse-anticholinergic convention (see the module docstring).
    **_rows("maprotiline", ["m1", "m2", "m3", "m4", "m5"], "stahl", 496,
            "Anticholinergic activity may explain sedative effects, dry mouth, "
            "constipation, and blurred vision"),

    # Stahl's own side-effect line for sulpiride. NOTE the Wikipedia conflict
    # reported at the end of a run: the same drug's article denies this affinity.
    # Recorded because its m1-m5 / alpha1 siblings already cite this same page.
    **_rows("sulpiride", ["h1"], "stahl", 788,
            "Antihistaminic actions may cause sedation, weight gain"),

    # Tropatepine has no Stahl monograph and no PDSP assay; its article's one
    # pharmacological sentence classes the whole drug as an anticholinergic,
    # which is the muscarinic family the dataset models as m1-m5.
    **_rows("tropatepine", ["m1", "m2", "m3", "m4", "m5"], "wikipedia_pharm",
            "tropatepine",
            "Tropatepine (brand name Lepticur ) is an anticholinergic used as an "
            "antiparkinsonian agent."),

    # Prothipendyl: the article names both actions, each in its own sentence.
    # The dopamine line is a hedge ("weaker ... than other phenothiazines"), but
    # it does assert the antagonism, which is what the binding claims.
    **_rows("prothipendyl", ["d2"], "wikipedia_pharm", "prothipendyl",
            "Prothipendyl is said to not possess antipsychotic effects, and in "
            "accordance, appears to be a weaker dopamine receptor antagonist than "
            "other phenothiazines."),
    **_rows("prothipendyl", ["h1"], "wikipedia_pharm", "prothipendyl",
            "is an anxiolytic , antiemetic , and antihistamine of the "
            "azaphenothiazine group"),

    # Chlorprothixene's receptor list is a bulleted block; alpha1 is its last
    # bullet, so the quote has to span from the "is an antagonist of" stem down
    # to it (the lines are contiguous in the page file, so it gates cleanly).
    # Its other subtypes already carry a measured Ki.
    **_rows("chlorprothixene", ["alpha1a", "alpha1b", "alpha1d"],
            "wikipedia_pharm", "chlorprothixene",
            "Chlorprothixene is an antagonist of the following receptors : "
            "- 5-HT 2 , 5-HT 6 , 5-HT 7 : antipsychotic effects, sedation/anxiolysis, "
            "antidepressant effect, weight gain "
            "- D 1 , D 2 , D 3 , D 4 , D 5 : antipsychotic effects, sedation, "
            "extrapyramidal side effects, prolactin increase, depression, "
            "apathy/anhedonia, weight gain "
            "- H 1 : sedation, weight gain "
            "- Muscarinic acetylcholine receptors : anticholinergic effects, "
            "inhibition of extrapyramidal side effects "
            "- α 1 -Adrenergic : hypotension, sedation, anxiolysis"),

    # Levomepromazine's article carries no Ki table; its single pharmacodynamics
    # sentence enumerates the receptor families it blocks. 5-HT2A and alpha1a/b/d
    # are the drug's only modeled members of the serotonin and alpha1 families it
    # names (d2 and h1 already carry a measured Ki).
    **_rows("levomepromazine", ["5ht2a", "alpha1a", "alpha1b", "alpha1d"],
            "wikipedia_pharm", "levomepromazine",
            "levomepromazine is a \" dirty drug \", that is, it exerts its effects "
            "by blocking a variety of receptors , including adrenergic receptors , "
            "dopamine receptors , histamine receptors , muscarinic acetylcholine "
            "receptors and serotonin receptors ."),
}

# Disagreements between corpora, surfaced on every run instead of being resolved
# in the data. (drug_id, note).
CONFLICTS: list[tuple[str, str]] = [
    ("sulpiride",
     "Stahl p788 attributes sedation to antihistaminic action (the source written "
     "onto h1, matching its already-sourced m1-m5 / alpha1 siblings), but the "
     "English Wikipedia article states a \"lack of alpha1 adrenergic, histamine "
     "and muscarinic acetylcholine receptor affinity\". Left as Stahl says it."),
]


def _page_text(corpus: str, page: Any) -> str | None:
    """The author-side page file for a source, or None when the corpus tree is absent."""
    entry = SOURCE_CORPORA.get(corpus)
    if not entry or not entry.get("pages_dir"):
        return None
    md = ROOT / entry["pages_dir"] / f"{page}.md"
    if not md.exists():
        return None
    return md.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing drugs_data.jsonl")
    args = ap.parse_args()

    drugs = drugs_io.load_drugs()
    by_id = {d["id"]: d for d in drugs}

    applied: list[str] = []
    already: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []
    skipped_gate: set[str] = set()

    for (drug_id, target), source in sorted(BINDING_SOURCES.items()):
        label = f"{drug_id} {target}"
        drug = by_id.get(drug_id)
        binding = None
        if drug:
            binding = next((b for b in drug.get("bindings", [])
                            if b.get("target") == target), None)
        if binding is None:
            unknown.append(label)
            continue
        if binding.get("sources"):
            already.append(label)
            continue

        page_text = _page_text(source["corpus"], source["page"])
        if page_text is None:
            skipped_gate.add(source["corpus"])
        elif normalize_for_match(source["quote"]) not in normalize_for_match(page_text):
            failed.append(f"{label}: quote not found on "
                          f"{source['corpus']} {source['page']}")
            continue

        binding["sources"] = [dict(source)]
        applied.append(label)

    print(f"applied {len(applied)}, already sourced {len(already)}, "
          f"gate failures {len(failed)}, unknown bindings {len(unknown)}")
    for line in applied:
        print(f"  + {line}")
    for line in failed:
        print(f"  ! {line}")
    for line in unknown:
        print(f"  ? {line} (no such binding)")
    for corpus in sorted(skipped_gate):
        print(f"  warning: {corpus} pages not on disk, quote gate skipped")
    for drug_id, note in CONFLICTS:
        print(f"  conflict [{drug_id}]: {note}")

    if failed:
        return 1
    if applied and not args.dry_run:
        drugs_io.save_drugs(drugs)
        print(f"wrote {drugs_io.DRUGS_PATH.relative_to(ROOT)}")
    elif args.dry_run:
        print("dry run, nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
