/**
 * The drug panel's "Predicted effects (target-based)" (BETA) grouping: one drug's
 * possible effects (readEffectIndex's `byDrug` rows) laid out either by effect or by
 * receptor, both ordered by the drug's Ki (tighter binding first).
 *
 * No three.js, no DOM: pure functions, unit-tested by tools/tests/effect_grouping.test.mjs.
 * The Ki key is the caller's (`kiOf`, the panel passes format.js `bindingKi`, the same
 * median the binding profile sorts by), so every affinity ordering agrees. The
 * persisted mode rides js/prefs.js like the Interactions grouping does.
 *
 * Built with the help of Claude Code.
 */
import { loadString, saveString } from "./prefs.js";

export const EFFECT_GROUPINGS = ["effect", "receptor"];
const GROUP_KEY = "neurarium.effectGroup";

/** The stored grouping, "effect" (the default) unless "receptor" was picked. */
export function loadEffectGrouping() {
  return loadString(GROUP_KEY) === "receptor" ? "receptor" : "effect";
}

/** Store the grouping, best-effort. @param {string} mode "effect" | "receptor" */
export function saveEffectGrouping(mode) {
  saveString(GROUP_KEY, mode);
}

// Ascending Ki, an unmeasured one (Infinity, or anything not a finite number) last,
// ties by name. Infinity - Infinity is NaN, hence the explicit comparison.
const byKiThenName = (a, b) => {
  const ka = Number.isFinite(a.ki) ? a.ki : Infinity;
  const kb = Number.isFinite(b.ki) ? b.ki : Infinity;
  if (ka !== kb) return ka < kb ? -1 : 1;
  return a.name.localeCompare(b.name);
};

/**
 * Group one drug's possible effects for display.
 *
 * @param {{effect:string, label:string, via:{binding:object, node:object}[]}[]} effects
 *   e.g. `[{effect: "weight_gain", label: "Weight gain", via: [{binding: {target:
 *   "h1", targetName: "H1", action: "antagonist", ki: {median: 1.1}}, node}]}]`.
 * @param {"effect"|"receptor"} mode
 * @param {(binding: object) => number} kiOf  a binding's Ki in nM, Infinity when unmeasured.
 * @returns {{key:string|object, label:string, ki:number, items:object[]}[]}
 *   - "effect": one group per effect, `key` = effect id, `ki` = the lowest Ki among
 *     its receptors, `items` = its via entries `{binding, node, ki}` by Ki.
 *   - "receptor": one group per binding (the binding object is the `key`, so a
 *     metabolite's binding at the same target stays apart), `label` = its target
 *     name, `items` = the effects it could mediate `{effect, label, node, ki}` by label.
 *   Groups are sorted by `ki` (missing last), then by label.
 */
export function groupPossibleEffects(effects, mode, kiOf) {
  if (mode === "receptor") {
    const byBinding = new Map();
    for (const e of effects || []) {
      for (const { binding, node } of e.via) {
        if (!byBinding.has(binding)) {
          byBinding.set(binding, { key: binding, label: binding.targetName || binding.target,
            ki: kiOf(binding), items: [] });
        }
        byBinding.get(binding).items.push({ effect: e.effect, label: e.label, node,
          ki: kiOf(binding), name: e.label });
      }
    }
    const groups = [...byBinding.values()];
    for (const g of groups) {
      g.name = g.label;
      g.items.sort((a, b) => a.label.localeCompare(b.label));
    }
    return groups.sort(byKiThenName);
  }
  const groups = (effects || []).map((e) => {
    const items = e.via.map(({ binding, node }) => ({ binding, node, ki: kiOf(binding),
      name: binding.targetName || binding.target })).sort(byKiThenName);
    const ki = items.length ? items[0].ki : Infinity;
    return { key: e.effect, label: e.label, ki, items, name: e.label };
  });
  return groups.sort(byKiThenName);
}
