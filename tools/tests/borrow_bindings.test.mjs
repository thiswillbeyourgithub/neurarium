// Unit tests for public/js/data/bindings.js borrowBindings: a prodrug takes its
// active metabolites' raw bindings as its own, any other drug keeps them apart in
// `metabolite_bindings` (read by the derived readouts via `allBindings`), each tagged
// with the metabolite's name. Run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { borrowBindings } from "../../public/js/data/bindings.js";

const sert = { target: "sert", action: "reuptake_inhibitor" };
const h1 = { target: "h1", action: "antagonist" };

test("a non-prodrug keeps its metabolites' bindings apart, tagged", () => {
  const parent = { id: "parent", name: "Parent", bindings: [h1],
    metabolites: [{ name: "Norparent", bindings: [sert] }] };
  borrowBindings([parent]);
  assert.deepEqual(parent.bindings, [h1]);
  assert.deepEqual(parent.metabolite_bindings, [{ ...sert, via_metabolite: "Norparent" }]);
});

test("a metabolite that is a modeled drug lends that drug's bindings", () => {
  const child = { id: "child", name: "Child", bindings: [sert] };
  const parent = { id: "parent", name: "Parent", bindings: [h1],
    metabolites: [{ name: "Child", drug_id: "child" }] };
  borrowBindings([parent, child]);
  assert.deepEqual(parent.metabolite_bindings, [{ ...sert, via_metabolite: "Child" }]);
});

test("a prodrug takes them as its own bindings", () => {
  const pro = { id: "pro", name: "Pro", prodrug: { value: true }, bindings: [],
    metabolites: [{ name: "Active", bindings: [sert] }] };
  borrowBindings([pro]);
  assert.deepEqual(pro.bindings, [{ ...sert, via_metabolite: "Active" }]);
  assert.equal(pro.metabolite_bindings, undefined);
});
