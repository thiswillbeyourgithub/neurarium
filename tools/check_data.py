#!/usr/bin/env python
"""Integrity checks over the emitted dataset (``public/data/``).

This validates the committed data files that the static site actually serves
(``meta.json`` + ``structures`` / ``projections`` / ``circuits`` / ``receptors``
/ ``drugs`` ``.jsonl``), independently of ``generate_data.py``. The generator
already raises on most of these at build time; running the same checks over the
*emitted* artifacts is a cheap regression guard that also catches generator/data
drift and the duplicate/TODO classes the generator does not look for.

Run it directly (stdlib only, no deps, like ``generate_data.py``):

    python tools/check_data.py

Exit status is ``0`` when there are no errors (warnings are allowed) and ``1``
when any error is found, so it is usable as a gate (see the pre-push hook in
``tools/git-hooks/``).

Fourteen families of checks, numbered 0 to 13 as the report headers print them
(each family lives in its own ``tools/checks/`` module, whose ``check_*`` docstring
holds the detail; this file is only the CLI that loads the data and runs them in order):

0. **Quote table** (``check_quotes``). Every ``quote_id`` resolves, none is orphaned.

1. **Duplicates** (per collection). An exact duplicate id/key, or two ids that
   collide once **normalized** (lowercased, every non-alphanumeric character
   stripped: ``mao_a`` and ``mao-a`` -> ``maoa``), is an **error**. Two entries
   whose **display names** collide once normalized is a **warning** (a likely
   accidental re-entry to eyeball, but occasionally legitimate). Projections have
   no id, so they are checked for duplicate ``from -> to`` endpoints instead.

2. **Reachability** (referential integrity). Every cross-reference must resolve
   or the detail is **unreachable** in the viewer. The canonical case: a drug
   binding whose ``target`` is not a key of ``meta.drug_targets`` can never be
   focused from its panel. This also covers every receptor ``location`` / target
   ``region``: it must name a structure **base** present in the atlas, otherwise
   its "Found in" row in the panel would point at nothing and so be **unclickable**.
   All dangling references are **errors**.

3. **TODOs**. A literal ``"TODO"`` placeholder anywhere **outside** a source url
   (e.g. a binding ``note`` left as TODO), plus any focusable target with no
   ``wikipedia`` (the viewer shows a NOSOURCE pill), is a **warning**. A source
   *url* left as ``"TODO"`` is handled **provenance-aware**: the viewer surfaces a
   source's tiered grade (the pill), never its url, so a missing link on an ``llm``
   citation is the expected "no free link yet" state (reported as an ``[ok]``
   count, not a warning); only a source that *claims* a higher grade
   (``sourced`` / ``verified``) yet still has a ``TODO`` url is **warned** (an
   inconsistency: it asserts more than its link backs).

4. **Provenance grades**. Every emitted source (a ``sources[].provenance``,
   including the per-binding drug sources) and every wikipedia reference (a
   ``wikipedia_provenance`` beside a ``wikipedia``) must carry a known grade
   (``llm`` / ``sourced`` / ``verified``), the value the viewer renders as a
   grey/yellow/green pill. An unknown or missing grade is an **error** (the pill
   would fall back to "no source" and mislead). An UNKNOWN stamp (``unknown`` on a
   binding, data_generators/unknown.py) is an **error** on a binding that states a
   direction, or when its search skipped a corpus ``UNKNOWN_REQUIRED_SOURCES`` lists.

5. **Source quotes**. Each per-binding drug source is
   ``{corpus, page, quote, provenance}``; a ``"verified"`` grade is the one that
   claims the quote was confirmed present in the source. This re-confirms it: the
   ``corpus`` must resolve to ``meta.source_corpora``, a verified source must
   carry a page + quote, and the **normalized** quote must be an exact substring
   of the **normalized** cited page text (``<pages_dir>/<page>.md``). The page
   material is author-side and may be absent on a clone (see ``data_sources/books/stahl/`` in
   CLAUDE.local.md); the quote-in-page check is then **skipped with a warning**
   while the structural checks still run. A quote that is genuinely not on its
   page (an invented or mistyped extraction) is an **error**, so this is the gate
   that keeps the LLM extraction honest.

6. **Structure connectivity**. Warns (never errors) about a structure the
   connectome leaves stranded or one-sided: **isolated** (no projection touches
   it), **inward-only** (receives but never projects out), or **outward-only**
   (projects out but never receives, e.g. the modeled ascending source nuclei).
   An eyeball list for the author, not a gate.

7. **Measured-affinity (Ki) coverage**. Warns (never errors) per drug that carries
   bindings but no measured PDSP Ki on any of them, and re-confirms the shipped
   ``meta.provenance_stats.ki_coverage`` figure against a recompute. The honest
   complement to "% sourced": where a measured affinity was never looked up.

8. **Drug flow vs. binding consistency**. Warns (never errors) where a drug's
   by-mechanism flow overlay and its own receptor bindings tell opposite stories:
   the modeled flow raises a system's tone while the drug's postsynaptic receptors
   on that system net-block (or the reverse), and where it boosts a system's flow
   *into* a region whose receptors it strongly blocks. Ports the viewer's flow
   model so it reasons about the same numbers; an eyeball list (most flags are the
   intended presynaptic-tone vs. postsynaptic-block split), not a gate.

9. **Changelog** (``check_changelog``). ``version.js`` has its release notes.
10. **Innervation coverage** (``check_innervation``). Warns per transmitter system.
11. **Baked meshes** (``check_baked_meshes``). The SDF bake matches its shapes.
12. **Enzyme variability** (``check_enzyme_variability``). Re-derived from the
    pinned PharmFreq tables.
13. **Freshness** (``check_freshness``). An editable online corpus page cited but
    downloaded too long ago fails, and so does an UNKNOWN search that old.

Built with the help of Claude Code.
"""

import sys

# The curated contradictions, keyed by citation site and resolved through the one site
# grammar (tools/sourcing/citation_site.py), exactly as the generator applies them.
from data_generators.quotes.contradictions import CONTRADICTIONS

from checks.baked_meshes import check_baked_meshes
from checks.changelog import check_changelog
from checks.clinpgx_variants import check_clinpgx_variants
from checks.common import DATA_DIR, Report, expand_mirrored, load_jsonl, load_meta
from checks.connectivity import check_connectivity
from checks.duplicates import check_duplicates
from checks.enzyme_variability import check_enzyme_variability
from checks.flow import check_flow_consistency
from checks.freshness import check_freshness
from checks.innervation import check_innervation
from checks.ki_coverage import check_ki_coverage
from checks.provenance import check_provenance
from checks.quotes import check_quotes, load_quotes, rehydrate_quotes
from checks.reachability import check_reachability
from checks.sources import check_sources
from checks.todos import check_todos


def main():
    argv = sys.argv[1:]
    verbose = "--verbose" in argv
    argv = [a for a in argv if a != "--verbose"]
    only = argv == ["--only", "freshness"]
    if argv and not only:
        print("usage: check_data.py [--verbose] [--only freshness]", file=sys.stderr)
        return 2
    report = Report(verbose=verbose)
    print(f"neurarium data integrity check\nreading {DATA_DIR}")

    meta = load_meta(report)
    structures = load_jsonl(report, "structures")
    projections = expand_mirrored(load_jsonl(report, "projections"))
    circuits = load_jsonl(report, "circuits")
    projection_groups = load_jsonl(report, "projection_groups")
    receptors = load_jsonl(report, "receptors")
    drugs = load_jsonl(report, "drugs")
    metabolites = load_jsonl(report, "metabolites")
    addons = load_jsonl(report, "addons")

    # Rehydrate the externalized source quotes in place (collecting referenced +
    # dangling ids), so every check below sees the original inline source shape;
    # then report the quote table's referential integrity.
    quotes_by_id = load_quotes(report)
    referenced, dangling = set(), []
    rehydrate_quotes([meta, structures, projections, circuits, projection_groups,
                      receptors, drugs, metabolites, addons], quotes_by_id, referenced,
                     dangling)
    check_quotes(report, quotes_by_id, referenced, dangling)
    collections = [meta, structures, projections, circuits, projection_groups,
                   receptors, drugs, metabolites, addons]
    if only:
        check_freshness(report, meta, collections, metabolites=metabolites,
                        receptors=receptors)
        return _summary(report)

    args = (report, meta, structures, projections, circuits, projection_groups,
            receptors, drugs)
    check_duplicates(*args, metabolites)
    check_reachability(*args, addons, metabolites)
    check_todos(*args)
    check_provenance(*args, addons, metabolites)
    check_sources(report, meta, drugs, projections, structures, receptors, addons,
                  metabolites, circuits, projection_groups, CONTRADICTIONS)
    check_connectivity(report, structures, projections)
    check_ki_coverage(report, meta, drugs)
    check_flow_consistency(report, meta, drugs, projections, receptors)
    check_changelog(report)
    check_innervation(report, meta, structures, projections, receptors)
    check_baked_meshes(report, structures)
    check_enzyme_variability(report, meta, drugs)
    check_clinpgx_variants(report, meta, receptors)
    check_freshness(report, meta, collections, metabolites=metabolites,
                        receptors=receptors)
    return _summary(report)


def _summary(report):
    print(f"\nSummary: {report.errors} error(s), {report.warnings} warning(s)")
    if report.reviews and not report.verbose:
        print(f"         {report.reviews} review item(s) not listed "
              f"(intended-by-design eyeball lists; --verbose prints them)")
    if report.errors:
        print("FAILED: fix the errors above (warnings are informational).")
        return 1
    print("PASSED (warnings are informational).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
