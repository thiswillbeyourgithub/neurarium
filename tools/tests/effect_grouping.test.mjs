// Unit tests for public/js/effect-grouping.js: a drug's possible effects grouped by
// effect or by receptor, both ordered by the drug's Ki with unmeasured Ki last.
// Run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { groupPossibleEffects } from "../../public/js/effect-grouping.js";

// The panel's own Ki key (format.js bindingKi); that module reads the i18n global at load.
globalThis.window = { __I18N__: { t: (k) => k, lang: "en" } };
const { bindingKi: kiOf } = await import("../../public/js/panel/format.js");

const h1 = { target: "h1", targetName: "H1", action: "antagonist", ki: { median: 1.1 } };
const d2 = { target: "d2", targetName: "D2", action: "antagonist", ki: { median: 125 } };
const m1 = { target: "m1", targetName: "M1", action: "antagonist", ki: { median: 6.2 } };
const nok = { target: "a2c", targetName: "Alpha-2C", action: "antagonist" };
const nok2 = { target: "5ht7", targetName: "5-HT7", action: "antagonist", ki: null };
const node = (id) => ({ id });

const effects = [
  { effect: "eps", label: "Extrapyramidal symptoms", via: [{ binding: d2, node: node("d2-eps") }] },
  { effect: "sedation", label: "Sedation",
    via: [{ binding: m1, node: node("m1-sed") }, { binding: h1, node: node("h1-sed") }] },
  { effect: "dry_mouth", label: "Dry mouth", via: [{ binding: m1, node: node("m1-dry") }] },
  { effect: "zz_unmeasured", label: "Aaa unmeasured", via: [{ binding: nok, node: node("x") }] },
  { effect: "weight_gain", label: "Weight gain",
    via: [{ binding: nok2, node: node("y") }, { binding: h1, node: node("h1-wg") }] },
];

test("by effect: effects by their best Ki, receptors under each by Ki, unmeasured last", () => {
  const g = groupPossibleEffects(effects, "effect", kiOf);
  assert.deepEqual(g.map((x) => x.key),
    ["sedation", "weight_gain", "dry_mouth", "eps", "zz_unmeasured"]);
  assert.deepEqual(g[0].items.map((i) => i.binding.target), ["h1", "m1"]);
  // A receptor with no Ki sorts after a measured one under the same effect.
  assert.deepEqual(g[1].items.map((i) => i.binding.target), ["h1", "5ht7"]);
  assert.equal(g[0].ki, 1.1);
  assert.equal(g[4].ki, Infinity);
  assert.equal(g[0].items[0].node.id, "h1-sed");
});

test("by receptor: receptors by Ki, effects under each by label, unmeasured last by name", () => {
  const g = groupPossibleEffects(effects, "receptor", kiOf);
  assert.deepEqual(g.map((x) => x.label), ["H1", "M1", "D2", "5-HT7", "Alpha-2C"]);
  assert.deepEqual(g[0].items.map((i) => i.effect), ["sedation", "weight_gain"]);
  assert.deepEqual(g[1].items.map((i) => i.label), ["Dry mouth", "Sedation"]);
  assert.equal(g[0].key, h1);
  assert.equal(g[1].items[0].node.id, "m1-dry");
});

test("a metabolite's binding at the same target is its own receptor group", () => {
  const own = { target: "d2", targetName: "D2", action: "antagonist", ki: { median: 5 } };
  const met = { ...own, viaMetabolite: "norclozapine", ki: { median: 2 } };
  const g = groupPossibleEffects([{ effect: "eps", label: "EPS",
    via: [{ binding: own, node: node("a") }, { binding: met, node: node("b") }] }], "receptor", kiOf);
  assert.equal(g.length, 2);
  assert.equal(g[0].key, met);
});

test("empty and missing input give no group", () => {
  assert.deepEqual(groupPossibleEffects([], "effect", kiOf), []);
  assert.deepEqual(groupPossibleEffects(null, "receptor", kiOf), []);
});
