// Node-kind registry: the ONE list of every graded node kind the viewer renders.
//
// Read by the Data browser (enumeration order = its kind <select> order), the Sources
// popup (each kind's coverage-bar label) and the popup's per-kind example (picked from
// the browser's own rows, see exampleRow). A new node kind is therefore one entry here
// plus its rows in node-browser.js collectNodes; nothing else names kinds by hand.
//
// `label` is the i18n key; `example` is the owner id (drug / receptor / target /
// structure base) whose row is preferred as the kind's example, so the popup shows a
// recognizable node instead of whichever owner happens to come first.
//
// Wikipedia `references` is deliberately absent: a reference is a pointer *at* a node,
// not itself one (and every present link defaults to `sourced`, which would read as a
// uniformly yellow bar). It stays in meta.provenance_stats.by_kind, just not rendered.
// `enzyme_variability` has a bar but no browser rows (its rows live in the enzyme panel).
// The canonical roster is tools/data_generators/node_kinds.py NODE_KINDS;
// tools/tests/test_node_kinds.py pins this list to it, and tools/tests/node_rows.test.mjs
// checks each kind's Data-browser row count against the shipped by_kind tally.

export const KINDS = [
  { kind: "addons", label: "about.kindAddons" },
  { kind: "structures", label: "about.kindStructures", example: "hippocampus" },
  { kind: "projections", label: "about.kindProjections" },
  { kind: "projection_transmitter", label: "about.kindProjectionTransmitter" },
  { kind: "projection_sign", label: "about.kindProjectionSign" },
  { kind: "circuits", label: "about.kindCircuits" },
  { kind: "projection_groups", label: "about.kindProjectionGroups" },
  { kind: "receptors", label: "about.kindReceptors", example: "5ht2a" },
  { kind: "receptor_class", label: "about.kindReceptorClass", example: "5ht2a" },
  { kind: "receptor_sign", label: "about.kindReceptorSign", example: "5ht2a" },
  { kind: "receptor_synaptic", label: "about.kindReceptorSynaptic", example: "5ht2a" },
  { kind: "receptor_locations", label: "about.kindReceptorLocations", example: "5ht2a" },
  { kind: "receptor_density", label: "about.kindReceptorDensity", example: "5ht2a" },
  { kind: "targets", label: "about.kindTargets", example: "sert" },
  { kind: "target_polarity", label: "about.kindTargetPolarity", example: "sert" },
  { kind: "target_locations", label: "about.kindTargetLocations", example: "sert" },
  { kind: "target_density", label: "about.kindTargetDensity", example: "sert" },
  { kind: "receptor_effect", label: "about.kindReceptorEffect", example: "5ht2a" },
  { kind: "receptor_release_modulation", label: "about.kindReleaseModulation", example: "5ht2a" },
  { kind: "receptor_demographic", label: "about.kindDemographic", example: "5ht2a" },
  { kind: "receptor_variant", label: "about.kindReceptorVariant", example: "sert" },
  { kind: "drug_bindings", label: "about.kindBindings", example: "olanzapine" },
  { kind: "drug_binding_action", label: "about.kindBindingAction", example: "olanzapine" },
  { kind: "drug_nbn", label: "about.kindNbn", example: "olanzapine" },
  { kind: "drug_brands", label: "about.kindDrugBrands", example: "olanzapine" },
  { kind: "drug_categories", label: "about.kindDrugCategories", example: "olanzapine" },
  { kind: "drug_half_life", label: "about.kindDrugHalfLife", example: "olanzapine" },
  { kind: "drug_tmax", label: "about.kindDrugTmax", example: "olanzapine" },
  { kind: "drug_formulations", label: "about.kindDrugFormulations", example: "olanzapine" },
  { kind: "drug_first_approval", label: "about.kindDrugFirstApproval", example: "olanzapine" },
  { kind: "drug_withdrawals", label: "about.kindDrugWithdrawals", example: "olanzapine" },
  { kind: "drug_holders", label: "about.kindDrugHolders", example: "olanzapine" },
  { kind: "drug_originator", label: "about.kindDrugOriginator", example: "olanzapine" },
  { kind: "drug_originator_country", label: "about.kindDrugOriginatorCountry", example: "olanzapine" },
  { kind: "drug_prodrug", label: "about.kindDrugProdrug", example: "olanzapine" },
  { kind: "drug_constituents", label: "about.kindDrugConstituents", example: "dimenhydrinate" },
  { kind: "drug_therapeutic_range", label: "about.kindDrugTherapeuticRange", example: "clozapine" },
  { kind: "drug_alert_level", label: "about.kindDrugAlertLevel", example: "clozapine" },
  { kind: "drug_lipophilicity", label: "about.kindDrugLipophilicity", example: "citalopram" },
  { kind: "drug_polar_surface", label: "about.kindDrugPolarSurface", example: "citalopram" },
  { kind: "drug_bbb", label: "about.kindDrugBbb", example: "olanzapine" },
  { kind: "drug_workup", label: "about.kindDrugWorkup", example: "olanzapine" },
  { kind: "drug_enzymes", label: "about.kindDrugEnzymes", example: "olanzapine" },
  { kind: "drug_enzyme_strength", label: "about.kindDrugEnzymeStrength", example: "olanzapine" },
  { kind: "enzyme_variability", label: "about.kindEnzymeVariability" },
  { kind: "drug_pgx", label: "about.kindDrugPgx", example: "citalopram" },
  { kind: "drug_metabolites", label: "about.kindDrugMetabolites", example: "fluoxetine" },
  { kind: "drug_metabolite_enzyme", label: "about.kindDrugMetaboliteEnzyme", example: "olanzapine" },
  { kind: "drug_metabolite_bindings", label: "about.kindDrugMetaboliteBindings", example: "olanzapine" },
];

/** Kind ids in registry order. */
export const KIND_ORDER = KINDS.map((k) => k.kind);

/** Kind id -> its i18n label key. */
export const KIND_LABELS = Object.fromEntries(KINDS.map((k) => [k.kind, k.label]));

const EXAMPLE = Object.fromEntries(KINDS.map((k) => [k.kind, k.example || null]));

/**
 * The representative row for one kind, out of collectNodes' rows: a navigable row
 * owned by the kind's preferred example when there is one, else the first navigable
 * row, else null. A lateralized owner matches through its `_R` member.
 *
 * @param {object[]} rows collectNodes output (each row carries `kind`, `owner`, `go`)
 * @param {string} kind a registry kind id
 * @returns {object|null}
 */
export function exampleRow(rows, kind) {
  const ex = EXAMPLE[kind];
  let first = null;
  for (const r of rows) {
    if (r.kind !== kind || !r.go) continue;
    if (ex && (r.owner === ex || r.owner === `${ex}_R`)) return r;
    if (!first) first = r;
  }
  return first;
}
