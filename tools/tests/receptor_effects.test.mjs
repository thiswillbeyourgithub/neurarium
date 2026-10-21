// Unit tests for public/js/receptor-effects.js: owner rows resolve, and the reader of
// the build-time effect index (derived/effects.json) resolves the file's ids. The join
// itself is Python (tools/tests/test_effect_index.py).
// Run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { groupByMode, resolveEffects, readEffectIndex } from "../../public/js/receptor-effects.js";

const modes = {
  agonism: { label: "Agonism", actions: ["agonist", "partial_agonist"] },
  antagonism: { label: "Antagonism", actions: ["antagonist", "inverse_agonist"] },
  both: { label: "Either", actions: ["agonist", "antagonist"] },
};
const labels = { sedation: "Sedation", hallucinations: "Hallucinations",
                 weight_gain: "Weight gain" };
const nodes = {
  h1: resolveEffects([{ mode: "antagonism", effect: "sedation", grade: "verified" },
                      { mode: "antagonism", effect: "weight_gain", grade: "verified" }],
                     modes, labels),
  "5ht2a": resolveEffects([{ mode: "agonism", effect: "hallucinations", grade: "verified" }],
                          modes, labels),
  alpha1a: resolveEffects([{ mode: "both", effect: "sedation", grade: "verified" }],
                          modes, labels),
};

test("resolveEffects labels mode and effect", () => {
  assert.equal(nodes.h1[0].label, "Sedation");
  assert.equal(nodes.h1[0].modeLabel, "Antagonism");
  assert.equal(nodes.h1[0].provenance, "verified");
});

const targetsById = new Map(["h1", "5ht2a", "alpha1a"].map((id) => [id, { id }]));
const effectsByTarget = new Map(Object.entries(nodes));
const quetiapine = { id: "quetiapine", bindings: [{ target: "h1", action: "antagonist", viaMetabolite: null },
                                                  { target: "alpha1a", action: "antagonist", viaMetabolite: null }] };
const pro = { id: "pro", bindings: [{ target: "5ht2a", action: "agonist", viaMetabolite: "Active" }] };
const drugsById = new Map([quetiapine, pro].map((d) => [d.id, d]));

test("readEffectIndex resolves owners, drugs and via bindings, sorted by label", () => {
  const json = { effects: [
    { id: "sedation", owners: [{ target: "h1", mode: "antagonism" }, { target: "alpha1a", mode: "both" }],
      drugs: [{ drug: "quetiapine", via: [{ target: "h1", action: "antagonist", mode: "antagonism" },
                                         { target: "alpha1a", action: "antagonist", mode: "both" }] }] },
    { id: "hallucinations", owners: [{ target: "5ht2a", mode: "agonism" }],
      drugs: [{ drug: "pro", via: [{ target: "5ht2a", action: "agonist", mode: "agonism",
                                     via_metabolite: "Active" }] }] },
  ] };
  const { effects, byDrug } = readEffectIndex(json, targetsById, effectsByTarget, drugsById, labels);
  assert.deepEqual(effects.map((e) => e.id), ["hallucinations", "sedation"]);
  const sed = effects[1];
  assert.deepEqual(sed.owners.map((o) => o.target.id), ["h1", "alpha1a"]);
  assert.equal(sed.owners[0].node, nodes.h1[0]);
  assert.equal(sed.drugs[0].via[1].binding, quetiapine.bindings[1]);
  assert.equal(byDrug.get("pro")[0].via[0].binding, pro.bindings[0]);
  assert.deepEqual(byDrug.get("quetiapine").map((e) => e.label), ["Sedation"]);
});

test("readEffectIndex skips ids the loaded data lacks and survives a null file", () => {
  const json = { effects: [{ id: "sedation", owners: [{ target: "gone", mode: "antagonism" }],
    drugs: [{ drug: "gone", via: [] },
            { drug: "quetiapine", via: [{ target: "h1", action: "agonist", mode: "agonism" }] }] }] };
  const { effects, byDrug } = readEffectIndex(json, targetsById, effectsByTarget, drugsById, labels);
  assert.deepEqual(effects[0].owners, []);
  assert.deepEqual(effects[0].drugs, []);
  assert.equal(byDrug.size, 0);
  assert.deepEqual(readEffectIndex(null, targetsById, effectsByTarget, drugsById, labels).effects, []);
});

test("the file tools/render_api.py writes from the emitted data reads back whole", () => {
  const dir = mkdtempSync(join(tmpdir(), "effects-"));
  try {
    const out = join(dir, "effects.json");
    const root = new URL("../..", import.meta.url).pathname;
    execFileSync("python", [join(root, "tools/render_api.py"), "--effects-out", out]);
    const json = JSON.parse(readFileSync(out, "utf8"));
    assert.ok(json.effects.length > 0);
    // Stub the loaded data from the file's own ids: every owner and via must resolve.
    const tById = new Map(), rows = new Map(), dById = new Map();
    const row = (target, mode, effect) => {
      tById.set(target, { id: target });
      if (!rows.has(target)) rows.set(target, []);
      if (!rows.get(target).some((n) => n.mode === mode && n.effect === effect)) {
        rows.get(target).push({ mode, effect });
      }
    };
    for (const e of json.effects) {
      for (const o of e.owners) row(o.target, o.mode, e.id);
      for (const d of e.drugs) {
        if (!dById.has(d.drug)) dById.set(d.drug, { id: d.drug, bindings: [] });
        for (const v of d.via) {
          assert.ok(v.target && v.action && v.mode, JSON.stringify(v));
          dById.get(d.drug).bindings.push({ target: v.target, action: v.action,
            viaMetabolite: v.via_metabolite || null });
        }
      }
    }
    const { effects } = readEffectIndex(json, tById, rows, dById, {});
    for (const [i, e] of json.effects.entries()) {
      const got = effects.find((x) => x.id === e.id);
      assert.equal(got.owners.length, e.owners.length, e.id);
      assert.equal(got.drugs.length, e.drugs.length, e.id);
      assert.equal(got.drugs.reduce((n, d) => n + d.via.length, 0),
                   e.drugs.reduce((n, d) => n + d.via.length, 0), `${e.id} #${i}`);
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("groupByMode follows the vocabulary order and keeps an unknown mode last", () => {
  const modes = { agonism: {}, antagonism: {}, both: {} };
  const rows = [{ m: "antagonism", id: 1 }, { m: "odd", id: 2 }, { m: "agonism", id: 3 },
    { m: "antagonism", id: 4 }];
  const got = groupByMode(rows, (r) => r.m, modes);
  assert.deepEqual(got.map((g) => [g.mode, g.rows.map((r) => r.id)]),
    [["agonism", [3]], ["antagonism", [1, 4]], ["odd", [2]]]);
  assert.deepEqual(groupByMode(null, (r) => r.m, modes), []);
});
