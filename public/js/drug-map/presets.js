// Drugs map presets: ready-made views a click loads, each a patch over DEFAULT_VIEW
// (js/drug-map/model.js), so a preset starts from the defaults rather than stacking on
// whatever the reader had set. Pure data + two helpers, no DOM, so node tests run it.
// A preset's display name is the i18n key `drugmap.preset.<id>`. The README pictures of
// every preset are rendered by tools/shot_drugs_map.py, which clicks each button.

import { DEFAULT_VIEW } from "./model.js";

const ANTIPSYCHOTICS = ["antipsychotic_atypical", "antipsychotic_conventional"];
const ANTIDEPRESSANTS = ["ssri", "snri", "tricyclic", "maoi", "antidepressant_other"];

/** @type {{id: string, view: object}[]} in display order */
export const PRESETS = [
  // Where each antipsychotic sits on the dopamine system alone, coloured by its NbN
  // mechanism: separates the D2 antagonists from the partial agonists and the D4-leaning ones.
  { id: "ap_dopamine", view: { cats: ANTIPSYCHOTICS, only: ["d1", "d2", "d3", "d4", "d5", "dat"], color: "nbn" } },
  // The classic "atypicality" plot: D2 affinity against 5-HT2A affinity, plotted directly.
  { id: "ap_d2_5ht2a", view: { cats: ANTIPSYCHOTICS, only: ["d2", "5ht2a"] } },
  // The receptors behind the usual side effects: H1 (sedation, weight), M1
  // (anticholinergic), alpha1 (orthostatic hypotension), 5-HT2C (weight).
  { id: "ap_side", view: { cats: ANTIPSYCHOTICS, only: ["h1", "m1", "alpha1a", "5ht2c"] } },
  // Serotonin against noradrenaline reuptake: SSRIs, SNRIs and tricyclics fan out.
  { id: "ad_sert_net", view: { cats: ANTIDEPRESSANTS, only: ["sert", "net"] } },
  // Every antidepressant on its whole binding profile, coloured by NbN mechanism.
  { id: "ad_profile", view: { cats: ANTIDEPRESSANTS, color: "nbn" } },
  // Sleep and anxiety drugs: benzodiazepines, Z-drugs, orexin and melatonin agents,
  // sedating antihistamines.
  { id: "sleep", view: { cats: ["benzodiazepine", "hypnotic", "anxiolytic", "antihistamine"] } },
  // The whole roster by its signed effect on each transmitter system, not by receptor.
  { id: "all_tone", view: { source: "tone" } },
  // Sedating antihistamines: H1 (sedation) against M1 (anticholinergic load), plotted directly.
  { id: "antihistamines", view: { cats: ["antihistamine"], only: ["h1", "m1"] } },
  // The serotonergic psychedelics (no class of their own: they sit in "recreational") on
  // the 5-HT1A / 5-HT2A / 5-HT2B / 5-HT2C receptors. A drug binding none of those drops
  // out of the map, which leaves LSD, DMT, mescaline, 2C-B, MDMA and psilocybin (placed by
  // its metabolite psilocin's bindings). None is marketed,
  // hence the marketed filter off.
  { id: "psychedelics", view: { cats: ["recreational"], only: ["5ht2a", "5ht2c", "5ht1a", "5ht2b"], marketed: false } },
  // MAO inhibitors by MAO-A against MAO-B: moclobemide / clorgiline vs selegiline /
  // rasagiline, the non-selective ones on the diagonal.
  { id: "maois", view: { cats: ["maoi"], only: ["mao_a", "mao_b"] } },
  // Opioids on the three opioid receptors (mu, kappa, delta).
  { id: "opioids", view: { cats: ["opioid"], only: ["mu", "kappa", "delta"] } },
  // Stimulants by dopamine against noradrenaline reuptake.
  { id: "stimulants", view: { cats: ["stimulant"], only: ["dat", "net"] } },
];

/**
 * The full view a preset loads: the defaults, then the preset's patch (`cats` as a Set,
 * the form the view holds).
 * @param {{view: object}} preset
 * @returns {object}
 */
export function presetView(preset) {
  const v = { ...DEFAULT_VIEW, hidden: new Set(), ...preset.view };
  if (Array.isArray(v.cats)) v.cats = new Set(v.cats);
  return v;
}

const sameList = (a, b) => (a === null || b === null ? a === b
  : a.length === b.length && a.every((x, i) => x === b[i]));
const sameSet = (a, b) => (a === null || b === null ? a === b
  : a.size === b.size && [...a].every((x) => b.has(x)));

/**
 * Whether `view` is exactly what `preset` loads, so its button can show as active. Drugs
 * hidden by hand are ignored: hiding one outlier keeps the preset lit.
 * @param {object} view
 * @param {{view: object}} preset
 * @returns {boolean}
 */
export function matchesPreset(view, preset) {
  const want = presetView(preset);
  return Object.keys(DEFAULT_VIEW).every((k) => {
    if (k === "hidden") return true;
    if (k === "cats") return sameSet(view.cats, want.cats);
    if (k === "only" || k === "years") return sameList(view[k], want[k]);
    return view[k] === want[k];
  });
}
