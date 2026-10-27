// Drugs map plot title (public/js/drug-map/title.js): the sentence derived from the view,
// with the real English catalogue so a template typo shows here.
// Run: node --test tools/tests/

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DEFAULT_VIEW } from "../../public/js/drug-map/model.js";
import { plotTitle, nameSet, shortName } from "../../public/js/drug-map/title.js";

// Load the English messages the browser would (i18n/en.js assigns onto a global).
globalThis.window = { __I18N_MESSAGES__: {} };
new Function(readFileSync(new URL("../../public/js/i18n/en.js", import.meta.url), "utf8"))();
const EN = window.__I18N_MESSAGES__.en;
const t = (key, vars = {}) => {
  assert.ok(key in EN, `missing ${key}`);
  return EN[key].replace(/\{(\w+)\}/g, (_, k) => String(vars[k]));
};

const ctx = {
  t,
  families: [["Antipsychotics", ["antipsychotic_atypical", "antipsychotic_conventional"]],
    ["Antidepressants", ["ssri", "snri"]]],
  systems: [["Dopaminergic", ["d1", "d2", "dat"]], ["Histaminergic", ["h1", "h2"]], ["GABAergic", ["gaba_a"]]],
  catName: (c) => ({ ssri: "SSRIs", antipsychotic_atypical: "Atypical antipsychotics" })[c] || c,
  nameOf: (k) => ({ d2: "D2", h1: "H1", "5ht2a": "5-HT2A", mao_a: "Monoamine oxidase A (MAO-A)",
    mao_b: "Monoamine oxidase B (MAO-B)" })[k] || k,
};
const view = (patch) => ({ ...DEFAULT_VIEW, hidden: new Set(), ...patch });
const AP = new Set(["antipsychotic_atypical", "antipsychotic_conventional"]);

test("the default view: all drugs, whole profile", () => {
  assert.equal(plotTitle(view({}), ctx), "All drugs by whole receptor binding profile");
});

test("whole families and whole systems are named by their group", () => {
  assert.equal(plotTitle(view({ cats: AP, only: ["d1", "d2", "dat", "h1"], color: "nbn" }), ctx),
    "Antipsychotics by dopaminergic and H1 binding, colored by nomenclature");
  // A partial family lists its classes; GABAergic keeps its capitals.
  assert.equal(plotTitle(view({ cats: new Set(["ssri", "antipsychotic_atypical"]), only: ["gaba_a", "d2", "h1"] }), ctx),
    "SSRIs and atypical antipsychotics by GABAergic, D2 and H1 binding");
});

test("one or two targets read as direct axes", () => {
  assert.equal(plotTitle(view({ cats: AP, only: ["d2", "5ht2a"] }), ctx),
    "Antipsychotics by D2 affinity (x) vs 5-HT2A affinity (y)");
  assert.equal(plotTitle(view({ only: ["d2"] }), ctx), "All drugs by D2 affinity");
  // Full target names shrink to their alias.
  assert.equal(plotTitle(view({ cats: new Set(["ssri"]), only: ["mao_a", "mao_b"] }), ctx),
    "SSRIs by MAO-A affinity (x) vs MAO-B affinity (y)");
  assert.equal(plotTitle(view({ only: [] }), ctx), "All drugs: no target picked");
});

test("tone source, years, and a long set falls back to a count", () => {
  assert.equal(plotTitle(view({ sources: ["tone"], years: [1990, 9999] }), ctx),
    "All drugs by net neurotransmitter tone (approved 1990–…)");
  assert.equal(plotTitle(view({ sources: ["receptors", "tone", "effects"] }), ctx),
    "All drugs by whole receptor binding profile, net neurotransmitter tone and possible body effects");
  const many = ["a", "b", "c", "d", "e", "f"];
  const wide = { ...ctx, systems: many.map((k) => [k.toUpperCase(), [k, `${k}2`]]) };
  assert.equal(plotTitle(view({ cats: new Set(many), only: [...many, "a2"] }), wide),
    "6 drug classes by binding to 7 targets");
  // A key outside the picker (no mapped drug binds it) is left out of the sentence.
  assert.equal(plotTitle(view({ only: ["d1", "d2", "dat", "bche"] }), ctx), "All drugs by dopaminergic binding");
  // Partial systems, too many to list: counted, named by their systems.
  const sys = { ...ctx, systems: [["Dopaminergic", ["d1", "d2", "d3", "d4", "d5", "dat", "comt"]]] };
  assert.equal(plotTitle(view({ only: ["d1", "d2", "d3", "d4", "d5", "dat"] }), sys),
    "All drugs by binding to 6 dopaminergic targets");
});

test("shortName keeps the shorter of a name and its trailing alias", () => {
  assert.equal(shortName("Serotonin transporter (SERT)"), "SERT");
  assert.equal(shortName("μ (MOR)"), "μ");
  assert.equal(shortName("D2"), "D2");
  assert.equal(shortName("Orexin receptors (OX1R/OX2R)"), "OX1R/OX2R");
});

test("picked keys from several sources each get their clause", () => {
  const mixed = { ...ctx, systems: [...ctx.systems, ["Body effects", ["effect:sedation", "effect:weight_gain", "effect:nausea"]]],
    nameOf: (k) => ({ "effect:sedation": "Sedation", "effect:weight_gain": "Weight gain", "effect:nausea": "Nausea" })[k] || ctx.nameOf(k) };
  assert.equal(plotTitle(view({ only: ["d2", "h1", "effect:sedation"] }), mixed), "All drugs by D2 and H1 binding and sedation");
  assert.equal(plotTitle(view({ only: ["effect:sedation", "effect:weight_gain"] }), mixed),
    "All drugs by sedation (x) vs weight gain (y)");
});

test("nameSet: whole groups first, leftovers in pick order", () => {
  assert.deepEqual(nameSet(["h1", "d1", "d2", "dat"], ctx.systems, ctx.nameOf), ["Dopaminergic", "H1"]);
});
