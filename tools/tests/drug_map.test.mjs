// Unit tests for public/js/drug-map/model.js: affinity profiles (Ki floor, unmeasured
// default, normalization), the 2-component PCA, the view filter and the colouring.
// Run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import {
  buildProfiles, pca, filterDrugs, colorize, DEFAULT_VIEW, PKI_FLOOR, PKI_UNMEASURED,
} from "../../public/js/drug-map/model.js";

const b = (target, ki) => ({ target, ki: ki === undefined ? null : { median: ki } });
const drug = (id, bindings, extra = {}) => ({ id, name: id, bindings, categories: ["x"], ...extra });

test("affinity: Ki floor, unmeasured default, strongest duplicate", () => {
  const raw = buildProfiles([
    drug("a", [b("d2", 1), b("h1", 20000), b("m1"), b("d2", 100)]),
  ], { normalize: false }).get("a");
  assert.equal(raw.get("d2"), 9 - PKI_FLOOR);       // 1 nM, the stronger duplicate
  assert.equal(raw.has("h1"), false);              // 20 µM: below the floor
  assert.equal(raw.get("m1"), PKI_UNMEASURED - PKI_FLOOR);
});

test("normalize scales each profile to unit length; drugs with nothing drop out", () => {
  const p = buildProfiles([drug("a", [b("d2", 1), b("m1", 1)]), drug("none", [b("h1", 1e6)])]);
  assert.ok(Math.abs(Math.hypot(...p.get("a").values()) - 1) < 1e-12);
  assert.equal(p.has("none"), false);
});

test("pca separates two binding families along PC1, deterministically", () => {
  const drugs = [
    drug("hal", [b("d2", 1)]), drug("flu", [b("d2", 2), b("h1", 5000)]),
    drug("ssri", [b("sert", 1)]), drug("parox", [b("sert", 0.1), b("m1", 1000)]),
  ];
  const prof = buildProfiles(drugs);
  const ids = drugs.map((d) => d.id);
  const { points, axes } = pca(ids, prof);
  const x = (id) => points.get(id).x;
  assert.ok(Math.sign(x("hal")) === Math.sign(x("flu")));
  assert.ok(Math.sign(x("ssri")) === Math.sign(x("parox")));
  assert.ok(Math.sign(x("hal")) !== Math.sign(x("ssri")));
  assert.ok(axes[0].share > 0.5 && axes[0].share <= 1);
  assert.ok(axes[0].loadings[0].w > 0);             // sign-fixed
  assert.deepEqual(pca(ids, prof).points, points);  // same view, same map
});

test("filter: categories, year range (unknown year drops), hidden", () => {
  const drugs = [
    drug("old", [], { categories: ["ap"], firstApproval: { year: 1955 } }),
    drug("new", [], { categories: ["ap"], firstApproval: { year: 2015 } }),
    drug("nod", [], { categories: ["ad"] }),
  ];
  const ids = (v) => filterDrugs(drugs, { ...DEFAULT_VIEW, ...v }).map((d) => d.id);
  assert.deepEqual(ids({}), ["old", "new", "nod"]);
  assert.deepEqual(ids({ cats: new Set(["ap"]) }), ["old", "new"]);
  assert.deepEqual(ids({ years: [1950, 1999] }), ["old"]);
  assert.deepEqual(ids({ hidden: new Set(["new"]) }), ["old", "nod"]);
});

test("colorize: category hue stable across filters, unknown last, year ramp", () => {
  const catLabels = { ap: "Antipsychotic", ad: "Antidepressant" };
  const all = [drug("a", [], { categories: ["ap"] }), drug("b", [], { categories: ["ad"] })];
  const full = colorize(all, "category", { catLabels, unknown: "?" });
  const only = colorize([all[1]], "category", { catLabels, unknown: "?" });
  assert.equal(only.colorOf.get("b"), full.colorOf.get("b"));
  const lab = colorize([...all, drug("c", [], { originator: { name: "Janssen" } })], "lab",
    { catLabels, unknown: "?" });
  assert.deepEqual(lab.legend.map((l) => l.label), ["Janssen", "?"]);
  const yr = colorize([drug("o", [], { firstApproval: { year: 1950 } }),
    drug("n", [], { firstApproval: { year: 2020 } })], "year", { catLabels, unknown: "?" });
  assert.deepEqual(yr.ramp, { from: 1950, to: 2020 });
});
