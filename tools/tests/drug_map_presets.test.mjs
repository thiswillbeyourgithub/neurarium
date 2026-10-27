// Drugs map presets (public/js/drug-map/presets.js): what a click loads, when its button
// lights, and that every preset names classes / targets the dataset actually has (a typo
// would load an empty map with no error) and has a name in both languages.
// Run: node --test tools/tests/

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DEFAULT_VIEW } from "../../public/js/drug-map/model.js";
import { matchesPreset, PRESETS, presetView } from "../../public/js/drug-map/presets.js";

const root = new URL("../../public/", import.meta.url);
const drugs = readFileSync(new URL("data/drugs.jsonl", root), "utf8")
  .split("\n").filter(Boolean).map((l) => JSON.parse(l));

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

test("every preset has an English and a French name", () => {
  for (const lang of ["en", "fr"]) {
    const src = readFileSync(new URL(`js/i18n/${lang}.js`, root), "utf8");
    for (const p of PRESETS) assert.ok(src.includes(`"drugmap.preset.${p.id}":`), `${lang}: ${p.id}`);
  }
});
