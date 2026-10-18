"""Family 5 walks over the pharmacology nodes: drugs, metabolites, enzyme profiles.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import re

from ..walks import iter_drug_sources

# A quote can be verbatim on the cited page and still not support the claim. The
# recurring way that happened here: Stahl's "How Drug Causes Side Effects" block
# lists the mechanisms of the drug's CLASS as subject-less rules ("Blocking
# muscarinic cholinergic receptors can cause dry mouth ..."), printed identically
# across the monographs (that one on 17 pages, the alpha-1 one on 28), so it never
# states that THIS drug blocks anything. 151 antipsychotic bindings were once
# sourced from three such lines, including muscarinic + H1 + alpha-1 blockade for
# sulpiride, a benzamide with none of them. A sentence that attributes the action
# ("By blocking X, IT can cause Y", "Paroxetine's weak antimuscarinic properties
# can cause ...") is fine and deliberately not matched: the subject is the point.
_NO_SUBJECT_QUOTE = re.compile(
    r"^(Blocking\b|Antihistaminic actions\b)[^.]*\b(can|may) cause\b", re.I)


def walk_drugs(gate, drugs):
    """Every quote-level citation a drug record carries, its Ki quotes and bullets."""
    check_one, check_uncertainty = gate.check_one, gate.check_uncertainty
    for drug in drugs:
        did = drug.get("id")
        for ctx, src, short_ok, facet, owner in iter_drug_sources(drug):
            check_one(ctx, src, short_ok=short_ok)
            # A binding that DECLARES the problem (the orange "uncertain" badge, whose
            # own bullets say the sentence attributes nothing) is not silently passing
            # a subject-less quote off as a green check, so the gate stands down.
            if (facet == "binding" and not owner.get("uncertainty")
                    and _NO_SUBJECT_QUOTE.match(src.get("quote") or "")):
                gate.report.error(
                    f"{ctx}: quote is a subject-less mechanism -> side-effect rule "
                    f"({src.get('quote')!r}). Stahl's 'How Drug Causes Side Effects' "
                    f"block prints the same lines on every monograph in the class, so "
                    f"such a sentence never says THIS drug has the action: it cannot "
                    f"source a binding (an attributed one, 'By blocking X, IT can "
                    f"cause Y', can)")
        for binding in drug.get("bindings", []):
            # A quote-carrying Ki source (corpus #9 wikipedia_pharm cites the verbatim
            # affinity-table row) is gated here like any other quote. A PDSP Ki cites a
            # CSV row (ki_id, no quote) and is verified by the CSV gate (ki.py) instead,
            # so only feed a Ki source that actually carries a quote.
            ki_src = (binding.get("ki") or {}).get("source")
            if ki_src and ki_src.get("quote"):
                # A Ki quote is one table row (target | value | species): short by
                # design, and its number + target make a chance match implausible.
                check_one(f"drug {did} binding {binding.get('target')} ki.source", ki_src,
                          short_ok=True)
            check_uncertainty(f"drug {did} binding {binding.get('target')}", binding)
        for e in drug.get("enzymes", []) or []:
            # The denial quote of a contradicted row is gated exactly like the claim it
            # doubts: both sides of a corpus disagreement earn their grade the same way.
            check_uncertainty(f"drug {did} enzyme {e.get('enzyme')} ({e.get('role')})", e)
            # HOW MUCH of the clearing the row claims: its own node, so its own gate.
            gate.check_claims(f"drug {did} enzyme {e.get('enzyme')}", e,
                              {"strength": e.get("strength")})
        # A denial of a metabolite link (CONTRADICTIONS), gated like the link.
        for m in drug.get("metabolites", []) or []:
            check_uncertainty(f"drug {did} metabolite {m.get('id')}", m)


def walk_metabolites(gate, metabolites):
    """A metabolite's own half-life + bindings (counted once, however many parents)."""
    check_one = gate.check_one
    for m in metabolites:
        mid = f"metabolite {m.get('id')}"
        for i, src in enumerate(m.get("half_life_sources", []) or []):
            check_one(f"{mid} half_life_sources[{i}]", src)
        for binding in m.get("bindings", []) or []:
            for i, src in enumerate(binding.get("sources", []) or []):
                check_one(f"{mid} binding {binding.get('target')} sources[{i}]", src)
            # A metabolite binding's quote-carrying Ki (wikipedia_pharm table row) is
            # gated exactly like a drug binding's (a PDSP CSV Ki is checked in ki.py).
            ki_src = (binding.get("ki") or {}).get("source")
            if ki_src and ki_src.get("quote"):
                check_one(f"{mid} binding {binding.get('target')} ki.source", ki_src,
                          short_ok=True)  # a table row, as for a drug's Ki above
            gate.check_uncertainty(f"{mid} binding {binding.get('target')}", binding)


def walk_enzymes(gate, meta):
    """Metabolizer-status profiles hang off `meta.enzymes`, not off any node file, so
    they are reached from here rather than by the node walks. The page lookup stands
    down for them (see the `tsv_dir` branch of the gate), but the structural half
    applies: a `verified` grade still owes a page and a quote, and the pipeline still
    has to be one `meta.quote_pipelines` describes."""
    for eid, enzyme in sorted((meta.get("enzymes") or {}).items()):
        for i, src in enumerate(((enzyme.get("variability") or {})
                                 .get("sources") or [])):
            gate.check_one(f"enzyme {eid} variability sources[{i}]", src)
