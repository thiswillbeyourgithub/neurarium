// Unit tests for public/js/drug-map/model.js: affinity profiles (Ki floor, unmeasured
// default, normalization, signed / tone / subset features), the 2-component PCA, the view filter and the colouring.
// Run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import {
  buildProfiles, pca, filterDrugs, colorize, directPoints, DEFAULT_VIEW, PKI_FLOOR, PKI_UNMEASURED,
} from "../../public/js/drug-map/model.js";
import { placeLabels, sizesFor, FONT_PX } from "../../public/js/drug-map/layout.js";

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

const act = (target, ki, effect) => ({ ...b(target, ki), effect });

test("signed: agonist and antagonist get opposite signs, direction-less counts 0", () => {
  const p = buildProfiles([
    drug("ago", [act("d2", 1, "boost"), act("h1", 1)]),
    drug("ant", [act("d2", 1, "block")]),
    drug("part", [act("d2", 1, "modulate")]),
  ], { normalize: false, signed: true });
  assert.equal(p.get("ago").get("d2"), 4);
  assert.equal(p.get("ago").has("h1"), false);
  assert.equal(p.get("ant").get("d2"), -4);
  assert.equal(p.get("part").get("d2"), 2);
});

test("tone and both: tone keys, each block normalized on its own", () => {
  const flow = { dopamine: { sum: -0.6 }, serotonin: { sum: 0.8 } };
  const d = drug("a", [b("d2", 1)], { flowSystems: flow });
  const tone = buildProfiles([d], { source: "tone", normalize: false }).get("a");
  assert.deepEqual([...tone], [["tone:dopamine", -0.6], ["tone:serotonin", 0.8]]);
  const both = buildProfiles([d], { source: "both" }).get("a");
  assert.equal(both.get("d2"), 1);                 // receptor block alone: unit length
  assert.ok(Math.abs(Math.hypot(both.get("tone:dopamine"), both.get("tone:serotonin")) - 1) < 1e-12);
});

test("only + directPoints: 5-HT2A vs D2 as raw axes, a drug lacking both drops", () => {
  const drugs = [drug("a", [b("d2", 1), b("5ht2a", 10), b("h1", 1)]), drug("b", [b("d2", 10)]), drug("c", [b("h1", 1)])];
  const p = buildProfiles(drugs, { only: ["5ht2a", "d2"], normalize: false });
  assert.equal(p.has("c"), false);
  assert.equal(p.get("a").has("h1"), false);
  const pts = directPoints(["a", "b"], p, ["5ht2a", "d2"]);
  assert.deepEqual(pts.get("a"), { x: 3, y: 4 });
  assert.deepEqual(pts.get("b"), { x: 0, y: 3 });
});

test("colorize: metabolic route (major, else sole substrate) and Ki coverage", () => {
  const sub = (label, strength) => ({ enzyme: label, label, role: "substrate", strength });
  const drugs = [
    drug("major", [], { enzymes: [sub("CYP2D6", "major"), sub("CYP3A4", "minor")] }),
    drug("sole", [], { enzymes: [sub("CYP2D6")] }),
    drug("many", [], { enzymes: [sub("CYP2D6"), sub("CYP1A2")] }),
  ];
  const route = colorize(drugs, "route", { catLabels: {}, unknown: "?", t: (k) => k });
  assert.equal(route.colorOf.get("major"), route.colorOf.get("sole"));
  assert.deepEqual(route.legend.map((r) => [r.label, r.count]), [["CYP2D6", 2], ["?", 1]]);
  const ki = colorize([
    drug("all", [b("d2", 1)]), drug("some", [b("d2", 1), b("h1")]), drug("none", [b("h1")]), drug("empty", []),
  ], "ki", { catLabels: {}, unknown: "?", t: (k) => k });
  assert.deepEqual(ki.legend.map((r) => r.label), ["drugmap.ki.all", "drugmap.ki.some", "drugmap.ki.none", "?"]);
});

test("layout: name size follows crowding, within its range", () => {
  const grid = (step) => Array.from({ length: 25 }, (_, i) => ({ x: (i % 5) * step, y: Math.floor(i / 5) * step }));
  assert.equal(sizesFor(grid(100)).font, FONT_PX[1]);
  assert.equal(sizesFor(grid(5)).font, FONT_PX[0]);
  const mid = sizesFor(grid(30)).font;
  assert.ok(mid > FONT_PX[0] && mid < FONT_PX[1]);
});

test("layout: names never overlap a dot or each other, and fall back to another side", () => {
  const measure = (s) => s.length * 7;
  const o = { font: 12, r: 5, width: 400, height: 300, measure };
  // A close right neighbour blocks the right slot of one, so its name goes elsewhere.
  const pts = [{ id: "a", x: 200, y: 150, text: "Alpha" }, { id: "b", x: 215, y: 150, text: "Beta" }];
  const out = placeLabels(pts, o);
  const box = (id) => {
    const at = out.get(id), p = pts.find((q) => q.id === id);
    return { x: at.x, y: at.y - 12, w: measure(p.text), h: 12 * 1.3 };
  };
  const hit = (a, c) => a.x < c.x + c.w && c.x < a.x + a.w && a.y < c.y + c.h && c.y < a.y + a.h;
  assert.equal(out.size, 2);
  for (const id of ["a", "b"]) for (const p of pts) assert.ok(!hit(box(id), { x: p.x - 5, y: p.y - 5, w: 10, h: 10 }));
  assert.ok(!hit(box("a"), box("b")));
  // A name with no room at all inside the frame is dropped rather than overlapping.
  assert.equal(placeLabels([{ id: "c", x: 2, y: 2, text: "Long name here" }], { ...o, width: 20, height: 20 }).size, 0);
});

test("colorize nbn: each nomenclature takes the class colour it shares most drugs with", () => {
  const catLabels = { atyp: "Atypical", ssri: "SSRI", other: "Other" };
  const d = (id, cat, nbn) => drug(id, [], { categories: [cat], nbn });
  const drugs = [
    d("a1", "atyp", "DS-RAn"), d("a2", "atyp", "DS-RAn"), d("a3", "atyp", "D-RAn"),
    d("s1", "ssri", "S-RI"), d("s2", "ssri", "S-RI"), d("x", "atyp", "S-RI"),
  ];
  const ctx = { catLabels, unknown: "?", t: (k) => k };
  const cls = colorize(drugs, "category", ctx).colorOf, nbn = colorize(drugs, "nbn", ctx).colorOf;
  // DS-RAn keeps the atypical colour, S-RI the SSRI one; D-RAn takes a spare colour.
  for (const id of ["a1", "a2", "s1", "s2"]) assert.equal(nbn.get(id), cls.get(id));
  assert.notEqual(nbn.get("a3"), nbn.get("a1"));
  assert.notEqual(nbn.get("a3"), nbn.get("s1"));
});
