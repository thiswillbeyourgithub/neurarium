/**
 * receptor_effect nodes (BETA): resolve them for the receptor / target panel, and
 * read the build-time effect index behind the Effects section, the effect panel and a
 * drug's "Predicted effects (target-based)".
 *
 * No three.js, no DOM: pure functions, unit-tested by
 * tools/tests/receptor_effects.test.mjs. The drug-side list is computed at build time
 * (tools/data_generators/effect_index.py), never stored in the dataset, and is a statement about the receptors a drug acts on, not about the drug:
 * the panel words it conditionally ("could cause"), never as a side effect of the drug.
 *
 * Built with the help of Claude Code.
 */

/**
 * Resolve one owner's emitted `effects` list into display rows.
 * @param {object[]} raw  `[{mode, effect, sources, grade, uncertainty?}]` from the record.
 * @param {Object<string,{label:string}>} modes  meta.receptor_effect_modes (localized labels).
 * @param {Object<string,string>} labels  meta.receptor_effect_labels (localized).
 * @returns {{mode:string, effect:string, label:string, modeLabel:string,
 *            sources:object[], uncertainty:object[], provenance:string}[]}
 */
export function resolveEffects(raw, modes, labels) {
  return (raw || []).map((e) => ({
    mode: e.mode,
    effect: e.effect,
    label: labels[e.effect] || e.effect,
    modeLabel: (modes[e.mode] && modes[e.mode].label) || e.mode,
    sources: e.sources || [],
    // Derived reasons to doubt (an isolated-tissue-only effect, quotes/uncertainty.py):
    // the row's pill reads orange and its tooltip leads with them.
    uncertainty: e.uncertainty || [],
    provenance: e.grade || "llm",
  }));
}

/**
 * Resolve the build-time effect index (`/derived/effects.json`, written by
 * tools/render_api.py from tools/data_generators/effect_index.py, the one place the
 * effect -> receptors -> drugs join is computed) against the loaded data. Ids only
 * in, objects out: nothing is joined here, so the viewer, the /api/ pages and
 * llms.txt can never disagree. An id the loaded data lacks (a stale file) is skipped.
 *
 * @param {{effects: object[]}} json  `{effects: [{id, owners: [{target, mode}],
 *   drugs: [{drug, via: [{target, action, mode, via_metabolite?}]}]}]}`.
 * @param {Map<string, object>} targetsById  merged receptor + target list by id.
 * @param {Map<string, object[]>} effectsByTarget  target id -> resolved effect rows.
 * @param {Map<string, object>} drugsById  drugs with resolved `allBindings` (else
 *   `bindings`), each `{target, action, viaMetabolite}`.
 * @param {Object<string,string>} labels  localized meta.receptor_effect_labels.
 * @returns {{effects: {id:string, label:string, owners:{target:object, node:object}[],
 *   drugs:{drug:object, via:{binding:object, node:object}[]}[]}[],
 *   byDrug: Map<string, {effect:string, label:string, via:object[]}[]>}}
 *   e.g. `effects[0] = {id: "nausea", label: "Nausea / vomiting", owners: [{target: 5ht3,
 *   node}], drugs: [{drug: ondansetron, via: [...]}]}`, sorted by localized label;
 *   `byDrug.get("olanzapine")` = that drug's possible effects, for the drug panel.
 */
export function readEffectIndex(json, targetsById, effectsByTarget, drugsById, labels) {
  const nodeOf = (target, mode, effect) =>
    (effectsByTarget.get(target) || []).find((n) => n.mode === mode && n.effect === effect);
  const effects = [];
  const byDrug = new Map();
  for (const e of (json && json.effects) || []) {
    const label = labels[e.id] || e.id;
    const owners = [];
    for (const o of e.owners || []) {
      const target = targetsById.get(o.target);
      const node = nodeOf(o.target, o.mode, e.id);
      if (target && node) owners.push({ target, node });
    }
    const drugs = [];
    for (const d of e.drugs || []) {
      const drug = drugsById.get(d.drug);
      if (!drug) continue;
      const via = [];
      for (const v of d.via || []) {
        // allBindings: the drug's own plus its active metabolites' (js/data/drugs.js).
        const binding = (drug.allBindings || drug.bindings || []).find((b) => b.target === v.target
          && b.action === v.action && (b.viaMetabolite || null) === (v.via_metabolite || null));
        const node = nodeOf(v.target, v.mode, e.id);
        if (binding && node) via.push({ binding, node });
      }
      if (!via.length) continue;
      drugs.push({ drug, via });
      if (!byDrug.has(drug.id)) byDrug.set(drug.id, []);
      byDrug.get(drug.id).push({ effect: e.id, label, via });
    }
    effects.push({ id: e.id, label, owners, drugs });
  }
  effects.sort((a, b) => a.label.localeCompare(b.label));
  for (const list of byDrug.values()) list.sort((a, b) => a.label.localeCompare(b.label));
  return { effects, byDrug };
}

/**
 * Group rows by receptor_effect mode, in the closed vocabulary's order
 * (meta.receptor_effect_modes: agonism, antagonism, ...), so a receptor panel and an
 * effect panel list the same modes the same way. Empty modes are left out; a mode
 * missing from the vocabulary goes last, so no row is ever dropped.
 * @param {object[]} rows
 * @param {(row: object) => string} modeOf
 * @param {Object<string, unknown>} modes meta.receptor_effect_modes
 * @returns {{mode: string, rows: object[]}[]} e.g. `[{mode: "antagonism", rows: [...]}]`
 */
export function groupByMode(rows, modeOf, modes) {
  const order = Object.keys(modes || {});
  const byMode = new Map();
  for (const r of rows || []) {
    const m = modeOf(r);
    if (!byMode.has(m)) byMode.set(m, []);
    byMode.get(m).push(r);
  }
  const rank = (m) => (order.includes(m) ? order.indexOf(m) : order.length);
  return [...byMode.keys()].sort((a, b) => rank(a) - rank(b))
    .map((mode) => ({ mode, rows: byMode.get(mode) }));
}
