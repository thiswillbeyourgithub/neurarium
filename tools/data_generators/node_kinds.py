"""The node-kind roster and the "backed" sum, shared by every tally reader.

``provenance._provenance_stats`` emits one ``meta.provenance_stats.by_kind`` entry
per kind below; ``check_data.py`` re-checks that tally and ``update_readme_stats.py``
renders it, so all three read these names instead of restating them.
``tools/tests/test_node_kinds.py`` pins the emitted meta, the README label table and
the viewer registry (``public/js/kinds.js``) to this roster.

Stdlib-free on purpose (imports nothing), so a standalone script can import it cheaply.
"""

from __future__ import annotations

# Every knowledge-node kind: each carries a claim + a grade and counts in the headline
# ``meta.provenance_stats.nodes``. Ordered as ``check_data.py`` prints its tally.
NODE_KINDS = ("addons", "drug_bindings", "drug_binding_action", "drug_nbn", "drug_brands",
              "drug_categories",
              "drug_half_life", "drug_tmax", "drug_formulations",
              "drug_first_approval", "drug_withdrawals",
              "drug_holders", "drug_originator", "drug_originator_country",
              "drug_prodrug", "drug_constituents", "drug_therapeutic_range", "drug_alert_level",
              "drug_lipophilicity", "drug_polar_surface", "drug_bbb", "drug_workup",
              "drug_enzymes", "drug_enzyme_strength",
              "enzyme_variability", "drug_pgx",
              "drug_metabolites",
              "drug_metabolite_enzyme", "drug_metabolite_bindings",
              "projections", "projection_transmitter", "projection_sign",
              "circuits", "projection_groups", "receptors",
              "receptor_class", "receptor_sign", "receptor_synaptic",
              "receptor_locations", "receptor_density", "targets", "target_polarity",
              "target_locations", "target_density", "receptor_effect",
              "receptor_release_modulation", "receptor_demographic",
              "receptor_variant",
              "structures")

# Tallied in ``by_kind`` but excluded from the headline: a Wikipedia reference points
# *at* a node, it is not itself one.
TALLY_ONLY_KINDS = ("references",)


def backed(counts):
    """Nodes resting on a real document: verified + uncertain + sourced.

    ``uncertain`` counts here on purpose (see quotes/uncertainty.py): the claim does
    have a quote-checked source, the badge only says the sentence does not attribute
    it. Only ``missing`` (a bare llm assertion or nothing at all) is unbacked.
    """
    return (counts.get("verified", 0) + counts.get("uncertain", 0)
            + counts.get("sourced", 0))
