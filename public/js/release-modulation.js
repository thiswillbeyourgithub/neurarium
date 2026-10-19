/**
 * receptor_release_modulation nodes (BETA): resolve them for the receptor panel's
 * "Downstream" section, and DERIVE a drug's possible release changes for the drug panel.
 *
 * No three.js, no DOM: pure functions, unit-tested by
 * tools/tests/release_modulation.test.mjs. The drug-side list is computed, never stored,
 * and is a statement about the receptors a drug acts on, not about the drug: the panel
 * words it conditionally ("could increase"), never as an effect of the drug.
 *
 * Built with the help of Claude Code.
 */

/**
 * Resolve one receptor's emitted `release_modulation` list into display rows.
 * @param {object[]} raw  `[{kind, site:{structure, cell}, modulates, effect_of_activation,
 *                          sources, grade}]` from the record.
 * @param {{kinds:Object<string,string>, cells:Object<string,string>,
 *          transmitters:Object<string,{label:string}>}} vocab  meta.release_modulation,
 *   labels localized.
 * @returns {object[]} rows `{kind, kindLabel, structure, cell, cellLabel, modulates,
 *   transmitterLabel, effect, sources, provenance}`.
 */
export function resolveModulation(raw, vocab) {
  const v = vocab || {};
  return (raw || []).map((n) => {
    const site = n.site || {};
    const tr = (v.transmitters || {})[n.modulates];
    return {
      kind: n.kind,
      kindLabel: (v.kinds || {})[n.kind] || n.kind,
      structure: site.structure || null,
      cell: site.cell,
      cellLabel: (v.cells || {})[site.cell] || site.cell,
      modulates: n.modulates,
      transmitterLabel: (tr && tr.label) || n.modulates,
      effect: n.effect_of_activation,
      sources: n.sources || [],
      provenance: n.grade || "llm",
    };
  });
}

/**
 * Template vars for a transmitter label: the French templates read {transmitter} as
 * "de <transmitter>" and leave the article to `ofNoun` ("d'histamine").
 * @param {string} label
 * @param {(word:string) => string} ofNoun  window.__I18N__.ofNoun.
 */
export function transmitterVars(label, ofNoun) {
  return { transmitter: ofNoun(label) };
}

/**
 * Which way a binding pushes a receptor's activation: +1 for an action the
 * receptor_effect `agonism` mode lists (agonist, partial agonist, PAM), -1 for one the
 * `antagonism` mode lists (antagonist, inverse agonist, NAM, blocker), 0 otherwise
 * (affinity_only, an inhibitor, an unknown action): no direction, no derivation.
 * @param {string|null} action
 * @param {Object<string,{actions:string[]}>} modes  meta.receptor_effect_modes.
 */
export function activationSign(action, modes) {
  if (!action) return 0;
  if (((modes.agonism || {}).actions || []).includes(action)) return 1;
  if (((modes.antagonism || {}).actions || []).includes(action)) return -1;
  return 0;
}

/**
 * Join a drug's bindings with the release-modulation nodes of the receptors they hit.
 *
 * Direction-aware: an agonist keeps a node's `effect` (the effect of activation), an
 * antagonist flips it, an affinity_only binding contributes nothing. Grouped by
 * (transmitter, derived direction, structure), so two receptors converging on "more
 * dopamine" read as one line with two "via" chips (one per receptor).
 *
 * @param {object[]} bindings  resolved drug bindings (`{target, action, ...}`).
 * @param {(targetId:string) => object[]} modsOf  target id -> resolved modulation rows.
 * @param {Object<string,{actions:string[]}>} modes  meta.receptor_effect_modes.
 * @returns {{modulates:string, transmitterLabel:string, direction:string,
 *            structure:string|null, via:{binding:object, node:object}[]}[]}
 *   in first-seen order of the bindings as given.
 */
export function deriveReleaseChanges(bindings, modsOf, modes) {
  const out = new Map();
  for (const b of bindings || []) {
    const sign = activationSign(b.action, modes || {});
    if (!sign) continue;
    for (const node of modsOf(b.target) || []) {
      const direction = sign > 0 ? node.effect
        : (node.effect === "increase" ? "decrease" : "increase");
      const key = `${node.modulates}|${direction}|${node.structure || ""}`;
      if (!out.has(key)) {
        out.set(key, { modulates: node.modulates, transmitterLabel: node.transmitterLabel,
                       direction, structure: node.structure, via: [] });
      }
      const entry = out.get(key);
      // One chip per (receptor, compound): two of its nodes (an autoreceptor on the
      // cell body and on the terminal) landing on the same change are one route, not
      // two, while the parent and its active metabolite on that receptor are two.
      if (!entry.via.some((v) => v.binding.target === b.target
          && (v.binding.viaMetabolite || null) === (b.viaMetabolite || null))) {
        entry.via.push({ binding: b, node });
      }
    }
  }
  return [...out.values()];
}
