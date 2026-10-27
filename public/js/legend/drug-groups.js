// How the Drugs browse list is grouped + ordered: by class (the default), by name,
// by first-approval decade, or by half-life bucket. DOM-free so it is unit tested
// (tools/tests/drug_groups.test.mjs); js/legend/drugs.js renders what it returns.

export const DRUG_SORT_MODES = ["class", "name", "year", "halflife"];

// Half-life buckets, by the T½ lower bound in hours: [upper bound (exclusive), i18n key].
const HL_BUCKETS = [
  [6, "drugs.hl.short"],
  [24, "drugs.hl.day"],
  [72, "drugs.hl.days"],
  [Infinity, "drugs.hl.long"],
];

const byName = (a, b) => a.name.localeCompare(b.name);
const yearOf = (d) => (d.firstApproval && d.firstApproval.year) || null;
const hoursOf = (d) => (d.halfLife && typeof d.halfLife.hours === "number" ? d.halfLife.hours : null);

/**
 * Group drugs for one sort mode. Each group is `{label, drugs}` in display order; a
 * drug with no value for the sort key lands in a trailing "unknown" group rather
 * than disappearing.
 * @param {object[]} drugs  the loaded drugs (name, categories, firstApproval, halfLife)
 * @param {string} mode     one of DRUG_SORT_MODES
 * @param {{cats: Object<string,string>, t: Function}} ctx  category labels + i18n
 * @returns {{label: string, drugs: object[]}[]}
 */
export function groupDrugs(drugs, mode, { cats, t }) {
  if (mode === "name") {
    return bucket([...drugs].sort(byName), (d) => d.name[0].toUpperCase());
  }
  if (mode === "year") {
    const known = drugs.filter(yearOf)
      .sort((a, b) => yearOf(a) - yearOf(b) || byName(a, b));
    return withUnknown(
      bucket(known, (d) => t("drugs.decade", { decade: Math.floor(yearOf(d) / 10) * 10 })),
      drugs.filter((d) => !yearOf(d)), t("drugs.unknownYear"));
  }
  if (mode === "halflife") {
    const known = drugs.filter((d) => hoursOf(d) !== null)
      .sort((a, b) => hoursOf(a) - hoursOf(b) || byName(a, b));
    return withUnknown(
      bucket(known, (d) => t(HL_BUCKETS.find(([max]) => hoursOf(d) < max)[1])),
      drugs.filter((d) => hoursOf(d) === null), t("drugs.unknownHalfLife"));
  }
  // By primary (first) category, in the meta category-label order, then any
  // leftover keys; A->Z within each.
  const byCat = new Map();
  for (const d of drugs) {
    const cat = (d.categories && d.categories[0]) || "other";
    if (!byCat.has(cat)) byCat.set(cat, []);
    byCat.get(cat).push(d);
  }
  const order = [...Object.keys(cats), ...[...byCat.keys()].filter((c) => !(c in cats))];
  return order.filter((c) => byCat.has(c))
    .map((c) => ({ label: cats[c] || c, drugs: byCat.get(c).sort(byName) }));
}

// Split an already-ordered list into consecutive runs sharing `keyOf`.
function bucket(sorted, keyOf) {
  const groups = [];
  for (const d of sorted) {
    const label = keyOf(d);
    if (!groups.length || groups[groups.length - 1].label !== label) groups.push({ label, drugs: [] });
    groups[groups.length - 1].drugs.push(d);
  }
  return groups;
}

function withUnknown(groups, unknown, label) {
  return unknown.length ? [...groups, { label, drugs: unknown.sort(byName) }] : groups;
}
