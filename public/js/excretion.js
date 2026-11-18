// Excretion (BETA): the drug panel's "Excretion" section (node kind drug_excretion,
// data_generators/excretion.py; mapped in js/data/drug-facts.js). One node per (drug,
// aspect, value): the route (urine / faeces), the share excreted unchanged, the kidney
// step (filtration, tubular secretion / reabsorption) and the urine-pH dependence, the
// labels coming from meta.excretion_aspects. Pure helpers only (no DOM), so
// tools/tests/excretion.test.mjs can pin the grouping and the wording.
// Built with the help of Claude Code.

/**
 * Localize meta.excretion_aspects ({aspect: {label, values: {value: label}}}, each label
 * an English string once emitted, or {en, fr} before externalize) into
 * {aspect: {label, values: {value: label}}}, keeping the generator's order.
 * @param {object} meta the emitted map
 * @param {(m: object) => string} localize picks the reader's language
 */
export function localizeAspects(meta, localize) {
  const out = {};
  for (const [aspect, a] of Object.entries(meta || {})) {
    const values = {};
    for (const [v, l] of Object.entries(a.values || {})) values[v] = localize(l);
    out[aspect] = { label: localize(a.label), values };
  }
  return out;
}

/**
 * Split a drug's rows by aspect in vocabulary order (the generator already sorts the
 * rows), empty aspects dropped: [{aspect, label, rows}].
 * @param {Array<{aspect: string}>} rows
 * @param {object} aspects the localized map from localizeAspects
 */
export function groupExcretion(rows, aspects) {
  return Object.entries(aspects || {})
    .map(([aspect, a]) => ({ aspect, label: a.label,
      rows: (rows || []).filter((r) => r.aspect === aspect) }))
    .filter((g) => g.rows.length);
}

/** The value label plus its verbatim figure: "urine (kidneys) (80%)". */
export function formatValue(n) {
  return n.amount ? `${n.valueLabel} (${n.amount})` : n.valueLabel;
}

/** One node as a single line, for the node browser: "route: urine (kidneys) (80%)". */
export function formatExcretion(n) {
  return `${n.aspectLabel}: ${formatValue(n)}`;
}
