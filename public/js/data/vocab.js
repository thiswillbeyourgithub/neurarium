// The presentation maps + vocabularies meta.json carries, localized once.

import { localizeMap } from "./localize.js";

/**
 * Read meta.json's presentation maps into the viewer's shape (label maps localized,
 * colour maps passed through). Every loader stage reads its vocabulary from here.
 * @param {object} metaRecord the parsed meta.json
 * @returns {object} one field per map (see the names returned below)
 */
export function readVocab(metaRecord) {
  // Presentation maps emitted by the generator (kind->arrow colour,
  // group->legend heading, kind->display label), so the palette/headings live in
  // the data, not hardcoded in the viewer. The label maps are bilingual {en,fr};
  // localize their values to plain strings here (the colour map is neutral).
  const projectionColors = metaRecord.projection_colors || {};
  // Sign (excitatory / inhibitory) colour mode: kind->sign fold + sign->colour.
  const kindSigns = metaRecord.kind_signs || {};
  const signColors = metaRecord.sign_colors || {};
  const groupLabels = localizeMap(metaRecord.group_labels);
  const kindLabels = localizeMap(metaRecord.kind_labels);
  const signLabels = localizeMap(metaRecord.sign_labels);
  // Receptor legend maps (family heading, mechanism class, pre/post-synaptic
  // label). The per-receptor sign reuses signColors/signLabels above.
  const receptorFamilyLabels = localizeMap(metaRecord.receptor_family_labels);
  // Family -> swatch colour, language-neutral: the transmitter's own colour for a
  // view that colours by transmitter (the simulation's receptor bars).
  const receptorFamilyColors = metaRecord.receptor_family_colors || {};
  const receptorClassLabels = localizeMap(metaRecord.receptor_class_labels);
  const synapticLabels = localizeMap(metaRecord.synaptic_labels);
  // Non-receptor drug-target presentation: type -> {en,fr} tag (localized) and
  // type -> swatch/dot colour (neutral), for the merged "Receptors & targets"
  // section where transporters/enzymes/channels sit beside the receptors.
  const targetTypeLabels = localizeMap(metaRecord.target_type_labels);
  const targetTypeColors = metaRecord.target_type_colors || {};
  // Drug legend + animation maps (category headings, binding targets, actions,
  // and the net-effect swatch colours/labels). drugTargets / drugActions are kept
  // as raw maps (their `name`/`label` are localized per binding below); the colour
  // map is language-neutral.
  const drugCategoryLabels = localizeMap(metaRecord.drug_category_labels);
  // Broad families over those categories (group id -> member categories), and labels.
  const drugCategoryGroups = metaRecord.drug_category_groups || {};
  const drugCategoryGroupLabels = localizeMap(metaRecord.drug_category_group_labels);
  // Regulatory history vocabularies (first approval + withdrawals): id -> label.
  const historyCountries = localizeMap(metaRecord.drug_history_countries);
  const historyScopes = new Set(metaRecord.drug_history_scopes || []);
  const historyAgencies = localizeMap(metaRecord.drug_history_agencies);
  const withdrawalReasons = localizeMap(metaRecord.drug_withdrawal_reasons);
  // Pre-prescription workup vocabularies (BDPM RCP #24): test / timing id -> label.
  const workupTests = localizeMap(metaRecord.workup_tests);
  const workupTimings = localizeMap(metaRecord.workup_timings);
  // Formulation release types (closed vocabulary, display order): id -> label.
  const releaseLabels = localizeMap(metaRecord.drug_releases);
  const drugTargets = metaRecord.drug_targets || {};
  const drugActions = metaRecord.drug_actions || {};
  const drugEffectColors = metaRecord.drug_effect_colors || {};
  const drugEffectLabels = localizeMap(metaRecord.drug_effect_labels);
  // Drug metabolism vocabularies (see ENZYMES in generate_data.py): the isoform
  // id -> {label, wikipedia} map, plus role and strength labels. Raw for the defs
  // (an isoform name is language-neutral), localized for the prose ones.
  const enzymeDefs = metaRecord.enzymes || {};
  const enzymeRoles = metaRecord.enzyme_roles || {};
  const enzymeStrengths = metaRecord.enzyme_strengths || {};
  const enzymeReactions = metaRecord.enzyme_reactions || {};
  // Drug target system -> projection kind, for the per-drug "by-mechanism flow"
  // overlay (only the diffuse ascending modulatory systems are mapped; see
  // generate_data.py SYSTEM_FLOW_KINDS). Language-neutral, applied per drug below.
  const systemFlowKinds = metaRecord.system_flow_kinds || {};
  // Source corpora (id -> {short, citation, url, pages_dir}) the per-claim binding
  // sources cite; the drug panel resolves a binding source's `corpus` to this for
  // its tooltip ref (see SOURCE_CORPORA in generate_data.py). Raw map (citation is
  // language-neutral); pages_dir is author-side and ignored by the viewer.
  const sourceCorpora = metaRecord.source_corpora || {};
  // Cross-donor-agreement floor a density profile had to clear to be published, so the
  // panel can state the real threshold rather than restate the generator's constant.
  const densityMinReliability = metaRecord.density_min_reliability ?? null;
  // Programmatic sourcing tally (per kind + headline) for the About panel; passed
  // through as-is (the numbers are computed in generate_data.py, see
  // _provenance_stats). Null on a dataset that predates it.
  const provenanceStats = metaRecord.provenance_stats || null;
  // Addon-node hook registry: slot -> the node kind whose panel it belongs to, and
  // tone -> its glyph. The viewer renders addons generically off these rather than
  // knowing any slot by name, so a new hook is a generator edit plus one call site.
  const addonSlots = metaRecord.addon_slots || {};
  // The browse sections an addon may anchor instead of a node (key -> label): the
  // one owner kind that is a view rather than a datum, for a caveat true of a whole
  // collection at once (see addonOwner below).
  const addonSections = metaRecord.addon_sections || {};
  const addonTones = metaRecord.addon_tones || {};
  // How a quote came to be cited: pipeline key -> its chain of custody as ordered step
  // keys, rendered at the bottom of every source tooltip. Passed through as-is; the
  // viewer only joins and localizes, so a new pipeline never needs a viewer edit.
  const quotePipelines = metaRecord.quote_pipelines || {};
  return {
    projectionColors,
    kindSigns,
    signColors,
    groupLabels,
    kindLabels,
    signLabels,
    receptorFamilyLabels,
    receptorFamilyColors,
    receptorClassLabels,
    synapticLabels,
    targetTypeLabels,
    targetTypeColors,
    drugCategoryLabels,
    drugCategoryGroups,
    drugCategoryGroupLabels,
    historyCountries,
    historyScopes,
    historyAgencies,
    withdrawalReasons,
    workupTests,
    workupTimings,
    releaseLabels,
    drugTargets,
    drugActions,
    drugEffectColors,
    drugEffectLabels,
    enzymeDefs,
    enzymeRoles,
    enzymeStrengths,
    enzymeReactions,
    systemFlowKinds,
    sourceCorpora,
    densityMinReliability,
    provenanceStats,
    addonSlots,
    addonSections,
    addonTones,
    quotePipelines,
  };
}
