// Drugs map "Extra details" (public/js/drug-map/extras.js): the JSON Lines behind the map.
// Run: node --test tools/tests/

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { coordinatesText, weightsText } from "../../public/js/drug-map/extras.js";
import { DEFAULT_VIEW, pca } from "../../public/js/drug-map/model.js";

globalThis.window = { __I18N_MESSAGES__: {} };
new Function(readFileSync(new URL("../../public/js/i18n/en.js", import.meta.url), "utf8"))();
const EN = window.__I18N_MESSAGES__.en;
const t = (key) => { assert.ok(key in EN, `missing ${key}`); return EN[key]; };
const nameOf = (k) => ({ d2: "D2", h1: "H1", sert: "SERT" })[k] || k;
const drugName = (id) => id[0].toUpperCase() + id.slice(1);
const prof = new Map([
  ["halo", new Map([["d2", 3.6], ["h1", 0.4]])],
  ["fluox", new Map([["sert", 3.0]])],
  ["queti", new Map([["d2", 1.0], ["h1", 2.5], ["sert", 0.1]])],
]);
const ids = ["halo", "fluox", "queti"];
const parse = (text) => text.split("\n").map((l) => JSON.parse(l));

test("coordinates: one JSON line per drug, features largest first", () => {
  const rows = parse(coordinatesText(ids, prof, { nameOf, drugName }));
  assert.deepEqual(rows[0], { drug: "Halo", D2: 3.6, H1: 0.4 });
  assert.deepEqual(Object.keys(rows[2]), ["drug", "H1", "D2", "SERT"]);
});

test("weights: every feature with PC1, PC2 and the mean the PCA centred on", () => {
  const { axes } = pca(ids, prof);
  const rows = parse(weightsText(axes, null, nameOf));
  assert.equal(rows.length, 3);
  const d2 = rows.find((r) => r.feature === "D2");
  assert.equal(d2.mean, Math.round((4.6 / 3) * 1e4) / 1e4);
  // A unit eigenvector: the squared PC1 weights sum to 1.
  assert.ok(Math.abs(rows.reduce((s, r) => s + r.PC1 ** 2, 0) - 1) < 1e-3);
  // Directly plotted features are the axes themselves.
  assert.deepEqual(parse(weightsText(null, ["d2", "h1"], nameOf)),
    [{ feature: "D2", x: 1, y: 0 }, { feature: "H1", x: 0, y: 1 }]);
});
