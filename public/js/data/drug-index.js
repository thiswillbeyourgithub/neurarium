// Target -> drugs reverse indexes, built off the resolved drugs. Pure.

import { normName } from "../util.js";

/**
 * Build the target reverse indexes off resolved drugs (each with `bindings`,
 * `metabolites` carrying `linkFocusable` + `ownBindings`, `displayName`). Pure, so
 * tools/tests/drugs_by_target.test.mjs drives it on hand-built drugs.
 * @returns {{drugsByTarget: Map, prodrugsByTarget: Map}} see BrainData.
 */
export function indexDrugsByTarget(drugs) {
  // Reverse index from the bindings: a target id -> the drugs that act on it, each
  // paired with its resolved binding (so the binding's net-effect colour + action
  // is available). The key is the binding's `target` (a receptor id or a
  // drug_targets key), which is exactly each "Receptors & targets" entry's id, so a
  // receptor / target panel can list "interacting drugs" by looking itself up here.
  // Deduped to one row per (drug, target) in case a drug binds the same target
  // twice (the first binding wins).
  const drugsByTarget = new Map();
  // One metabolite can be produced by several modeled drugs (e.g. mCPP by both
  // nefazodone and trazodone), so it would otherwise contribute a separate, identical
  // row per parent to the same target. We collapse those into ONE row keyed by
  // (metabolite id, target) and merge the parents into `viaMetaboliteOfList`,
  // so the panel reads "metab. of A, B" once instead of listing the same molecule
  // twice. Persists across the outer drug loop (a shared metabolite is visited under
  // each parent).
  const metabRowByKey = new Map();
  // A prodrug's borrowed bindings, kept apart from `drugsByTarget` so a target panel
  // can show "LISDEXAMFETAMINE (via dextroamphetamine)" without counting it: the
  // binding node is the metabolite's (see the prodrug pass above). Only a borrowing
  // through a focusable metabolite drug (or a salt's modeled constituent) lands here; a non-drug metabolite already
  // gets its own "NAME (metab. of PRODRUG)" row below, which names the prodrug.
  const prodrugsByTarget = new Map();
  // A salt lends its constituent's bindings under the same tag (see the borrowing
  // pass), so a modeled constituent counts as the lender too.
  const focusableMetabolite = (d, name) =>
    d.metabolites.some((m) => m.name === name && m.linkFocusable)
    || (d.combo || []).some((c) => c.name === name && c.drugId);
  for (const d of drugs) {
    const seen = new Set();
    const seenBorrowed = new Set();
    for (const b of d.bindings) {
      if (b.viaMetabolite) {
        if (seenBorrowed.has(b.target) || !focusableMetabolite(d, b.viaMetabolite)) continue;
        seenBorrowed.add(b.target);
        if (!prodrugsByTarget.has(b.target)) prodrugsByTarget.set(b.target, []);
        prodrugsByTarget.get(b.target).push({ drug: d, binding: b });
        continue;
      }
      if (seen.has(b.target)) continue;
      seen.add(b.target);
      if (!drugsByTarget.has(b.target)) drugsByTarget.set(b.target, []);
      drugsByTarget.get(b.target).push({ drug: d, binding: b });
    }
    // Surface a metabolite's OWN bindings under their target too, attributed to the
    // parent drug ("NAME (metab. of PRODRUG)"). Only its own (non-linked) bindings,
    // and only when the metabolite is not itself a focusable drug already listed here,
    // so nothing is double-listed.
    for (const m of d.metabolites) {
      if (m.linkFocusable) continue;
      for (const b of m.ownBindings) {
        const rowKey = `${m.id || normName(m.name)}:${b.target}`;
        const existing = metabRowByKey.get(rowKey);
        if (existing) {
          // Same metabolite, same target, different parent: merge the prodrug into the
          // existing row rather than adding a duplicate (one molecule, one record, so
          // its bindings are the same under every parent).
          if (!existing.viaMetaboliteOfList.includes(d.displayName)) {
            existing.viaMetaboliteOfList.push(d.displayName);
          }
          continue;
        }
        if (!drugsByTarget.has(b.target)) drugsByTarget.set(b.target, []);
        const row = {
          drug: d,
          binding: b,
          viaMetaboliteOfList: [d.displayName],
          metaboliteName: m.name,
        };
        metabRowByKey.set(rowKey, row);
        drugsByTarget.get(b.target).push(row);
      }
    }
  }
  return { drugsByTarget, prodrugsByTarget };
}
