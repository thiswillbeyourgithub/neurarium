// Drugs map PCA axis caption (public/js/drug-map/axis.js): each heavy feature lands at the
// end its drugs reach, which a signed profile flips for a blocked feature.
// Run: node --test tools/tests/

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { axisCaption, axisPoles, axisTooltip } from "../../public/js/drug-map/axis.js";
import { pca } from "../../public/js/drug-map/model.js";

globalThis.window = { __I18N_MESSAGES__: {} };
new Function(readFileSync(new URL("../../public/js/i18n/en.js", import.meta.url), "utf8"))();
const EN = window.__I18N_MESSAGES__.en;
const t = (key, vars = {}) => {
  assert.ok(key in EN, `missing ${key}`);
  return EN[key].replace(/\{(\w+)\}/g, (_, k) => String(vars[k]));
};
const names = { orexin: "Orexin", h1: "H1", gaba_a: "GABA-A", mt1: "MT1", "tone:serotonin": "Serotonin tone",
  "effect:sedation": "Sedation" };
const nameOf = (k) => names[k] || k;

// Weights and raw means as in the example in axis.js.
const LOADINGS = [
  { target: "orexin", w: 0.45, mean: -0.3 },  // positive weight, mostly blocked -> negative end
  { target: "gaba_a", w: 0.40, mean: 0.2 },   // positive weight, mostly activated -> positive end
  { target: "h1", w: -0.35, mean: -0.5 },     // negative weight, mostly blocked -> positive end
  { target: "mt1", w: -0.28, mean: 0.1 },     // negative weight, mostly activated -> negative end
];

test("a blocked feature lands at the end opposite its weight", () => {
  const { pos, neg } = axisPoles(LOADINGS, true);
  assert.deepEqual(pos, [{ target: "gaba_a", act: "boost" }, { target: "h1", act: "block" }]);
  assert.deepEqual(neg, [{ target: "orexin", act: "block" }, { target: "mt1", act: "boost" }]);
  assert.equal(axisCaption({ share: 0.25, loadings: LOADINGS }, 1, { signed: true, nameOf, t }),
    "PC2 (25% of variance): ↑ GABA-A boosted, H1 blocked · ↓ Orexin blocked, MT1 boosted");
});

test("unsigned: no action words, PC1 uses horizontal arrows, runs group under one word", () => {
  const unsigned = LOADINGS.map((l) => ({ ...l, mean: Math.abs(l.mean) }));
  assert.equal(axisCaption({ share: 0.4, loadings: unsigned }, 0, { signed: false, nameOf, t }),
    "PC1 (40% of variance): → Orexin, GABA-A · ← H1, MT1");
  const grouped = [{ target: "gaba_a", w: 0.5, mean: 1 }, { target: "orexin", w: 0.4, mean: 1 },
    { target: "tone:serotonin", w: 0.3, mean: -1 }, { target: "effect:sedation", w: -0.2, mean: 1 }];
  assert.equal(axisCaption({ share: 0.1, loadings: grouped }, 1, { signed: true, nameOf, t }),
    "PC2 (10% of variance): ↑ GABA-A, Orexin boosted · ↓ Serotonin tone lowered, Sedation");
});

test("the tooltip lists every loading with what drugs do to it", () => {
  const tip = axisTooltip({ loadings: LOADINGS }, 1, { signed: true, nameOf, t }).split("\n");
  assert.equal(tip.length, 1 + LOADINGS.length);
  assert.equal(tip[1], "+0.45  Orexin: mostly blocked");
  assert.equal(tip[3], "−0.35  H1: mostly blocked");
});

test("pca loadings carry the raw mean of each feature", () => {
  const prof = new Map([["a", new Map([["x", -1], ["y", 1]])], ["b", new Map([["x", -3]])]]);
  const { axes } = pca(["a", "b"], prof);
  const x = axes[0].loadings.find((l) => l.target === "x");
  assert.equal(x.mean, -2);
});

test("archScore: a parabola is all arch, noise or a line none", async () => {
  const { archScore } = await import("../../public/js/drug-map/axis.js");
  const pts = (xs, f) => xs.map((x) => ({ x, y: f(x) }));
  const xs = [-2, -1, 0, 1, 2, 3, -3];
  assert.ok(archScore(pts(xs, (x) => x * x - 2)) > 0.999);
  // PCA's PC2 is uncorrelated with PC1; a scatter with no curve scores near 0.
  const scatter = [[-2, 1], [-1, -1], [0, 1], [1, -1], [2, 1], [-2, -1], [-1, 1], [0, -1], [1, 1], [2, -1]];
  assert.ok(archScore(scatter.map(([x, y]) => ({ x, y }))) < 0.05);
  assert.equal(archScore(pts([1, 2, 3], (x) => x)), null);
  assert.equal(archScore(pts([1, 1, 1, 1], (x) => x)), null);
});

test("archScore: an arch opening sideways (both ends on one side) counts too", async () => {
  const { archScore } = await import("../../public/js/drug-map/axis.js");
  const ys = [-3, -2, -1, 0, 1, 2, 3];
  assert.ok(archScore(ys.map((y) => ({ x: 4 - y * y, y }))) > 0.999);
});
