// Unit tests for public/js/legend/drug-groups.js: the Drugs browse list's groupings
// (class, name, approval decade, half-life bucket), unknowns trailing.
// Run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { groupDrugs } from "../../public/js/legend/drug-groups.js";

const t = (k, p) => (p ? `${k}:${JSON.stringify(p)}` : k);
const cats = { antipsychotic_conventional: "Conventional", antipsychotic_atypical: "Atypical" };
const drug = (name, cat, year, hours) => ({
  name, categories: [cat],
  firstApproval: year ? { year } : null,
  halfLife: hours === undefined ? null : { hours },
});
const DRUGS = [
  drug("Clozapine", "antipsychotic_atypical", 1972, 12),
  drug("Haloperidol", "antipsychotic_conventional", 1959, 20),
  drug("Aripiprazole", "antipsychotic_atypical", 2002, 75),
  drug("Chlorpromazine", "antipsychotic_conventional", 1953, 30),
  drug("Zotepine", "antipsychotic_atypical", null, 4),
  drug("Mystery", "nootropic", 1999),
];
const shape = (groups) => groups.map((g) => [g.label, g.drugs.map((d) => d.name)]);

test("class: meta order, leftovers after, A->Z within", () => {
  assert.deepEqual(shape(groupDrugs(DRUGS, "class", { cats, t })), [
    ["Conventional", ["Chlorpromazine", "Haloperidol"]],
    ["Atypical", ["Aripiprazole", "Clozapine", "Zotepine"]],
    ["nootropic", ["Mystery"]],
  ]);
});

test("name: one group per initial", () => {
  assert.deepEqual(shape(groupDrugs(DRUGS, "name", { cats, t })).map(([l]) => l),
    ["A", "C", "H", "M", "Z"]);
});

test("year: decades in order, by year within, unknown last", () => {
  assert.deepEqual(shape(groupDrugs(DRUGS, "year", { cats, t })), [
    ['drugs.decade:{"decade":1950}', ["Chlorpromazine", "Haloperidol"]],
    ['drugs.decade:{"decade":1970}', ["Clozapine"]],
    ['drugs.decade:{"decade":1990}', ["Mystery"]],
    ['drugs.decade:{"decade":2000}', ["Aripiprazole"]],
    ["drugs.unknownYear", ["Zotepine"]],
  ]);
});

test("halflife: buckets by hours, unknown last", () => {
  assert.deepEqual(shape(groupDrugs(DRUGS, "halflife", { cats, t })), [
    ["drugs.hl.short", ["Zotepine"]],
    ["drugs.hl.day", ["Clozapine", "Haloperidol"]],
    ["drugs.hl.days", ["Chlorpromazine"]],
    ["drugs.hl.long", ["Aripiprazole"]],
    ["drugs.unknownHalfLife", ["Mystery"]],
  ]);
});
