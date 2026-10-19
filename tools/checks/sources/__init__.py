"""Family 5: every quote-level source is present verbatim in the page it cites.

``check_sources`` is a dispatcher: the shared per-source gate is ``gate.QuoteGate``
and each node kind has its own walk module, run in a fixed order (the report's
message order is part of the output).

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

from .anatomy import walk_addons, walk_projections, walk_structures
from .contradictions import check_contradictions
from .drugs import walk_drugs, walk_enzymes, walk_metabolites
from .gate import QuoteGate
from .headings import check_heading_shapes
from .ki import KiGate, check_ki_rows
from .receptors import walk_receptors, walk_targets
from .stahl import check_stahl_monographs
from .sweep import sweep_committed_caches, sweep_quote_table


def check_sources(report, meta, drugs, projections, structures, receptors, addons,
                  metabolites=(), circuits=(), groups=(), contradictions=(), quotes_by_id=None):
    """The core of the sourcing system: confirm every quote-level source (a
    binding's ``sources``, a drug's ``nbn_sources``, an enzyme's ``variability``
    sources, and a projection's quote-level ``sources``) is actually present in the
    page it cites.

    A source is ``{corpus, page, quote, provenance}`` (the one shape used everywhere:
    drug bindings, NbN, projection/circuit/group quotes, region anatomy). A source
    with no ``corpus`` field is defensively skipped (there are none today; fabricated
    bibliographic ``{citation, url}`` citations were removed). This:

    * checks ``corpus`` resolves to ``meta.source_corpora`` (else the citation is
      unrenderable) and that a ``"verified"`` grade carries a page + quote;
    * for any source that carries a quote + page, locates the corpus's page file
      (``<pages_dir>/<page>.md``) and asserts the **normalized** quote is a
      substring of the **normalized** page text (see :func:`normalize_for_match`).

    The page material is author-side and may be absent on a plain checkout (it is
    large + uncommitted, see ``data_sources/books/stahl/`` in CLAUDE.local.md); when a corpus has no
    ``pages_dir`` on disk the quote-in-page check is **skipped with a warning**
    while the structural checks above still run. So this hard-fails an invented or
    mistyped quote on the author's machine (and the pre-push gate) without
    breaking on a clone that lacks the sources.

    One corpus stands that lookup **down** rather than skipping it. A corpus shipping
    its own raw tables declares ``tsv_dir`` and no ``pages_dir`` (PharmFreq, #13):
    there is no prose page to look in, and a page written out of the same numbers as
    the quote would prove nothing. Its quotes are gated by re-derivation from the
    sha256-pinned files instead, in :func:`check_enzyme_variability` (family 12),
    which is why that is the one quote gate that runs on a plain clone."""
    report.header("5. Source quotes (verbatim in cited page)")
    gate = QuoteGate(report, meta)
    before = report.errors
    walk_drugs(gate, drugs)
    walk_metabolites(gate, metabolites)
    walk_addons(gate, addons)
    walk_projections(gate, meta, projections)
    walk_structures(gate, structures)
    walk_receptors(gate, meta, receptors, structures)
    walk_targets(gate, meta, structures)
    walk_enzymes(gate, meta)
    # Coverage: every emitted quote and every committed cache quote, whichever kind.
    if quotes_by_id is not None:
        n_table = sweep_quote_table(gate, quotes_by_id)
        n_cache = sweep_committed_caches(gate)
        if report.errors == before:
            report.ok(f"sweeps: {n_table} quotes.jsonl rows + {n_cache} committed cache "
                      f"quotes present on their pages")
    gate.report_quotes(before)

    check_heading_shapes(report, gate.headings)
    check_stahl_monographs(report, drugs, gate.headings)

    ki = KiGate(report, gate.corpora)
    check_ki_rows(ki, drugs, metabolites)

    check_contradictions(gate, ki, meta, contradictions, drugs=drugs,
                         metabolites=metabolites, receptors=receptors,
                         projections=projections, circuits=circuits, groups=groups,
                         structures=structures)
    gate.report_unjudged()
