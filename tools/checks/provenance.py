"""Family 4: source provenance grades + the coverage tally.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import re
from collections import Counter

from data_generators import unknown
from data_generators.node_kinds import NODE_KINDS, backed
from data_generators.provenance_stats import own_targets

from .walks import iter_drug_sources, unknown_stamps


# Valid source provenance grades (mirrors generate_data.py PROVENANCE_LEVELS), the
# value the viewer renders as the grey/yellow/green source pill.
_PROVENANCE_LEVELS = {"llm", "sourced", "verified"}

# The knowledge-node kinds folded into the headline coverage are NODE_KINDS, imported
# from data_generators/node_kinds.py (the one roster).
# ``drug_binding_action`` is graded from the bindings' own quote sources, so its quotes
# are already walked as part of drug_bindings / drug_metabolite_bindings: the kind adds a
# tally column, never a new quote to gate.


def print_coverage(stats):
    """Print the per-kind, per-tier sourcing tally over the dataset's **nodes** (the
    same numbers the About panel + README headline read from
    ``meta.provenance_stats``), so the pre-push output shows at a glance exactly how
    many nodes sit at each provenance grade.

    A *node* is any sourceable datum (see the Nodes section of CLAUDE.md). Each node
    is reduced to its single strongest grade first, so the columns partition the node
    count (they sum to ``total``); the grades map to the viewer's pills: verified =
    green check, sourced = yellow ``~``, missing = grey ``?`` (an unbacked ``llm``
    assertion) / orange NOSOURCE (no source at all). ``references`` (wikipedia
    pointers) are a kind of their own, tallied but not folded into the headline (a
    reference points *at* a node, it is not itself one), so they are printed below the
    node total."""
    by = stats.get("by_kind", {})
    a = stats.get("nodes", {})
    node_kinds = NODE_KINDS

    def backed_pct(c):
        total = c.get("total", 0)
        return round(100 * backed(c) / total) if total else 0

    def row(label, c, pct=None, suffix=""):
        pct = backed_pct(c) if pct is None else pct
        m = c.get("missing", 0)
        s = c.get("sourced", 0)
        u = c.get("uncertain", 0)
        sv = backed(c)  # sourced-or-verified-or-uncertain = the backed count
        print(f"    {label:<19}{m:>6}{s:>6}{u:>6}{sv:>6}"
              f"{c.get('total', 0):>8}{pct:>7}%{suffix}")

    # Grade columns: M = missing (no source document: a bare llm assertion, or nothing
    # at all), S = sourced (document-backed but not quote-checked), U = uncertain
    # (quote-checked, but the quote does not attribute the claim), S+V = the backed
    # count (S and U are both subsets of it). S is ~always 0 on the node kinds because
    # the sourcing pipeline goes straight from llm to quote-verified; it shows up only
    # on Wikipedia refs.
    print("\n  node coverage by kind (each node reduced to its strongest grade;")
    print("  M=missing  S=sourced  U=uncertain  S+V=backed):")
    print(f"    {'kind':<19}{'M':>6}{'S':>6}{'U':>6}{'S+V':>6}{'total':>8}{'backed':>8}")
    for kind in node_kinds:
        row(kind, by.get(kind, {}))
    print(f"    {'-' * 53}")
    row("all nodes", a, pct=a.get("pct_backed", 0))
    if a.get("unknown"):
        print(f"    + {a['unknown']} UNKNOWN (searched, no source states it; "
              f"outside the total)")
    if by.get("references"):
        row("references", by["references"], suffix="   (pointers, not in headline)")


def check_provenance(report, meta, structures, projections, circuits,
                     projection_groups, receptors, drugs, addons, metabolites=()):
    report.header("4. Source provenance grades")
    before = report.errors
    counts = Counter()

    def grade(value, ctx):
        if value not in _PROVENANCE_LEVELS:
            report.error(f"{ctx}: provenance {value!r} is not one of "
                         f"{sorted(_PROVENANCE_LEVELS)}")
        else:
            counts[value] += 1

    def rec_id(label, record):
        if label == "projection":
            return f"{record.get('from')}->{record.get('to')}"
        return record.get("id")

    # Citation sources (projections + drugs + circuits + projection groups) each
    # carry a per-source grade.
    for label, items in (("projection", projections), ("drug", drugs),
                         ("circuit", circuits),
                         ("projection group", projection_groups)):
        for record in items:
            for i, src in enumerate(record.get("sources", []) or []):
                grade(src.get("provenance"),
                      f"{label} {rec_id(label, record)} sources[{i}]")

    # Projection-group classification (the grouping/description grade) + its
    # wikipedia reference each carry a grade, like a receptor / target.
    for group in projection_groups:
        if "classification_provenance" in group:
            grade(group.get("classification_provenance"),
                  f"projection group {group.get('id')} classification_provenance")
        if group.get("wikipedia"):
            grade(group.get("wikipedia_provenance"),
                  f"projection group {group.get('id')} wikipedia")
    # A circuit's optional wikipedia reference likewise carries a grade.
    for circuit in circuits:
        if circuit.get("wikipedia"):
            grade(circuit.get("wikipedia_provenance"),
                  f"circuit {circuit.get('id')} wikipedia")

    # Per-binding drug sources (the quote-level provenance) each carry a grade too,
    # as does a drug's nbn_sources (the NbN is quote-sourced the same way).
    for drug in drugs:
        for ctx, src, _short, _facet, _owner in iter_drug_sources(drug):
            grade(src.get("provenance"), ctx)
        # A drug's class classification carries its own grade (default llm).
        if drug.get("category_provenance"):
            grade(drug.get("category_provenance"),
                  f"drug {drug.get('id')} category_provenance")
        # A drug's description carries its own grade (llm synthesis vs sourced WP lead).
        if drug.get("description"):
            grade(drug.get("description_provenance"),
                  f"drug {drug.get('id')} description_provenance")

    # A metabolite's own facts, once per molecule (metabolites.jsonl).
    for m in metabolites:
        mid = f"metabolite {m.get('id')}"
        for i, src in enumerate(m.get("half_life_sources", []) or []):
            grade(src.get("provenance"), f"{mid} half_life_sources[{i}]")
        for binding in m.get("bindings", []) or []:
            for i, src in enumerate(binding.get("sources", []) or []):
                grade(src.get("provenance"),
                      f"{mid} binding {binding.get('target')} sources[{i}]")

    # Each receptor / structure classification claim and each non-receptor target
    # classification carries a source grade (the panel's "Source" pill), counted in
    # the coverage tally like a binding / projection.
    for receptor in receptors:
        # Each classification attribute (family / receptor_class / sign / synaptic)
        # is its own graded sub-claim, so a wrong/unsourced GPCR or sign shows
        # honestly instead of borrowing a neighbour attribute's quote grade.
        for attr, entry in (receptor.get("classification") or {}).items():
            grade(entry.get("grade"),
                  f"receptor {receptor.get('id')} classification[{attr}]")
            for i, src in enumerate(entry.get("sources") or []):
                grade(src.get("provenance"),
                      f"receptor {receptor.get('id')} classification[{attr}] sources[{i}]")
        # Per-region expression sources (the "Found in" grading): each carries a grade.
        for base, srcs in (receptor.get("location_sources") or {}).items():
            for i, src in enumerate(srcs or []):
                grade(src.get("provenance"),
                      f"receptor {receptor.get('id')} location_sources[{base}][{i}]")
    for structure in structures:
        if "classification_provenance" in structure:
            grade(structure.get("classification_provenance"),
                  f"structure {structure.get('id')} classification_provenance")
    own = own_targets(meta.get("drug_targets", {}))
    for key, target in meta.get("drug_targets", {}).items():
        if key in own and "classification_provenance" in target:
            grade(target.get("classification_provenance"),
                  f"target {key} classification_provenance")
        # Tone-polarity sub-claim (kind target_polarity): its own grade + optional
        # quote source, distinct from the type/system classification above.
        if "polarity_provenance" in target:
            grade(target.get("polarity_provenance"),
                  f"target {key} polarity_provenance")
            for i, src in enumerate(target.get("polarity_sources") or []):
                grade(src.get("provenance"),
                      f"target {key} polarity_sources[{i}]")
        # Per-region expression sources (the target's "Found in" grading), mirror of
        # the receptor location_sources above; each carries a grade.
        for base, srcs in (target.get("location_sources") or {}).items():
            for i, src in enumerate(srcs or []):
                grade(src.get("provenance"),
                      f"target {key} location_sources[{base}][{i}]")

    # Addon nodes are graded through their quote-level sources like a binding.
    for addon in addons:
        for i, src in enumerate(addon.get("sources", []) or []):
            grade(src.get("provenance"), f"addon {addon.get('id')} sources[{i}]")

    # Wikipedia references (structures / receptors / drugs, + the meta targets)
    # carry a sibling `wikipedia_provenance` whenever the link is present.
    for label, items in (("structure", structures), ("receptor", receptors),
                         ("drug", drugs)):
        for record in items:
            if record.get("wikipedia"):
                grade(record.get("wikipedia_provenance"),
                      f"{label} {record.get('id')} wikipedia")
    for key, target in meta.get("drug_targets", {}).items():
        if target.get("wikipedia"):
            grade(target.get("wikipedia_provenance"), f"target {key} wikipedia")

    # UNKNOWN stamps (data_generators/unknown.py): only on a claim still unsourced, and
    # only after a search that covered every corpus its kind requires.
    n_unknown = 0
    for where, kind, claim, stamp in unknown_stamps(drugs, metabolites, receptors, meta):
        n_unknown += 1
        if kind == "drug_binding_action" and (
                claim.get("action") or not claim.get("affinity_only")):
            report.error(f"{where}: UNKNOWN stamped on a binding that states a direction "
                         f"(a real source wins)")
        if kind == "receptor_effect" and claim.get("effects"):
            report.error(f"{where}: UNKNOWN stamped on an owner that carries a sourced "
                         f"effect (a real source wins)")
        missing = unknown.missing_required(kind, stamp.get("corpora") or [])
        if missing:
            report.error(f"{where}: UNKNOWN search skipped required source(s) "
                         f"{', '.join(missing)}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(stamp.get("searched"))):
            report.error(f"{where}: UNKNOWN stamp has no YYYY-MM-DD search date")

    if report.errors == before:
        summary = ", ".join(f"{counts[lvl]} {lvl}"
                            for lvl in sorted(_PROVENANCE_LEVELS) if counts[lvl])
        if n_unknown:
            summary += f"; {n_unknown} UNKNOWN stamp(s), each fully searched"
        report.ok(f"every source/reference carries a valid provenance grade "
                  f"({summary})")

    # Internal consistency of the emitted provenance_stats tally (the figure the
    # About panel + README headline read). Re-deriving the counts would duplicate
    # the generator; this just confirms the emitted buckets are self-consistent, so
    # a malformed emit or a hand-edited stat can never ship a wrong "% sourced".
    stats = meta.get("provenance_stats")
    if not stats:
        report.warn("meta.provenance_stats is missing (the % sourced figure)")
    else:
        before_stats = report.errors
        for kind, c in stats.get("by_kind", {}).items():
            parts = (c.get("verified", 0) + c.get("uncertain", 0)
                     + c.get("sourced", 0) + c.get("missing", 0))
            if parts != c.get("total", 0):
                report.error(f"provenance_stats by_kind[{kind}] buckets "
                             f"({parts}) do not sum to total ({c.get('total')})")
        a = stats.get("nodes", {})
        node_kinds = NODE_KINDS
        by = stats.get("by_kind", {})
        for key in ("total", "verified", "uncertain", "sourced", "missing", "unknown"):
            want = sum(by.get(k, {}).get(key, 0) for k in node_kinds)
            if a.get(key) != want:
                report.error(f"provenance_stats nodes[{key}]={a.get(key)} "
                             f"!= sum over node kinds ({want})")
        n_backed = backed(a)
        if a.get("backed") != n_backed:
            report.error(f"provenance_stats nodes.backed={a.get('backed')} "
                         f"!= verified+uncertain+sourced ({n_backed})")
        want_pct = round(100 * n_backed / a["total"]) if a.get("total") else 0
        if a.get("pct_backed") != want_pct:
            report.error(f"provenance_stats nodes.pct_backed="
                         f"{a.get('pct_backed')} != {want_pct}")
        if report.errors == before_stats:
            report.ok(f"provenance_stats is self-consistent "
                      f"({a.get('pct_backed')}% of {a.get('total')} nodes "
                      f"sourced or verified)")
        print_coverage(stats)
