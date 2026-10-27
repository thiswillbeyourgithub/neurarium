// Drugs map presets (public/js/drug-map/presets.js): what a click loads, when its button
// lights, and that every preset names classes / targets the dataset actually has (a typo
// would load an empty map with no error) and has a name in both languages.
// Run: node --test tools/tests/

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildProfiles, DEFAULT_VIEW, filterDrugs, mappableDrugs } from "../../public/js/drug-map/model.js";
import { matchesPreset, PRESETS, presetView } from "../../public/js/drug-map/presets.js";

const root = new URL("../../public/", import.meta.url);
const drugs = readFileSync(new URL("data/drugs.jsonl", root), "utf8")
  .split("\n").filter(Boolean).map((l) => JSON.parse(l));
// The `effect` each binding carries in the viewer (signed profiles read it), derived as
// js/data/bindings.js bindingDisplayFields does: the full resolver also wants the quote
// table, too heavy here, so this repeats its one rule.
const actions = JSON.parse(readFileSync(new URL("data/meta.json", root), "utf8")).drug_actions;
const viewerDrugs = drugs.map((d) => ({ ...d, bindings: (d.bindings || []).map((b) => ({ ...b,
  effect: b.affinity_only ? null : b.effect || (actions[b.action] || {}).effect || "modulate" })) }));

test("presetView starts from the defaults and holds cats as a Set", () => {
  const ap = PRESETS.find((p) => p.id === "ap_dopamine");
  const v = presetView(ap);
  assert.equal(v.color, "nbn");
  assert.equal(v.normalize, DEFAULT_VIEW.normalize);
  assert.ok(v.cats instanceof Set && v.cats.has("antipsychotic_atypical"));
  assert.equal(v.hidden.size, 0);
});

test("a preset matches its own view, ignores hidden drugs, not a changed one", () => {
  for (const p of PRESETS) {
    const v = presetView(p);
    assert.ok(matchesPreset(v, p), p.id);
    assert.ok(matchesPreset({ ...v, hidden: new Set(["haloperidol"]) }, p), p.id);
    assert.ok(!matchesPreset({ ...v, labels: !v.labels }, p), p.id);
    // One preset never lights another's button.
    for (const q of PRESETS) if (q !== p) assert.ok(!matchesPreset(v, q), `${p.id} vs ${q.id}`);
  }
});

test("every preset class and target exists in the dataset", () => {
  const cats = new Set(drugs.map((d) => (d.categories && d.categories[0]) || "other"));
  const targets = new Set(drugs.flatMap((d) => (d.bindings || []).map((b) => b.target)));
  for (const p of PRESETS) {
    for (const c of p.view.cats || []) assert.ok(cats.has(c), `${p.id}: class ${c}`);
    for (const k of p.view.only || []) assert.ok(targets.has(k), `${p.id}: target ${k}`);
  }
});

test("every receptor preset places at least 3 drugs", () => {
  // A class with no measured Ki at all (the mood stabilizers: channel blockers PDSP and
  // GtoPdb hold no Ki for) never reaches the map, so its preset would load an empty plot.
  // Tone presets are skipped: their profile is derived in the viewer (flowSystems).
  for (const p of PRESETS.filter((q) => presetView(q).sources.every((s) => s === "receptors"))) {
    const v = presetView(p);
    const kept = mappableDrugs(filterDrugs(viewerDrugs, v));
    const placed = buildProfiles(kept, { normalize: v.normalize, signed: v.signed, only: v.only, measuredKi: v.measuredKi });
    assert.ok(placed.size >= 3, `${p.id}: ${placed.size} drug(s) placed`);
  }
});

test("every preset has an English and a French name", () => {
  for (const lang of ["en", "fr"]) {
    const src = readFileSync(new URL(`js/i18n/${lang}.js`, root), "utf8");
    for (const p of PRESETS) assert.ok(src.includes(`"drugmap.preset.${p.id}":`), `${lang}: ${p.id}`);
  }
});
