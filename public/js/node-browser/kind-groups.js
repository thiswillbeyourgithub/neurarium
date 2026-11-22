// The Data browser kind picker's layout: kinds grouped by OWNER (drug, receptor or
// target, region...) then by the panel SECTION that shows them, in the panel's own
// order, each kind under a short label that drops the owner ("Originator", not "Drug
// originator", since the owner header already says it). A header is pickable too and
// means every kind under it: "Excretion" + forbid "faeces" covers all excretion rows.
//
// "Name" comes first: it matches the OWNER's name across every kind (see query.js).
//
// Every registry kind with browser rows sits here exactly once (enzyme_variability has
// none); tools/tests/node_query.test.mjs pins that against kinds.js KINDS.
//
// Shape: an owner `{label, sections}` or `{label, kinds}` (no section level); a section
// `{label, kinds}`; a kind `[kindId, shortLabelKey]`. Labels are i18n keys.

export const KIND_GROUPS = [
  { label: "nodes.ownerDrug", sections: [
    { label: "drug.admin", kinds: [
      ["drug_categories", "nodes.k.drug_categories"],
      ["drug_nbn", "nodes.k.drug_nbn"],
      ["drug_originator", "nodes.k.drug_originator"],
      ["drug_originator_country", "nodes.k.drug_originator_country"],
      ["drug_first_approval", "nodes.k.drug_first_approval"],
      ["drug_withdrawals", "nodes.k.drug_withdrawals"],
      ["drug_holders", "nodes.k.drug_holders"],
      ["drug_brands", "nodes.k.drug_brands"],
      ["drug_constituents", "nodes.k.drug_constituents"],
    ] },
    { label: "drug.pkTiming", kinds: [
      ["drug_tmax", "nodes.k.drug_tmax"],
      ["drug_half_life", "nodes.k.drug_half_life"],
      ["drug_therapeutic_range", "nodes.k.drug_therapeutic_range"],
      ["drug_alert_level", "nodes.k.drug_alert_level"],
      ["drug_formulations", "nodes.k.drug_formulations"],
      ["drug_lipophilicity", "nodes.k.drug_lipophilicity"],
      ["drug_polar_surface", "nodes.k.drug_polar_surface"],
      ["drug_bbb", "nodes.k.drug_bbb"],
    ] },
    { label: "drug.actsOn", kinds: [
      ["drug_prodrug", "nodes.k.drug_prodrug"],
      ["drug_bindings", "nodes.k.drug_bindings"],
      ["drug_binding_action", "nodes.k.drug_binding_action"],
    ] },
    { label: "drug.metabolism", kinds: [
      ["drug_metabolites", "nodes.k.drug_metabolites"],
      ["drug_metabolite_bindings", "nodes.k.drug_metabolite_bindings"],
      ["drug_metabolite_enzyme", "nodes.k.drug_metabolite_enzyme"],
      ["drug_enzymes", "nodes.k.drug_enzymes"],
      ["drug_enzyme_strength", "nodes.k.drug_enzyme_strength"],
    ] },
    { label: "drug.pharmacogenomics", kinds: [["drug_pgx", "nodes.k.drug_pgx"]] },
    { label: "drug.workup", kinds: [["drug_workup", "nodes.k.drug_workup"]] },
    { label: "drug.excretion", kinds: [["drug_excretion", "nodes.k.drug_excretion"]] },
    { label: "drug.sleep", kinds: [["drug_sleep", "nodes.k.drug_sleep"]] },
    { label: "drug.seizure", kinds: [["drug_seizure_threshold", "nodes.k.drug_seizure_threshold"]] },
  ] },
  { label: "nodes.ownerTarget", sections: [
    { label: "nodes.secClassification", kinds: [
      ["receptors", "nodes.k.receptors"],
      ["receptor_class", "nodes.k.receptor_class"],
      ["receptor_sign", "nodes.k.receptor_sign"],
      ["receptor_synaptic", "nodes.k.receptor_synaptic"],
      ["targets", "nodes.k.targets"],
      ["target_polarity", "nodes.k.target_polarity"],
    ] },
    { label: "receptor.foundIn", kinds: [
      ["receptor_locations", "nodes.k.receptor_locations"],
      ["receptor_density", "nodes.k.receptor_density"],
      ["target_locations", "nodes.k.target_locations"],
      ["target_density", "nodes.k.target_density"],
    ] },
    { label: "effects.heading", kinds: [["receptor_effect", "nodes.k.receptor_effect"]] },
    { label: "relmod.heading", kinds: [["receptor_release_modulation", "nodes.k.receptor_release_modulation"]] },
    { label: "demog.heading", kinds: [["receptor_demographic", "nodes.k.receptor_demographic"]] },
    { label: "variant.heading", kinds: [["receptor_variant", "nodes.k.receptor_variant"]] },
  ] },
  { label: "nodes.ownerRegion", kinds: [["structures", "nodes.k.structures"]] },
  { label: "nodes.ownerPathway", kinds: [
    ["projections", "nodes.k.projections"],
    ["projection_transmitter", "nodes.k.projection_transmitter"],
    ["projection_sign", "nodes.k.projection_sign"],
  ] },
  { label: "nodes.ownerCircuit", kinds: [["circuits", "nodes.k.circuits"]] },
  { label: "nodes.ownerGroup", kinds: [["projection_groups", "nodes.k.projection_groups"]] },
  { label: "nodes.ownerAddon", kinds: [["addons", "nodes.k.addons"]] },
];

/** The "Name" entry's label key: matches the owner's name, not a kind. */
export const NAME_LABEL = "nodes.kindName";

/**
 * The picker's entries, in display order, for the kinds present in the rows:
 * `{label, depth, kinds: Set<string>|null, name?: true, head?: true}`, depth 0 = owner, 1 = section,
 * 2 = kind (an owner with no section level puts its kinds at depth 1). A header holds
 * every present kind under it; one with none is dropped. A header with a single kind
 * under it (a one-kind owner or section) shows alone, its label picking that kind.
 * @param {Set<string>|string[]} present the kinds with rows
 * @param {(key: string) => string} t i18n lookup
 * @returns {object[]}
 */
export function kindChoices(present, t) {
  const has = new Set(present);
  const out = [{ label: t(NAME_LABEL), depth: 0, kinds: null, name: true }];
  const leaves = (kinds, depth) => kinds.filter(([k]) => has.has(k))
    .map(([k, key]) => ({ label: t(key), depth, kinds: new Set([k]) }));
  // A header over its children (direct children only: their kinds already cover the
  // grandchildren), or nothing when no child is present.
  const block = (label, depth, children) => {
    const top = children.filter((c) => c.depth === depth + 1);
    if (!top.length) return [];
    const kinds = new Set(top.flatMap((c) => [...c.kinds]));
    const head = { label: t(label), depth, kinds, head: true };
    return top.length === 1 && kinds.size === 1 ? [head] : [head, ...children];
  };
  for (const owner of KIND_GROUPS) {
    out.push(...block(owner.label, 0, owner.sections
      ? owner.sections.flatMap((s) => block(s.label, 1, leaves(s.kinds, 2)))
      : leaves(owner.kinds, 1)));
  }
  return out;
}
