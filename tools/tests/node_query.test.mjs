// The Data browser's stackable filters (public/js/node-browser/query.js): filters
// combine on a row's owner, the last filter picks the listed rows, "include
// metabolites" adds the matched drugs' metabolite drugs, and value sorting groups by
// kind with unvalued rows last. Run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import {
  kindsFor, metaboliteOwners, runFilters, sortRows, filterTouchesDrugs,
  serializeFilters, parseFilters, SORTS, DEFAULT_SORT,
} from "../../public/js/node-browser/query.js";

const LABELS = { drug_categories: "Drug classes", drug_half_life: "Drug half-life",
                 drug_tmax: "Drug time to peak", structures: "Regions" };
const row = (kind, owner, notion, value = null) =>
  ({ kind, owner, name: owner, notion, grade: "verified", value });
const ROWS = [
  row("drug_categories", "diazepam", "benzodiazepine"),
  row("drug_categories", "alprazolam", "benzodiazepine"),
  row("drug_categories", "oxazepam", "anxiolytic"),
  row("drug_categories", "sertraline", "SSRI"),
  row("drug_half_life", "diazepam", "T½ 2 days", 48),
  row("drug_half_life", "alprazolam", "T½ 11 h", 11),
  row("drug_half_life", "oxazepam", "T½ 8 h", 8),
  row("drug_half_life", "sertraline", "T½ 26 h", 26),
  row("drug_tmax", "diazepam", "Tmax 1 h", 1),
  row("structures", "amygdala_R", "Limbic"),
];
const ctx = {
  kinds: Object.keys(LABELS),
  kindLabel: (k) => LABELS[k],
  fold: (s) => s.toLowerCase(),
  metabolites: metaboliteOwners([
    { id: "diazepam", metabolites: [{ drugId: "oxazepam" }, { drugId: null }] },
    { id: "alprazolam", metabolites: [] },
    { id: "sertraline", metabolites: [] },
  ]),
};
const owners = (rows) => rows.map((r) => `${r.kind}:${r.owner}`);

test("kind box: empty = all, exact label = one kind, else label substring", () => {
  assert.equal(kindsFor("", ctx.kinds, ctx.kindLabel, ctx.fold), null);
  assert.deepEqual([...kindsFor("drug half-life", ctx.kinds, ctx.kindLabel, ctx.fold)],
    ["drug_half_life"]);
  assert.deepEqual([...kindsFor("drug", ctx.kinds, ctx.kindLabel, ctx.fold)],
    ["drug_categories", "drug_half_life", "drug_tmax"]);
});

test("AND narrows owners, the last filter picks the rows: benzo half-lives", () => {
  const out = runFilters(ROWS, [
    { kind: "Drug classes", text: "benzo" },
    { kind: "Drug half-life", text: "", op: "and" },
  ], ctx);
  assert.deepEqual(owners(out), ["drug_half_life:diazepam", "drug_half_life:alprazolam"]);
});

test("include metabolites adds the matched drugs' metabolite drugs", () => {
  const out = runFilters(ROWS, [
    { kind: "Drug classes", text: "benzo", metabolites: true },
    { kind: "Drug half-life", text: "", op: "and" },
  ], ctx);
  assert.deepEqual(owners(out),
    ["drug_half_life:diazepam", "drug_half_life:alprazolam", "drug_half_life:oxazepam"]);
  assert.equal(filterTouchesDrugs(ROWS, { kind: "Regions", text: "" }, ctx), false);
  assert.equal(filterTouchesDrugs(ROWS, { kind: "Drug classes", text: "benzo" }, ctx), true);
});

test("OR unions rows, XOR keeps owners matched by exactly one side", () => {
  const or = runFilters(ROWS, [
    { kind: "Drug classes", text: "ssri" },
    { kind: "Drug time to peak", text: "", op: "or" },
  ], ctx);
  assert.deepEqual(owners(or), ["drug_categories:sertraline", "drug_tmax:diazepam"]);
  const xor = runFilters(ROWS, [
    { kind: "Drug classes", text: "benzo" },
    { kind: "Drug time to peak", text: "", op: "xor" },
  ], ctx);
  assert.deepEqual(owners(xor), ["drug_categories:alprazolam"]);
});

test("value sort groups by kind, unvalued rows last", () => {
  const rows = sortRows(ROWS.slice(), "valueDesc");
  assert.deepEqual(rows.slice(0, 5).map((r) => r.value), [48, 26, 11, 8, 1]);
  assert.ok(rows.slice(5).every((r) => r.value == null));
  assert.deepEqual(sortRows(ROWS.slice(), "valueAsc").slice(0, 4).map((r) => r.value),
    [8, 11, 26, 48]);
});

test("the filter stack round-trips through its URL form, null at default", () => {
  assert.equal(serializeFilters([{ kind: "", text: "", op: "and" }]), null);
  const stack = [
    { op: "and", kind: "Drug classes", text: "a,b|c", metabolites: true },
    { op: "xor", kind: "Drug half-life", text: "", metabolites: false },
  ];
  const v = serializeFilters(stack);
  assert.equal(v, "|Drug classes|a%2Cb%7Cc|m,xor|Drug half-life");
  assert.equal(parseFilters(serializeFilters([{ kind: "", text: "100%" }]))[0].text, "100%");
  assert.deepEqual(parseFilters(v), stack);
  assert.equal(parseFilters("bogus|x")[0].op, "and");
});

test("the default sort is smallest value first, and is a menu entry", () => {
  assert.equal(DEFAULT_SORT, "valueAsc");
  assert.equal(SORTS[0], DEFAULT_SORT);
});
